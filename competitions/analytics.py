from __future__ import annotations

from django.db.models import Max, Sum
from django.db.models.functions import TruncHour
from django.utils import timezone

from competitions.models import CandidateProfile, Competition, EngagementSnapshot, TikTokConnection


def _video_label(url: str, video_id: int) -> str:
    cleaned = url.rstrip("/").split("/")[-1]
    if cleaned and len(cleaned) <= 24:
        return cleaned
    return f"Video #{video_id}"


def _build_achievements(
    profile: CandidateProfile,
    totals: dict,
    rank: int | None,
    video_count: int,
    tiktok_connected: bool,
) -> list[dict]:
    views = int(totals.get("views") or 0)
    likes = int(totals.get("likes") or 0)
    score = float(totals.get("engagement_score") or 0)
    brand_mentions = int(totals.get("brand_mention_comments") or 0)

    def milestone(
        id: str,
        title: str,
        description: str,
        unlocked: bool,
        *,
        current: int | float | None = None,
        target: int | float | None = None,
    ) -> dict:
        item = {
            "id": id,
            "title": title,
            "description": description,
            "unlocked": unlocked,
        }
        if current is not None and target is not None and target > 0:
            item["current"] = current
            item["target"] = target
            item["progress"] = min(100, round((current / target) * 100))
        return item

    achievements = [
        milestone(
            "profile_complete",
            "Profile ready",
            "Complete your candidate profile to join the competition.",
            profile.is_profile_complete,
        ),
        milestone(
            "first_video",
            "First video live",
            "Submit at least one competition video.",
            video_count >= 1,
            current=video_count,
            target=1,
        ),
        milestone(
            "tiktok_connected",
            "TikTok connected",
            "Link TikTok for automatic engagement sync.",
            tiktok_connected,
        ),
        milestone(
            "views_100",
            "100 views",
            "Reach 100 total video views.",
            views >= 100,
            current=views,
            target=100,
        ),
        milestone(
            "views_1k",
            "1K views",
            "Reach 1,000 total video views.",
            views >= 1000,
            current=views,
            target=1000,
        ),
        milestone(
            "likes_50",
            "50 likes",
            "Collect 50 likes across your videos.",
            likes >= 50,
            current=likes,
            target=50,
        ),
        milestone(
            "brand_mention",
            "Ella Resort buzz",
            "Get a comment mentioning Ella Resort.",
            brand_mentions >= 1,
            current=brand_mentions,
            target=1,
        ),
    ]
    return achievements


def build_candidate_analytics(profile: CandidateProfile, competition: Competition | None) -> dict:
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
                "tiktok_connected": False,
            },
            "history": [],
            "videos": [],
            "achievements": _build_achievements(profile, {}, None, 0, False),
            "profile_complete": profile.is_profile_complete,
            "video_count": 0,
            "unlocked_achievements": 0,
            "total_achievements": 10,
        }

    videos = profile.videos.filter(competition=competition, is_active=True)
    video_count = videos.count()

    totals_agg = videos.aggregate(
        views=Sum("views"),
        likes=Sum("likes"),
        comments=Sum("comments"),
        shares=Sum("shares"),
        brand_mention_comments=Sum("brand_mention_comments"),
        engagement_score=Sum("engagement_score"),
        last_synced_at=Max("last_synced_at"),
    )

    tiktok_connected = TikTokConnection.objects.filter(
        candidate_profile=profile
    ).exists()

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
        "tiktok_connected": tiktok_connected,
    }

    history_qs = (
        EngagementSnapshot.objects.filter(video__in=videos)
        .annotate(bucket=TruncHour("captured_at"))
        .values("bucket")
        .annotate(
            views=Sum("views"),
            likes=Sum("likes"),
            comments=Sum("comments"),
            shares=Sum("shares"),
            engagement_score=Sum("engagement_score"),
        )
        .order_by("bucket")
    )

    history = [
        {
            "captured_at": row["bucket"].isoformat() if row["bucket"] else None,
            "label": row["bucket"].strftime("%b %d, %H:%M") if row["bucket"] else "",
            "views": row["views"] or 0,
            "likes": row["likes"] or 0,
            "comments": row["comments"] or 0,
            "shares": row["shares"] or 0,
        }
        for row in history_qs
        if row["bucket"] is not None
    ]

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
            "label": _video_label(video.url, video.id),
            "views": video.views,
            "likes": video.likes,
            "comments": video.comments,
            "shares": video.shares,
            "brand_mention_comments": video.brand_mention_comments,
            "last_synced_at": video.last_synced_at,
        }
        for video in videos.order_by("-views", "-updated_at")
    ]

    achievements = _build_achievements(
        profile, totals, None, video_count, tiktok_connected
    )
    unlocked = sum(1 for item in achievements if item["unlocked"])

    return {
        "totals": totals,
        "history": history,
        "videos": video_rows,
        "achievements": achievements,
        "profile_complete": profile.is_profile_complete,
        "video_count": video_count,
        "unlocked_achievements": unlocked,
        "total_achievements": len(achievements),
    }
