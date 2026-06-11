from django.urls import path

from .tiktok_views import (
    TikTokCallbackView,
    TikTokConnectView,
    TikTokDisconnectView,
    TikTokStatusView,
)
from .views import (
    CandidateAnalyticsView,
    CandidateMeProfileView,
    CandidateStatsView,
    CandidateVideoDetailView,
    CandidateVideoListCreateView,
    CompetitionStatusView,
    OrgCandidateDetailView,
    OrgCandidateListCreateView,
    OrganizationCompetitionView,
    OrganizationMeView,
    PublicCompetitionView,
    PublicLeaderboardView,
    SyncCompetitionView,
    AdminLeaderboardView,
)

urlpatterns = [
    path("organizations/me/", OrganizationMeView.as_view(), name="organization-me"),
    path(
        "organizations/competition/",
        OrganizationCompetitionView.as_view(),
        name="organization-competition",
    ),
    path(
        "organizations/competition/status/",
        CompetitionStatusView.as_view(),
        name="competition-status",
    ),
    path(
        "organizations/competition/sync/",
        SyncCompetitionView.as_view(),
        name="competition-sync",
    ),
    path(
        "organizations/leaderboard/",
        AdminLeaderboardView.as_view(),
        name="organization-leaderboard",
    ),
    path(
        "organizations/candidates/",
        OrgCandidateListCreateView.as_view(),
        name="org-candidates",
    ),
    path(
        "organizations/candidates/<int:pk>/",
        OrgCandidateDetailView.as_view(),
        name="org-candidate-detail",
    ),
    path("candidate/me/profile/", CandidateMeProfileView.as_view(), name="candidate-profile"),
    path("candidate/me/stats/", CandidateStatsView.as_view(), name="candidate-stats"),
    path(
        "candidate/me/analytics/",
        CandidateAnalyticsView.as_view(),
        name="candidate-analytics",
    ),
    path(
        "candidate/me/videos/",
        CandidateVideoListCreateView.as_view(),
        name="candidate-videos",
    ),
    path(
        "candidate/me/videos/<int:pk>/",
        CandidateVideoDetailView.as_view(),
        name="candidate-video-detail",
    ),
    path("tiktok/connect/", TikTokConnectView.as_view(), name="tiktok-connect"),
    path("tiktok/callback/", TikTokCallbackView.as_view(), name="tiktok-callback"),
    path("tiktok/status/", TikTokStatusView.as_view(), name="tiktok-status"),
    path("tiktok/disconnect/", TikTokDisconnectView.as_view(), name="tiktok-disconnect"),
    path(
        "public/<slug:org_slug>/competition/",
        PublicCompetitionView.as_view(),
        name="public-competition",
    ),
    path(
        "public/<slug:org_slug>/leaderboard/",
        PublicLeaderboardView.as_view(),
        name="public-leaderboard",
    ),
]
