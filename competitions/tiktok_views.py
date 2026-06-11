from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from competitions.models import CandidateProfile, TikTokConnection
from competitions.tiktok import client
from competitions.tiktok.service import (
    build_oauth_state,
    load_oauth_state,
    save_connection,
)
from organizations.mixins import TenantViewMixin
from organizations.permissions import IsOrgCandidate


class TikTokConnectView(TenantViewMixin, APIView):
    permission_classes = [IsOrgCandidate]

    def get(self, request):
        if not client.is_tiktok_configured():
            return Response(
                {"detail": "TikTok integration is not configured on the server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        profile = get_object_or_404(
            CandidateProfile,
            user=request.user,
            organization=self.get_organization(),
        )
        code_challenge = None
        code_verifier = None
        if client.uses_pkce():
            code_verifier, code_challenge = client.generate_pkce_pair()
        state = build_oauth_state(profile.id, code_verifier)
        return Response(
            {
                "authorize_url": client.build_authorize_url(state, code_challenge),
                "login_kit": "desktop" if client.uses_pkce() else "web",
                "redirect_uri": settings.TIKTOK_REDIRECT_URI,
                "setup_hints": client.tiktok_setup_hints(),
            }
        )


class TikTokCallbackView(TenantViewMixin, APIView):
    permission_classes = [IsOrgCandidate]

    def post(self, request):
        code = request.data.get("code")
        state = request.data.get("state")
        if not code or not state:
            return Response(
                {"detail": "Missing OAuth code or state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            profile_id, code_verifier = load_oauth_state(state)
        except Exception:
            return Response(
                {"detail": "Invalid or expired OAuth state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile = get_object_or_404(
            CandidateProfile,
            pk=profile_id,
            user=request.user,
            organization=self.get_organization(),
        )

        token_response = client.exchange_code_for_tokens(code, code_verifier)
        connection = save_connection(profile, token_response)
        return Response(
            {
                "detail": "TikTok account connected.",
                "connected": True,
                "open_id": connection.open_id,
            }
        )


class TikTokStatusView(TenantViewMixin, APIView):
    permission_classes = [IsOrgCandidate]

    def get(self, request):
        profile = get_object_or_404(
            CandidateProfile,
            user=request.user,
            organization=self.get_organization(),
        )
        connection = TikTokConnection.objects.filter(candidate_profile=profile).first()
        if not connection:
            return Response(
                {
                    "connected": False,
                    "configured": client.is_tiktok_configured(),
                }
            )

        return Response(
            {
                "connected": bool(connection.access_token),
                "configured": client.is_tiktok_configured(),
                "open_id": connection.open_id,
                "connected_at": connection.connected_at,
                "access_token_expires_at": connection.access_token_expires_at,
            }
        )


class TikTokDisconnectView(TenantViewMixin, APIView):
    permission_classes = [IsOrgCandidate]

    def delete(self, request):
        profile = get_object_or_404(
            CandidateProfile,
            user=request.user,
            organization=self.get_organization(),
        )
        TikTokConnection.objects.filter(candidate_profile=profile).delete()
        return Response({"detail": "TikTok disconnected."})
