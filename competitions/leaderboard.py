from __future__ import annotations

from django.core.cache import cache
from django.db.models import Count, Max, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from competitions.eligibility import eligible_videos_filter
from competitions.models import Competition, CompetitionVideo
from competitions.serializers import LeaderboardEntrySerializer, PublicCompetitionSerializer
from organizations.models import Organization
from organizations.serializers import OrganizationSerializer

PUBLIC_LEADERBOARD_CACHE_SECONDS = 300
PUBLIC_LEADERBOARD_CACHE_PREFIX = "public_lb:v1:"


def aggregate_candidate_leaderboard_rows(competition: Competition) -> list[dict]:
    rows = (
        CompetitionVideo.objects.filter(**eligible_videos_filter(competition))
        .values(
            "candidate_profile_id",
            "candidate_profile__user__first_name",
            "candidate_profile__user__last_name",
            "candidate_profile__user__username",
            "candidate_profile__profile_image_url",
            "candidate_profile__is_profile_complete",
        )
        .annotate(
            views=Coalesce(Sum("views"), 0),
            likes=Coalesce(Sum("likes"), 0),
            comments=Coalesce(Sum("scored_comments"), 0),
            shares=Coalesce(Sum("shares"), 0),
            brand_mention_comments=Coalesce(Sum("brand_mention_comments"), 0),
            engagement_score=Coalesce(Sum("engagement_score"), 0.0),
            video_count=Count("id"),
            last_synced_at=Max("last_synced_at"),
        )
        .order_by("-engagement_score", "-views")
    )

    entries: list[dict] = []
    for index, row in enumerate(rows, start=1):
        name = (
            f"{row['candidate_profile__user__first_name']} "
            f"{row['candidate_profile__user__last_name']}"
        ).strip() or row["candidate_profile__user__username"]
        initials = "".join(part[0].upper() for part in name.split()[:2]) or "?"

        entries.append(
            {
                "rank": index,
                "candidate_id": row["candidate_profile_id"],
                "name": name,
                "username": row["candidate_profile__user__username"],
                "initials": initials,
                "profile_image_url": row["candidate_profile__profile_image_url"] or "",
                "is_profile_complete": row["candidate_profile__is_profile_complete"],
                "views": row["views"],
                "likes": row["likes"],
                "comments": row["comments"],
                "shares": row["shares"],
                "brand_mention_comments": row["brand_mention_comments"],
                "engagement_score": float(row["engagement_score"]),
                "video_count": row["video_count"],
                "last_synced_at": row["last_synced_at"],
            }
        )

    return entries


def build_leaderboard(competition: Competition) -> list[dict]:
    return [
        {
            "rank": entry["rank"],
            "candidate_id": entry["candidate_id"],
            "name": entry["name"],
            "username": entry["username"],
            "initials": entry["initials"],
            "profile_image_url": entry["profile_image_url"],
            "views": entry["views"],
            "likes": entry["likes"],
            "comments": entry["comments"],
            "shares": entry["shares"],
            "engagement_score": entry["engagement_score"],
            "video_count": entry["video_count"],
            "last_synced_at": entry["last_synced_at"],
        }
        for entry in aggregate_candidate_leaderboard_rows(competition)
    ]


def invalidate_public_leaderboard_cache(org_slug: str) -> None:
    cache.delete(f"{PUBLIC_LEADERBOARD_CACHE_PREFIX}{org_slug}")


def build_leaderboard_response(
    organization: Organization,
    competition: Competition,
    *,
    use_cache: bool = False,
) -> dict:
    cache_key = f"{PUBLIC_LEADERBOARD_CACHE_PREFIX}{organization.slug}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    leaderboard_available = competition.status == Competition.Status.ENDED
    leaderboard = build_leaderboard(competition) if leaderboard_available else []
    last_updated = max(
        (entry["last_synced_at"] for entry in leaderboard if entry["last_synced_at"]),
        default=timezone.now(),
    )

    payload = {
        "organization": OrganizationSerializer(organization).data,
        "competition": PublicCompetitionSerializer(competition).data,
        "leaderboard": LeaderboardEntrySerializer(leaderboard, many=True).data,
        "last_updated_at": last_updated,
        "leaderboard_available": leaderboard_available,
    }

    if use_cache and leaderboard_available:
        cache.set(cache_key, payload, PUBLIC_LEADERBOARD_CACHE_SECONDS)

    return payload
