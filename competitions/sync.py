from django.utils import timezone

from competitions.models import (
    Competition,
    CompetitionVideo,
    EngagementSnapshot,
    TikTokConnection,
)
from competitions.comment_mentions import count_brand_mention_comments
from competitions.tiktok import client
from competitions.tiktok.public_metrics import fetch_public_tiktok_metrics
from competitions.tiktok.service import sync_video_from_tiktok


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


def _apply_score(video: CompetitionVideo) -> CompetitionVideo:
    competition = video.competition
    weights = competition.get_scoring_weights()
    score = calculate_engagement_score(
        video.views,
        video.likes,
        video.comments,
        video.shares,
        weights,
        brand_mention_comments=video.brand_mention_comments,
    )
    video.engagement_score = score
    video.last_synced_at = timezone.now()
    video.save(
        update_fields=[
            "views",
            "likes",
            "comments",
            "shares",
            "brand_mention_comments",
            "engagement_score",
            "last_synced_at",
            "updated_at",
        ]
    )
    EngagementSnapshot.objects.create(
        video=video,
        views=video.views,
        likes=video.likes,
        comments=video.comments,
        shares=video.shares,
        engagement_score=score,
    )
    return video


def sync_video_metrics(video: CompetitionVideo) -> CompetitionVideo:
    competition = video.competition
    profile = video.candidate_profile

    connection = TikTokConnection.objects.filter(candidate_profile=profile).first()
    if competition.social_platform == Competition.SocialPlatform.TIKTOK:
        if (
            client.is_tiktok_configured()
            and connection is not None
        ):
            try:
                if sync_video_from_tiktok(video, connection):
                    video.brand_mention_comments = count_brand_mention_comments(video)
                    return _apply_score(video)
            except Exception:
                pass

        public = fetch_public_tiktok_metrics(video.url)
        if public:
            video.views = public["views"]
            video.likes = public["likes"]
            video.comments = public["comments"]
            video.shares = public["shares"]

    video.brand_mention_comments = count_brand_mention_comments(video)
    return _apply_score(video)


def sync_competition_videos(competition) -> int:
    count = 0
    videos = competition.videos.filter(is_active=True).select_related(
        "competition",
        "candidate_profile",
    )
    for video in videos:
        sync_video_metrics(video)
        count += 1
    return count
