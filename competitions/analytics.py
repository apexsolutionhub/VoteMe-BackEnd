from __future__ import annotations

from datetime import timedelta

from django.db.models import Max, Sum
from django.utils import timezone

from competitions.criteria import _legacy_achievements, build_criteria_achievements
from competitions.models import CandidateProfile, Competition, EngagementSnapshot


def _video_label(video) -> str:
    title = (getattr(video, "title", None) or "").strip()
    if title:
        return title if len(title) <= 48 else f"{title[:45]}..."
    url = getattr(video, "url", "")
    video_id = getattr(video, "id", 0)
    cleaned = url.rstrip("/").split("/")[-1]
    if cleaned and len(cleaned) <= 24:
        return cleaned
    return f"Video #{video_id}"


def _build_portfolio_history(videos, history_since) -> list[dict]:
    """
    Total engagement across all videos at each hour where any video synced.

    Uses the latest snapshot per video up to each bucket so partial syncs do
    not make totals look like they crashed.
    """
    snapshots = list(
        EngagementSnapshot.objects.filter(
            video__in=videos,
            captured_at__gte=history_since,
        ).order_by("captured_at")
    )
    if not snapshots:
        return []

    video_ids = list(videos.values_list("id", flat=True))
    buckets = sorted(
        {
            snap.captured_at.replace(minute=0, second=0, microsecond=0)
            for snap in snapshots
        }
    )

    history: list[dict] = []
    for bucket in buckets:
        bucket_end = bucket + timedelta(hours=1)
        total_views = 0
        total_likes = 0
        total_comments = 0
        total_shares = 0
        has_data = False

        for video_id in video_ids:
            latest = (
                EngagementSnapshot.objects.filter(
                    video_id=video_id,
                    captured_at__lt=bucket_end,
                )
                .order_by("-captured_at")
                .first()
            )
            if latest is None:
                continue
            has_data = True
            total_views += latest.views
            total_likes += latest.likes
            total_comments += latest.comments
            total_shares += latest.shares

        if not has_data:
            continue

        history.append(
            {
                "captured_at": bucket.isoformat(),
                "label": bucket.strftime("%b %d, %H:%M"),
                "views": total_views,
                "likes": total_likes,
                "comments": total_comments,
                "shares": total_shares,
            }
        )

    return history


def build_candidate_analytics(
    profile: CandidateProfile,
    competition: Competition | None,
    *,
    rank: int | None = None,
) -> dict:
    if competition is None:
        return {
            "totals": {
                "views": 0,
                "likes": 0,
                "comments": 0,
                "shares": 0,
                "brand_mention_comments": 0,
                "last_synced_at": None,
                "competition_status": "draft",
                "live_tracking_enabled": False,
                "tracking_interval_minutes": 10,
            },
            "history": [],
            "videos": [],
            "achievements": _legacy_achievements(profile, {}, 0),
            "profile_complete": profile.is_profile_complete,
            "video_count": 0,
            "unlocked_achievements": 0,
            "total_achievements": 0,
            "competition_result": None,
        }

    eligible_videos = profile.videos.filter(
        competition=competition,
        is_active=True,
        is_competition_eligible=True,
    )
    video_count = eligible_videos.count()

    totals_agg = eligible_videos.aggregate(
        views=Sum("views"),
        likes=Sum("likes"),
        comments=Sum("scored_comments"),
        shares=Sum("shares"),
        brand_mention_comments=Sum("brand_mention_comments"),
        engagement_score=Sum("engagement_score"),
        last_synced_at=Max("last_synced_at"),
    )

    totals = {
        "views": totals_agg["views"] or 0,
        "likes": totals_agg["likes"] or 0,
        "comments": totals_agg["comments"] or 0,
        "shares": totals_agg["shares"] or 0,
        "brand_mention_comments": totals_agg["brand_mention_comments"] or 0,
        "last_synced_at": totals_agg["last_synced_at"],
        "competition_status": competition.status,
        "live_tracking_enabled": competition.live_tracking_enabled,
        "tracking_interval_minutes": competition.tracking_interval_minutes,
    }

    history_since = timezone.now() - timedelta(days=7)
    history = _build_portfolio_history(eligible_videos, history_since)

    if not history and video_count > 0:
        now = timezone.now()
        history = [
            {
                "captured_at": now.isoformat(),
                "label": now.strftime("%b %d, %H:%M"),
                "views": totals["views"],
                "likes": totals["likes"],
                "comments": totals["comments"],
                "shares": totals["shares"],
            }
        ]

    video_rows = [
        {
            "id": video.id,
            "url": video.url,
            "label": _video_label(video),
            "title": video.title,
            "views": video.views,
            "likes": video.likes,
            "comments": video.comments,
            "shares": video.shares,
            "brand_mention_comments": video.brand_mention_comments,
            "last_synced_at": video.last_synced_at,
            "platform_published_at": video.platform_published_at,
            "is_competition_eligible": video.is_competition_eligible,
            "ineligibility_reason": video.ineligibility_reason,
        }
        for video in eligible_videos.order_by("-views", "-updated_at")
    ]

    totals["engagement_score"] = totals_agg["engagement_score"] or 0
    achievements = build_criteria_achievements(
        competition,
        profile,
        totals,
        video_count=video_count,
        rank=rank,
    )
    unlocked = sum(1 for item in achievements if item["unlocked"])

    competition_result = None
    if (
        competition is not None
        and competition.status == Competition.Status.ENDED
        and rank is not None
    ):
        competition_result = {
            "rank": rank,
            "engagement_score": float(totals.get("engagement_score") or 0),
            "visible": True,
            "on_podium": rank <= 3,
        }

    return {
        "totals": totals,
        "history": history,
        "videos": video_rows,
        "achievements": achievements,
        "profile_complete": profile.is_profile_complete,
        "video_count": video_count,
        "unlocked_achievements": unlocked,
        "total_achievements": len(achievements),
        "competition_result": competition_result,
    }
