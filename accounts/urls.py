from django.urls import path

from .views import (
    CandidateDetailView,
    CandidateListCreateView,
    ChangePasswordView,
    LoginView,
    MeView,
    RefreshTokenView,
    SignupStatusView,
    SignupView,
)

urlpatterns = [
    path("auth/signup/status/", SignupStatusView.as_view(), name="signup-status"),
    path("auth/signup/", SignupView.as_view(), name="signup"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshTokenView.as_view(), name="token-refresh"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("admin/candidates/", CandidateListCreateView.as_view(), name="candidates"),
    path(
        "admin/candidates/<int:pk>/",
        CandidateDetailView.as_view(),
        name="candidate-detail",
    ),
]
