from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from accounts.permissions import IsAdmin
from accounts.serializers import (
    ChangePasswordSerializer,
    LegacyCreateCandidateSerializer,
    LoginSerializer,
    ProfileUpdateSerializer,
    UserSerializer,
)
from accounts.tokens import tokens_for_membership
from organizations.mixins import resolve_membership
from organizations.serializers import (
    OrganizationSerializer,
    SignupSerializer,
)


def _user_with_org(user, organization, membership) -> dict:
    data = UserSerializer(user).data
    data["organization"] = {
        "id": str(organization.id),
        "name": organization.name,
        "slug": organization.slug,
        "org_code": organization.org_code,
        "membership_role": membership.role,
    }
    return data


class SignupStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"enabled": bool(settings.SIGNUP_SECRET_CODE)})


class SignupView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.SIGNUP_SECRET_CODE:
            return Response(
                {
                    "detail": (
                        "Registration is not available yet. "
                        "Contact voteMe to set up your competition workspace."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        tokens = tokens_for_membership(result["user"], result["membership"])

        return Response(
            {
                **tokens,
                "organization": OrganizationSerializer(result["organization"]).data,
                "user": _user_with_org(
                    result["user"],
                    result["organization"],
                    result["membership"],
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        organization = serializer.validated_data["organization"]
        membership = serializer.validated_data["membership"]
        tokens = tokens_for_membership(user, membership)

        return Response(
            {
                **tokens,
                "user": _user_with_org(user, organization, membership),
            }
        )


class MeView(APIView):
    def get(self, request):
        organization, membership = resolve_membership(
            request.user,
            request.auth.get("organization_slug") if request.auth else None,
        )
        return Response(_user_with_org(request.user, organization, membership))

    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        organization, membership = resolve_membership(
            request.user,
            request.auth.get("organization_slug") if request.auth else None,
        )
        return Response(_user_with_org(user, organization, membership))


class ChangePasswordView(APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        organization, membership = resolve_membership(
            request.user,
            request.auth.get("organization_slug") if request.auth else None,
        )
        return Response(
            {
                "detail": "Password updated successfully.",
                "user": _user_with_org(user, organization, membership),
            }
        )


class CandidateListCreateView(generics.ListCreateAPIView):
    """Legacy global endpoint — prefer org-scoped /organizations/candidates/."""

    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = LegacyCreateCandidateSerializer

    def get_queryset(self):
        return User.objects.filter(role=User.Role.CANDIDATE).order_by("-date_joined")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        return Response(UserSerializer(queryset, many=True).data)


class CandidateDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def delete(self, request, pk):
        candidate = get_object_or_404(User, pk=pk, role=User.Role.CANDIDATE)
        username = candidate.username
        candidate.delete()
        return Response(
            {"detail": f"Candidate account '{username}' has been deleted."},
            status=status.HTTP_200_OK,
        )


class RefreshTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
            access = str(refresh.access_token)
        except Exception:
            return Response(
                {"detail": "Invalid or expired refresh token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response({"access": access})
