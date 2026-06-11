from django.db.models import Max, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import UserSerializer
from competitions.models import (
    CandidateProfile,
    Competition,
    CompetitionVideo,
    TikTokConnection,
)
from competitions.serializers import (
    CandidateCompetitionVideoSerializer,
    CandidateProfileSerializer,
    CompetitionSerializer,
    CompetitionVideoSerializer,
    CreateCandidateSerializer,
    LeaderboardEntrySerializer,
    PublicCompetitionSerializer,
)
from competitions.analytics import build_candidate_analytics
from competitions.sync import sync_competition_videos, sync_video_metrics
from organizations.mixins import TenantViewMixin
from organizations.models import Organization, OrganizationMember
from organizations.permissions import IsOrgAdmin, IsOrgCandidate
from organizations.serializers import OrganizationSerializer


def build_leaderboard(competition: Competition) -> list[dict]:
    profiles = (
        CandidateProfile.objects.filter(organization=competition.organization)
        .select_related("user")
        .prefetch_related("videos")
    )

    entries = []
    for profile in profiles:
        videos = profile.videos.filter(competition=competition, is_active=True)
        if not videos.exists():
            continue

        totals = videos.aggregate(
            views=Sum("views"),
            likes=Sum("likes"),
            comments=Sum("comments"),
            shares=Sum("shares"),
            engagement_score=Sum("engagement_score"),
            last_synced_at=Max("last_synced_at"),
        )

        name = (
            f"{profile.user.first_name} {profile.user.last_name}".strip()
            or profile.user.username
        )
        initials = "".join(part[0].upper() for part in name.split()[:2]) or "?"

        entries.append(
            {
                "candidate_id": profile.id,
                "name": name,
                "username": profile.user.username,
                "initials": initials,
                "profile_image_url": profile.profile_image_url,
                "views": totals["views"] or 0,
                "likes": totals["likes"] or 0,
                "comments": totals["comments"] or 0,
                "shares": totals["shares"] or 0,
                "engagement_score": float(totals["engagement_score"] or 0),
                "video_count": videos.count(),
                "last_synced_at": totals["last_synced_at"],
            }
        )

    entries.sort(key=lambda item: item["engagement_score"], reverse=True)
    for index, entry in enumerate(entries, start=1):
        entry["rank"] = index

    return entries


