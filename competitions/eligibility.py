from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from competitions.models import Competition, CompetitionVideo

INELIGIBILITY_BEFORE_START = "published_before_start"
INELIGIBILITY_AFTER_END = "published_after_end"
INELIGIBILITY_NOT_STARTED = "competition_not_started"


def get_effective_publish_time(video: CompetitionVideo) -> datetime:
    """Platform publish time when known; otherwise when the candidate registered the URL."""
    if video.platform_published_at:
        return video.platform_published_at
    return video.created_at


def compute_video_eligibility(video: CompetitionVideo) -> tuple[bool, str]:
    competition = video.competition

    if competition.start_at is None:
        return False, INELIGIBILITY_NOT_STARTED

    published_at = get_effective_publish_time(video)

    if published_at < competition.start_at:
        return False, INELIGIBILITY_BEFORE_START

    if competition.end_at and published_at > competition.end_at:
        return False, INELIGIBILITY_AFTER_END

    return True, ""


def evaluate_video_eligibility(
    video: CompetitionVideo,
    *,
    persist: bool = False,
) -> CompetitionVideo:
    eligible, reason = compute_video_eligibility(video)
    video.is_competition_eligible = eligible
    video.ineligibility_reason = "" if eligible else reason

    if persist:
        video.save(
            update_fields=[
                "is_competition_eligible",
                "ineligibility_reason",
                "updated_at",
            ]
        )
    return video


def eligible_videos_filter(competition: Competition):
    """Q object / kwargs for videos that count toward scoring and milestones."""
    return {
        "competition": competition,
        "is_active": True,
        "is_competition_eligible": True,
    }


def eligible_videos_queryset(competition: Competition):
    return CompetitionVideo.objects.filter(**eligible_videos_filter(competition))


def reevaluate_competition_videos(competition: Competition) -> int:
    """Re-check every active video after go-live, end, or bulk sync."""
    updated = 0
    for video in competition.videos.filter(is_active=True).select_related("competition"):
        before_eligible = video.is_competition_eligible
        before_reason = video.ineligibility_reason
        evaluate_video_eligibility(video, persist=True)
        if (
            video.is_competition_eligible != before_eligible
            or video.ineligibility_reason != before_reason
        ):
            updated += 1
    return updated
