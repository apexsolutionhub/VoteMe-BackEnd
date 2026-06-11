from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from competitions.models import CompetitionVideo, TikTokConnection
from competitions.tiktok import client

logger = logging.getLogger(__name__)

OAUTH_STATE_CACHE_PREFIX = "tiktok_oauth_state:"
OAUTH_STATE_TTL = 600


def build_oauth_state(candidate_profile_id: int, code_verifier: str | None = None) -> str:
    state = secrets.token_urlsafe(32)
    cache.set(
        f"{OAUTH_STATE_CACHE_PREFIX}{state}",
        {"profile_id": candidate_profile_id, "cv": code_verifier or ""},
        timeout=OAUTH_STATE_TTL,
    )
    return state


def load_oauth_state(state: str) -> tuple[int, str | None]:
    cache_key = f"{OAUTH_STATE_CACHE_PREFIX}{state}"
    payload = cache.get(cache_key)
    if not payload:
        raise ValueError("OAuth state expired or invalid.")
    cache.delete(cache_key)
    code_verifier = payload.get("cv") or None
    if client.uses_pkce() and not code_verifier:
        raise ValueError("Missing PKCE verifier for desktop OAuth.")
    return int(payload["profile_id"]), code_verifier


def ensure_fresh_access_token(connection: TikTokConnection) -> str:
    if (
        connection.access_token_expires_at
        and connection.access_token_expires_at > timezone.now() + timedelta(minutes=2)
    ):
        return connection.access_token

    if not connection.refresh_token:
        raise ValueError("TikTok refresh token missing; reconnect the account.")

    token_response = client.refresh_access_token(connection.refresh_token)
    token_data = token_response.get("data", token_response)
    connection.access_token = token_data["access_token"]
    connection.refresh_token = token_data.get("refresh_token") or connection.refresh_token
    connection.access_token_expires_at = client.token_expiry_from_response(
        token_data, "expires_in"
    )
    connection.refresh_token_expires_at = client.token_expiry_from_response(
        token_data, "refresh_expires_in"
    )
    connection.save(
        update_fields=[
            "access_token",
            "refresh_token",
            "access_token_expires_at",
            "refresh_token_expires_at",
        ]
    )
    return connection.access_token


def save_connection(profile, token_response: dict) -> TikTokConnection:
    token_data = token_response.get("data", token_response)
    connection, _created = TikTokConnection.objects.update_or_create(
        candidate_profile=profile,
        defaults={
            "open_id": token_data.get("open_id", ""),
            "access_token": token_data.get("access_token", ""),
            "refresh_token": token_data.get("refresh_token", ""),
            "scope": token_data.get("scope", ""),
            "access_token_expires_at": client.token_expiry_from_response(
                token_data, "expires_in"
            ),
            "refresh_token_expires_at": client.token_expiry_from_response(
                token_data, "refresh_expires_in"
            ),
            "connected_at": timezone.now(),
        },
    )
    return connection


def sync_video_from_tiktok(
    video: CompetitionVideo,
    connection: TikTokConnection,
) -> bool:
    video_id = video.platform_video_id
    if not video_id:
        return False

    try:
        access_token = ensure_fresh_access_token(connection)
        metrics_map = client.query_video_metrics(access_token, [video_id])
    except Exception:
        logger.exception("TikTok sync failed for video %s", video.pk)
        return False

    metrics = metrics_map.get(video_id)
    if not metrics:
        return False

    video.views = metrics["views"]
    video.likes = metrics["likes"]
    video.comments = metrics["comments"]
    video.shares = metrics["shares"]
    video.save(update_fields=["views", "likes", "comments", "shares", "updated_at"])
    return True