class OrganizationCompetitionView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get(self, request):
        organization = self.get_organization()
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return Response(
                {"detail": "No competition configured yet."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(CompetitionSerializer(competition).data)

    def patch(self, request):
        organization = self.get_organization()
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            competition = Competition.objects.create(organization=organization)

        serializer = CompetitionSerializer(competition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CompetitionStatusView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request):
        organization = self.get_organization()
        competition = get_object_or_404(
            Competition,
            organization=organization,
            pk=request.data.get("competition_id"),
        )
        new_status = request.data.get("status")
        if new_status not in Competition.Status.values:
            return Response(
                {"detail": "Invalid status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        competition.status = new_status
        if new_status == Competition.Status.LIVE and competition.start_at is None:
            competition.start_at = timezone.now()
        if new_status == Competition.Status.ENDED and competition.end_at is None:
            competition.end_at = timezone.now()
        competition.save()
        return Response(CompetitionSerializer(competition).data)


class SyncCompetitionView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def post(self, request):
        organization = self.get_organization()
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return Response(
                {"detail": "No competition found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        synced = sync_competition_videos(competition)
        leaderboard = build_leaderboard(competition)
        return Response(
            {
                "detail": f"Synced {synced} videos.",
                "synced_count": synced,
                "leaderboard": LeaderboardEntrySerializer(leaderboard, many=True).data,
                "last_synced_at": timezone.now(),
            }
        )


class OrgCandidateListCreateView(TenantViewMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get_queryset(self):
        organization = self.get_organization()
        return (
            CandidateProfile.objects.filter(organization=organization)
            .select_related("user")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CreateCandidateSerializer
        return CandidateProfileSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return Response(CandidateProfileSerializer(queryset, many=True).data)

    def create(self, request, *args, **kwargs):
        serializer = CreateCandidateSerializer(
            data=request.data,
            context={"organization": self.get_organization()},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        profile = CandidateProfile.objects.get(
            user=user,
            organization=self.get_organization(),
        )
        return Response(
            CandidateProfileSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )


class OrgCandidateDetailView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def delete(self, request, pk):
        organization = self.get_organization()
        profile = get_object_or_404(CandidateProfile, pk=pk, organization=organization)
        username = profile.user.username
        profile.user.delete()
        return Response(
            {"detail": f"Candidate account '{username}' has been deleted."},
            status=status.HTTP_200_OK,
        )


class CandidateMeProfileView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgCandidate]

    def get_profile(self):
        organization = self.get_organization()
        return get_object_or_404(
            CandidateProfile,
            user=self.request.user,
            organization=organization,
        )

    def get(self, request):
        profile = self.get_profile()
        competition = request.organization.competitions.order_by("-created_at").first()
        serializer = CandidateProfileSerializer(
            profile,
            context={"social_platform": competition.social_platform if competition else "tiktok"},
        )
        return Response(serializer.data)

    def patch(self, request):
        profile = self.get_profile()
        competition = request.organization.competitions.order_by("-created_at").first()
        serializer = CandidateProfileSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"social_platform": competition.social_platform if competition else "tiktok"},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CandidateProfileSerializer(profile).data)


class CandidateVideoListCreateView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgCandidate]

    def get_context(self):
        organization = self.get_organization()
        profile = get_object_or_404(
            CandidateProfile,
            user=self.request.user,
            organization=organization,
        )
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return None, None
        return profile, competition

    def get(self, request):
        profile, competition = self.get_context()
        if competition is None:
            return Response([])
        videos = list(
            profile.videos.filter(competition=competition, is_active=True).order_by(
                "-updated_at"
            )
        )
        for video in videos:
            sync_video_metrics(video)
            video.refresh_from_db()
        return Response(CandidateCompetitionVideoSerializer(videos, many=True).data)

    def post(self, request):
        profile, competition = self.get_context()
        if competition is None:
            return Response(
                {"detail": "No active competition."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CompetitionVideoSerializer(
            data=request.data,
            context={
                "competition": competition,
                "candidate_profile": profile,
            },
        )
        serializer.is_valid(raise_exception=True)
        video = serializer.save()
        return Response(
            CandidateCompetitionVideoSerializer(video).data,
            status=status.HTTP_201_CREATED,
        )


class CandidateVideoDetailView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgCandidate]

    def delete(self, request, pk):
        organization = self.get_organization()
        profile = get_object_or_404(
            CandidateProfile,
            user=request.user,
            organization=organization,
        )
        video = get_object_or_404(
            CompetitionVideo,
            pk=pk,
            candidate_profile=profile,
        )
        video.is_active = False
        video.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class CandidateStatsView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgCandidate]

    def get(self, request):
        organization = self.get_organization()
        profile = get_object_or_404(
            CandidateProfile,
            user=request.user,
            organization=organization,
        )
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return Response(
                {
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
                }
            )

        videos = list(profile.videos.filter(competition=competition, is_active=True))
        for video in videos:
            sync_video_metrics(video)

        videos = profile.videos.filter(competition=competition, is_active=True)
        totals = videos.aggregate(
            views=Sum("views"),
            likes=Sum("likes"),
            comments=Sum("comments"),
            shares=Sum("shares"),
            brand_mention_comments=Sum("brand_mention_comments"),
            last_synced_at=Max("last_synced_at"),
        )
        tiktok_connected = TikTokConnection.objects.filter(
            candidate_profile=profile
        ).exists()

        return Response(
            {
                "views": totals["views"] or 0,
                "likes": totals["likes"] or 0,
                "comments": totals["comments"] or 0,
                "shares": totals["shares"] or 0,
                "brand_mention_comments": totals["brand_mention_comments"] or 0,
                "last_synced_at": totals["last_synced_at"],
                "competition_status": competition.status,
                "live_tracking_enabled": competition.live_tracking_enabled,
                "tracking_interval_minutes": competition.tracking_interval_minutes,
                "tiktok_connected": tiktok_connected,
            }
        )


class CandidateAnalyticsView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgCandidate]

    def get(self, request):
        organization = self.get_organization()
        profile = get_object_or_404(
            CandidateProfile,
            user=request.user,
            organization=organization,
        )
        competition = organization.competitions.order_by("-created_at").first()
        if competition:
            videos = profile.videos.filter(competition=competition, is_active=True)
            for video in videos:
                sync_video_metrics(video)
        return Response(build_candidate_analytics(profile, competition))


class PublicCompetitionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, org_slug):
        organization = get_object_or_404(Organization, slug=org_slug, status=Organization.Status.ACTIVE)
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return Response(
                {"detail": "Competition not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(PublicCompetitionSerializer(competition).data)


class AdminLeaderboardView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get(self, request):
        organization = self.get_organization()
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return Response(
                {"detail": "Competition not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if competition.live_tracking_enabled:
            sync_competition_videos(competition)

        leaderboard = build_leaderboard(competition)
        return Response(
            {
                "organization": OrganizationSerializer(organization).data,
                "competition": PublicCompetitionSerializer(competition).data,
                "leaderboard": LeaderboardEntrySerializer(leaderboard, many=True).data,
                "last_updated_at": timezone.now(),
            }
        )


class PublicLeaderboardView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, org_slug):
        return Response(
            {"detail": "Leaderboard is not publicly available."},
            status=status.HTTP_404_NOT_FOUND,
        )


class OrganizationMeView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organization = self.get_organization()
        membership = self.get_membership()
        competition = organization.competitions.order_by("-created_at").first()
        return Response(
            {
                "organization": {
                    "id": str(organization.id),
                    "name": organization.name,
                    "slug": organization.slug,
                    "org_code": organization.org_code,
                },
                "membership": {
                    "role": membership.role,
                },
                "user": UserSerializer(request.user).data,
                "competition": (
                    CompetitionSerializer(competition).data if competition else None
                ),
            }
        )
