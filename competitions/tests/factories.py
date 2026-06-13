from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from organizations.models import Organization, OrganizationMember

User = get_user_model()


def create_test_org(
    *,
    slug: str = "test-org",
    name: str = "Test Org",
) -> Organization:
    org, _ = Organization.objects.get_or_create(
        slug=slug,
        defaults={
            "name": name,
            "org_code": slug.upper()[:8],
            "status": Organization.Status.ACTIVE,
        },
    )
    return org


def create_test_competition(
    organization: Organization,
    *,
    status: str = "live",
    start_at=None,
    end_at=None,
) -> "Competition":
    from competitions.models import Competition

    now = timezone.now()
    competition, _ = Competition.objects.get_or_create(
        organization=organization,
        defaults={
            "title": "Test Competition",
            "status": status,
            "start_at": start_at if start_at is not None else now - timedelta(days=1),
            "end_at": end_at,
        },
    )
    if competition.status != status:
        competition.status = status
        competition.save(update_fields=["status", "updated_at"])
    return competition


def create_test_candidate(
    organization: Organization,
    *,
    username: str = "candidate1",
) -> tuple[User, "CandidateProfile"]:
    from competitions.models import CandidateProfile

    user, _ = User.objects.get_or_create(
        username=username,
        defaults={
            "role": User.Role.CANDIDATE,
            "first_name": "Test",
            "last_name": "Candidate",
        },
    )
    OrganizationMember.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={"role": OrganizationMember.Role.CANDIDATE},
    )
    profile, _ = CandidateProfile.objects.get_or_create(
        user=user,
        organization=organization,
    )
    return user, profile


def create_test_video(
    competition: "Competition",
    profile: "CandidateProfile",
    *,
    url: str = "https://www.tiktok.com/@user/video/1",
    views: int = 0,
    likes: int = 0,
    comments: int = 0,
    scored_comments: int | None = None,
    shares: int = 0,
    platform_published_at=None,
    is_active: bool = True,
) -> "CompetitionVideo":
    from competitions.models import CompetitionVideo
    from competitions.sync import _apply_score

    video, _ = CompetitionVideo.objects.update_or_create(
        competition=competition,
        url=url,
        defaults={
            "candidate_profile": profile,
            "views": views,
            "likes": likes,
            "comments": comments,
            "scored_comments": scored_comments if scored_comments is not None else comments,
            "shares": shares,
            "platform_published_at": platform_published_at,
            "is_active": is_active,
        },
    )
    _apply_score(video, metrics_synced=False, record_snapshot=False)
    video.refresh_from_db()
    return video
