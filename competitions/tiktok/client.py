from __future__ import annotations

import hashlib
import logging
import secrets
import string
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/video/query/"
TIKTOK_RESEARCH_COMMENT_URL = (
    "https://open.tiktokapis.com/v2/research/video/comment/list/"
)

PKCE_VERIFIER_CHARS = string.ascii_letters + string.digits + "-._~"


def is_tiktok_configured() -> bool:
    return bool(settings.TIKTOK_CLIENT_KEY and settings.TIKTOK_CLIENT_SECRET)


def uses_pkce() -> bool:
    return getattr(settings, "TIKTOK_LOGIN_KIT", "desktop") == "desktop"


def tiktok_setup_hints() -> list[str]:
    redirect_uri = settings.TIKTOK_REDIRECT_URI
    login_kit = getattr(settings, "TIKTOK_LOGIN_KIT", "desktop")
    hints = [
        f"Login Kit mode: {login_kit} (set TIKTOK_LOGIN_KIT=desktop|web to override).",
        f"Redirect URI must match the developer portal exactly: {redirect_uri}",
    ]
    if login_kit == "desktop":
        hints.append(
            "Enable the Desktop Login Kit product and register the redirect URI there "
            "(http://localhost is only allowed for Desktop, not Web)."
        )
    else:
        hints.append(
            "Web Login Kit requires an https:// redirect URI (use ngrok or similar for local dev)."
        )
    return hints


def generate_pkce_pair() -> tuple[str, str]:
    """Desktop Login Kit: hex-encoded SHA256 challenge (not standard base64url)."""
    code_verifier = "".join(
        secrets.choice(PKCE_VERIFIER_CHARS) for _ in range(64)
    )
    code_challenge = hashlib.sha256(code_verifier.encode("utf-8")).hexdigest()
    return code_verifier, code_challenge


def build_authorize_url(state: str, code_challenge: str | None = None) -> str:
    params: dict[str, str] = {
        "client_key": settings.TIKTOK_CLIENT_KEY,
        "scope": settings.TIKTOK_SCOPES,
        "response_type": "code",
        "redirect_uri": settings.TIKTOK_REDIRECT_URI,
        "state": state,
    }
    if uses_pkce():
        if not code_challenge:
            raise ValueError("Desktop Login Kit requires a PKCE code_challenge.")
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return f"{TIKTOK_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(
    code: str,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, str] = {
        "client_key": settings.TIKTOK_CLIENT_KEY,
        "client_secret": settings.TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.TIKTOK_REDIRECT_URI,
    }
    if uses_pkce():
        if not code_verifier:
            raise ValueError("Desktop Login Kit requires code_verifier on token exchange.")
        payload["code_verifier"] = code_verifier
    return _post_token(payload)


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    payload = {
        "client_key": settings.TIKTOK_CLIENT_KEY,
        "client_secret": settings.TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    return _post_token(payload)


def _post_token(payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            TIKTOK_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=payload,
        )
        response.raise_for_status()
        body = response.json()
        if body.get("error", {}).get("code") not in (None, "ok"):
            raise ValueError(body.get("error", {}).get("message", "TikTok token error"))
        return body


def token_expiry_from_response(token_data: dict[str, Any], field: str) -> timezone.datetime | None:
    expires_in = token_data.get(field)
    if not expires_in:
        return None
    try:
        return timezone.now() + timedelta(seconds=int(expires_in))
    except (TypeError, ValueError):
        return None


def query_video_metrics(access_token: str, video_ids: list[str]) -> dict[str, dict[str, int]]:
    if not video_ids:
        return {}

    fields = "id,view_count,like_count,comment_count,share_count"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {"filters": {"video_ids": video_ids[:20]}}

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{TIKTOK_VIDEO_QUERY_URL}?fields={fields}",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        body = response.json()

    if body.get("error", {}).get("code") not in (None, "ok"):
        raise ValueError(body.get("error", {}).get("message", "TikTok video query failed"))

    metrics: dict[str, dict[str, int]] = {}
    for item in body.get("data", {}).get("videos", []):
        video_id = str(item.get("id", ""))
        if not video_id:
            continue
        metrics[video_id] = {
            "views": int(item.get("view_count") or 0),
            "likes": int(item.get("like_count") or 0),
            "comments": int(item.get("comment_count") or 0),
            "shares": int(item.get("share_count") or 0),
        }
    return metrics


def fetch_research_comments(video_id: str, access_token: str) -> list[dict[str, Any]]:
    """Optional Research API comment fetch when academic credentials are configured."""
    if not settings.TIKTOK_RESEARCH_CLIENT_KEY:
        return []

    fields = "id,text,create_time"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    comments: list[dict[str, Any]] = []
    cursor = 0

    with httpx.Client(timeout=30.0) as client:
        while True:
            response = client.post(
                f"{TIKTOK_RESEARCH_COMMENT_URL}?fields={fields}",
                headers=headers,
                json={
                    "video_id": int(video_id) if video_id.isdigit() else video_id,
                    "max_count": 100,
                    "cursor": cursor,
                },
            )
            if response.status_code >= 400:
                logger.warning("TikTok research comment fetch failed: %s", response.text)
                break

            body = response.json()
            batch = body.get("data", {}).get("comments", [])
            comments.extend(batch)
            if not body.get("data", {}).get("has_more"):
                break
            cursor = body.get("data", {}).get("cursor", 0)

    return comments
