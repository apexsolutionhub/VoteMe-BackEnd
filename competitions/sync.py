from __future__ import annotations

import logging
import threading
from datetime import timedelta

from django.utils import timezone

from competitions.models import Competition, CompetitionVideo, EngagementSnapshot
from competitions.comment_mentions import refresh_video_comment_scores
from competitions.eligibility import evaluate_video_eligibility, reevaluate_competition_videos
from competitions.tiktok.public_metrics import fetch_public_tiktok_metrics

logger = logging.getLogger(__name__)


def calculate_engagement_score(
    views: int,
    likes: int,
    comments: int,
    shares: int,
    weights: dict[str, float],
    brand_mention_comments: int = 0,
) -> float:
    score = (
        views * weights.get("views", 1.0)
        + likes * weights.get("likes", 3.0)
        + comments * weights.get("comments", 5.0)
        + shares * weights.get("shares", 2.0)
        + brand_mention_comments * weights.get("brand_mentions", 10.0)
    )
    return max(score, 0.0)


def _is_due_for_sync(video: CompetitionVideo) -> bool:
    if not video.last_synced_at:
        return True
    interval = max(video.competition.tracking_interval_minutes, 1)
    return timezone.now() - video.last_synced_at >= timedelta(minutes=interval)


def _metrics_changed(
    video: CompetitionVideo,
    *,
    views: int,
    likes: int,
    comments: int,
    shares: int,
) -> bool:
    return (
        video.views != views
        or video.likes != likes
        or video.comments != comments
        or video.shares != shares
    )


def _apply_score(
    video: CompetitionVideo,
    *,
    metrics_synced: bool,
    record_snapshot: bool = False,
) -> CompetitionVideo:
    evaluate_video_eligibility(video, persist=False)

    competition = video.competition
    weights = competition.get_scoring_weights()
    if video.is_competition_eligible:
        score = calculate_engagement_score(
            video.views,
            video.likes,
            video.scored_comments,
            video.shares,
            weights,
            brand_mention_comments=video.brand_mention_comments,
        )
    else:
        score = 0.0
    video.engagement_score = score
    update_fields = [
        "title",
        "views",
        "likes",
        "comments",
        "scored_comments",
        "shares",
        "brand_mention_comments",
        "platform_published_at",
        "is_competition_eligible",
        "ineligibility_reason",
        "engagement_score",
        "updated_at",
    ]
    if metrics_synced:
        video.last_synced_at = timezone.now()
        update_fields.append("last_synced_at")
    video.save(update_fields=update_fields)

    if metrics_synced and record_snapshot:
        EngagementSnapshot.objects.create(
            video=video,
            views=video.views,
            likes=video.likes,
            comments=video.comments,
            shares=video.shares,
            engagement_score=score,
        )
    return video


def sync_video_metrics(video: CompetitionVideo, *, force: bool = False) -> bool:
    """Fetch and persist metrics. Returns True when external metrics were retrieved."""
    competition = video.competition

    if not force and not competition.live_tracking_enabled:
        return False

    if not force and not _is_due_for_sync(video):
        return False

    metrics_synced = False
    previous_views = video.views
    previous_likes = video.likes
    previous_comments = video.comments
    previous_shares = video.shares

    if competition.social_platform == Competition.SocialPlatform.TIKTOK:
        public = fetch_public_tiktok_metrics(video.url)
        if public:
            video.views = public["views"]
            video.likes = public["likes"]
            video.comments = public["comments"]
            video.shares = public["shares"]
            title = public.get("title")
            if title:
                video.title = title
            published = public.get("platform_published_at")
            if published:
                video.platform_published_at = published
            metrics_synced = True
            canonical_url = public.get("canonical_url")
            if canonical_url and canonical_url != video.url:
                from competitions.validators import extract_video_id

                video.url = canonical_url
                video.platform_video_id = extract_video_id(canonical_url, "tiktok")
                video.save(update_fields=["url", "platform_video_id", "updated_at"])

    refresh_video_comment_scores(video, persist=False)

    if metrics_synced:
        changed = _metrics_changed(
            video,
            views=previous_views,
            likes=previous_likes,
            comments=previous_comments,
            shares=previous_shares,
        )
        _apply_score(
            video,
            metrics_synced=True,
            record_snapshot=changed or force,
        )
        return True

    _apply_score(video, metrics_synced=False, record_snapshot=False)
    return False


def recompute_competition_comment_scores(competition: Competition) -> int:
    updated = 0
    for video in competition.videos.filter(is_active=True).select_related("competition"):
        refresh_video_comment_scores(video, persist=False)
        _apply_score(video, metrics_synced=False, record_snapshot=False)
        updated += 1
    return updated


def sync_competition_videos(
    competition: Competition, *, force: bool = False
) -> dict[str, int]:
    if not force and not competition.live_tracking_enabled:
        return {"synced_count": 0, "failed_count": 0, "attempted_count": 0}

    synced_count = 0
    failed_count = 0
    videos = competition.videos.filter(is_active=True).select_related("competition")
    attempted_count = videos.count()
    for video in videos:
        if sync_video_metrics(video, force=force):
            synced_count += 1
        elif force:
            failed_count += 1
    reevaluate_competition_videos(competition)
    return {
        "synced_count": synced_count,
        "failed_count": failed_count,
        "attempted_count": attempted_count,
    }


def sync_video_by_id(video_id: int, *, force: bool = True) -> CompetitionVideo:
    video = CompetitionVideo.objects.select_related("competition").get(pk=video_id)
    sync_video_metrics(video, force=force)
    video.refresh_from_db()
    return video


def enqueue_video_sync(video_id: int, *, force: bool = True) -> None:
    """Run metrics sync in a background thread so API responses stay fast."""

    def _run() -> None:
        from django.db import close_old_connections

        close_old_connections()
        try:
            sync_video_by_id(video_id, force=force)
        except Exception:
            logger.exception("Background sync failed for video %s", video_id)
        finally:
            close_old_connections()

    threading.Thread(target=_run, daemon=True).start()
