from django.db.models import Count, Max, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.serializers import UserSerializer
from competitions.criteria import ensure_default_criteria
from competitions.leaderboard import (
    build_leaderboard,
    build_leaderboard_response,
    invalidate_public_leaderboard_cache,
)
from competitions.models import (
    CandidateProfile,
    Competition,
    CompetitionCriterion,
    CompetitionVideo,
)
from competitions.serializers import (
    CandidateCompetitionVideoSerializer,
    CandidateProfileSerializer,
    CompetitionCriterionSerializer,
    CompetitionSerializer,
    CompetitionVideoSerializer,
    CreateCandidateSerializer,
    LeaderboardEntrySerializer,
    PublicCompetitionSerializer,
)
from competitions.analytics import build_candidate_analytics
from competitions.eligibility import reevaluate_competition_videos
from competitions.scheduling import parse_competition_start_at
from competitions.standings import build_competition_standings
from competitions.sync import (
    enqueue_video_sync,
    recompute_competition_comment_scores,
    sync_competition_videos,
    sync_video_metrics,
)
from organizations.mixins import TenantViewMixin
from organizations.models import Organization, OrganizationMember
from organizations.permissions import IsOrgAdmin, IsOrgCandidate
from organizations.serializers import OrganizationSerializer


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
        ensure_default_criteria(competition)
        return Response(CompetitionSerializer(competition).data)

    def patch(self, request):
        organization = self.get_organization()
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            competition = Competition.objects.create(organization=organization)

        serializer = CompetitionSerializer(competition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        competition = serializer.save()
        recompute_competition_comment_scores(competition)
        return Response(CompetitionSerializer(competition).data)


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
        if new_status == Competition.Status.LIVE:
            start_at_raw = request.data.get("start_at")
            if start_at_raw:
                parsed_start = parse_competition_start_at(start_at_raw)
                if parsed_start is None:
                    return Response(
                        {"detail": "Invalid start date."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                competition.start_at = parsed_start
            elif competition.start_at is None:
                competition.start_at = timezone.now()
        if new_status == Competition.Status.ENDED and competition.end_at is None:
            competition.end_at = timezone.now()
        competition.save()
        reevaluate_competition_videos(competition)
        invalidate_public_leaderboard_cache(organization.slug)
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

        result = sync_competition_videos(competition, force=True)
        leaderboard = build_leaderboard(competition)
        synced = result["synced_count"]
        failed = result["failed_count"]
        attempted = result["attempted_count"]
        payload = {
            "detail": f"Synced {synced} videos.",
            "synced_count": synced,
            "failed_count": failed,
            "attempted_count": attempted,
            "leaderboard": LeaderboardEntrySerializer(leaderboard, many=True).data,
            "last_synced_at": timezone.now(),
        }
        if attempted and synced == 0:
            payload["sync_warning"] = (
                "No fresh TikTok metrics could be fetched. "
                "Try again in a minute or use Sync on individual videos."
            )
        elif failed:
            payload["sync_warning"] = (
                f"{failed} video(s) could not be refreshed from TikTok."
            )
        invalidate_public_leaderboard_cache(organization.slug)
        return Response(payload)


class OrgCandidateListCreateView(TenantViewMixin, generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get_queryset(self):
        organization = self.get_organization()
        return (
            CandidateProfile.objects.filter(organization=organization)
            .select_related("user", "organization")
            .annotate(
                video_count=Count(
                    "videos",
                    filter=Q(videos__is_active=True),
                    distinct=True,
                )
            )
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
        videos = profile.videos.filter(
            competition=competition,
            is_active=True,
        ).order_by("-updated_at")
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
        enqueue_video_sync(video.id, force=True)
        return Response(
            CandidateCompetitionVideoSerializer(video).data,
            status=status.HTTP_201_CREATED,
        )


class CandidateVideoSyncView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgCandidate]

    def post(self, request, pk):
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
            is_active=True,
        )
        metrics_updated = sync_video_metrics(video, force=True)
        video.refresh_from_db()
        payload = CandidateCompetitionVideoSerializer(video).data
        payload["metrics_updated"] = metrics_updated
        if not metrics_updated:
            platform = video.competition.social_platform
            if platform != Competition.SocialPlatform.TIKTOK:
                payload["sync_warning"] = (
                    f"Live metric refresh is not implemented for {platform} yet."
                )
            else:
                payload["sync_warning"] = (
                    "Could not fetch fresh TikTok metrics right now. "
                    "Try again in a minute."
                )
        return Response(payload)


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
        return Response({"detail": "Video removed."}, status=status.HTTP_200_OK)


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
                }
            )

        videos = profile.videos.filter(
            competition=competition,
            is_active=True,
            is_competition_eligible=True,
        )
        totals = videos.aggregate(
            views=Sum("views"),
            likes=Sum("likes"),
            comments=Sum("scored_comments"),
            shares=Sum("shares"),
            brand_mention_comments=Sum("brand_mention_comments"),
            last_synced_at=Max("last_synced_at"),
        )
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
        rank = None
        if competition is not None:
            ensure_default_criteria(competition)
            for entry in build_leaderboard(competition):
                if entry["candidate_id"] == profile.id:
                    rank = entry["rank"]
                    break
        return Response(build_candidate_analytics(profile, competition, rank=rank))


class CompetitionCriterionListCreateView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get_competition(self, organization: Organization) -> Competition:
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            competition = Competition.objects.create(organization=organization)
        ensure_default_criteria(competition)
        return competition

    def get(self, request):
        organization = self.get_organization()
        competition = self.get_competition(organization)
        criteria = competition.criteria.order_by("sort_order", "id")
        return Response(CompetitionCriterionSerializer(criteria, many=True).data)

    def post(self, request):
        organization = self.get_organization()
        competition = self.get_competition(organization)
        serializer = CompetitionCriterionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        criterion = serializer.save(competition=competition)
        return Response(
            CompetitionCriterionSerializer(criterion).data,
            status=status.HTTP_201_CREATED,
        )


class CompetitionCriterionDetailView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get_object(self, organization: Organization, pk: int) -> CompetitionCriterion:
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            raise Competition.DoesNotExist
        return get_object_or_404(CompetitionCriterion, competition=competition, pk=pk)

    def patch(self, request, pk: int):
        organization = self.get_organization()
        criterion = self.get_object(organization, pk)
        serializer = CompetitionCriterionSerializer(
            criterion,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk: int):
        organization = self.get_organization()
        criterion = self.get_object(organization, pk)
        criterion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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


class AdminCompetitionStandingsView(TenantViewMixin, APIView):
    permission_classes = [IsAuthenticated, IsOrgAdmin]

    def get(self, request):
        organization = self.get_organization()
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return Response(
                {"detail": "Competition not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        standings = build_competition_standings(competition)
        last_updated = max(
            (
                entry["last_synced_at"]
                for entry in standings["candidates"]
                if entry.get("last_synced_at")
            ),
            default=timezone.now(),
        )
        return Response(
            {
                "organization": OrganizationSerializer(organization).data,
                "competition": PublicCompetitionSerializer(competition).data,
                "standings": standings,
                "last_updated_at": last_updated,
            }
        )


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

        payload = build_leaderboard_response(organization, competition)
        return Response(payload)


class PublicLeaderboardView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, org_slug):
        organization = get_object_or_404(
            Organization,
            slug=org_slug,
            status=Organization.Status.ACTIVE,
        )
        competition = organization.competitions.order_by("-created_at").first()
        if competition is None:
            return Response(
                {"detail": "Competition not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = build_leaderboard_response(organization, competition, use_cache=True)
        response = Response(payload)
        if payload.get("leaderboard_available"):
            response["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
        return response


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
