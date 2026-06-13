from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone as dt_timezone
from typing import TypedDict

import httpx

from django.utils import timezone

from competitions.tiktok.url_resolve import BROWSER_HEADERS, resolve_tiktok_video_url

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 10
OVERALL_TIMEOUT_SECONDS = 12


class TikTokMetrics(TypedDict, total=False):
    views: int
    likes: int
    comments: int
    shares: int
    canonical_url: str
    title: str
    platform_published_at: datetime


def _aware_datetime(value: datetime) -> datetime:
    if timezone.is_aware(value):
        return value
    return timezone.make_aware(value, dt_timezone.utc)


def _published_at_from_unix(timestamp: int | float | str | None) -> datetime | None:
    if timestamp is None:
        return None
    try:
        return _aware_datetime(datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc))
    except (TypeError, ValueError, OSError):
        return None


def _published_at_from_upload_date(upload_date: str | None) -> datetime | None:
    if not upload_date or len(upload_date) != 8:
        return None
    try:
        naive = datetime.strptime(upload_date, "%Y%m%d")
        return _aware_datetime(naive.replace(tzinfo=dt_timezone.utc))
    except ValueError:
        return None


def _published_at_from_item(item: dict) -> datetime | None:
    for key in ("createTime", "create_time", "publish_time"):
        published = _published_at_from_unix(item.get(key))
        if published:
            return published
    return None


def _normalize_title(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = " ".join(str(raw).split())
    return cleaned[:500]


def _metrics_from_item(item: dict) -> TikTokMetrics | None:
    stats = item.get("stats") or item.get("statsV2") or {}
    parsed = _stats_from_mapping(stats)
    if not parsed:
        return None
    title = _normalize_title(item.get("desc") or item.get("title"))
    if title:
        parsed["title"] = title
    published = _published_at_from_item(item)
    if published:
        parsed["platform_published_at"] = published
    return parsed


def _stats_from_mapping(data: dict) -> TikTokMetrics | None:
    views = data.get("playCount") or data.get("play_count") or data.get("view_count")
    if views is None:
        return None
    return {
        "views": int(views),
        "likes": int(data.get("diggCount") or data.get("like_count") or 0),
        "comments": int(data.get("commentCount") or data.get("comment_count") or 0),
        "shares": int(
            data.get("shareCount") or data.get("repost_count") or data.get("share_count") or 0
        ),
    }


def _parse_stats_from_html(html: str) -> TikTokMetrics | None:
    sigi = re.search(
        r'<script id="SIGI_STATE"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if sigi:
        try:
            payload = json.loads(sigi.group(1))
            item_module = payload.get("ItemModule") or {}
            if item_module:
                item = next(iter(item_module.values()))
                parsed = _metrics_from_item(item)
                if parsed:
                    return parsed
        except (json.JSONDecodeError, StopIteration, ValueError):
            pass

    universal = re.search(
        r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if universal:
        try:
            payload = json.loads(universal.group(1))
            detail = (
                payload.get("__DEFAULT_SCOPE__", {})
                .get("webapp.video-detail", {})
                .get("itemInfo", {})
                .get("itemStruct", {})
            )
            parsed = _metrics_from_item(detail)
            if parsed:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    stats_match = re.search(
        r'"stats"\s*:\s*\{[^}]*"playCount"\s*:\s*(\d+)[^}]*"diggCount"\s*:\s*(\d+)'
        r'[^}]*"commentCount"\s*:\s*(\d+)[^}]*"shareCount"\s*:\s*(\d+)',
        html,
    )
    if stats_match:
        return {
            "views": int(stats_match.group(1)),
            "likes": int(stats_match.group(2)),
            "comments": int(stats_match.group(3)),
            "shares": int(stats_match.group(4)),
        }

    def grab(field: str) -> int | None:
        match = re.search(rf'"{field}"\s*:\s*(\d+)', html)
        return int(match.group(1)) if match else None

    views = grab("playCount")
    if views is None:
        return None

    return {
        "views": views,
        "likes": grab("diggCount") or 0,
        "comments": grab("commentCount") or 0,
        "shares": grab("shareCount") or 0,
    }


def _fetch_html(video_url: str) -> str | None:
    try:
        from curl_cffi import requests as cffi_requests

        response = cffi_requests.get(
            video_url,
            impersonate="chrome131",
            timeout=FETCH_TIMEOUT_SECONDS,
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        if response.status_code == 200 and len(response.text) > 5000:
            return response.text
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("curl_cffi fetch failed for %s: %s", video_url, exc)

    try:
        with httpx.Client(timeout=float(FETCH_TIMEOUT_SECONDS), follow_redirects=True) as http:
            response = http.get(
                video_url,
                headers={
                    **BROWSER_HEADERS,
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )
            response.raise_for_status()
            if len(response.text) > 5000:
                return response.text
    except Exception as exc:
        logger.debug("HTTP fetch failed for %s: %s", video_url, exc)

    return None


def _fetch_via_ytdlp(video_url: str) -> TikTokMetrics | None:
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        return None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "socket_timeout": FETCH_TIMEOUT_SECONDS,
        "retries": 1,
        "nocheckcertificate": True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception as exc:
        logger.debug("yt-dlp metrics failed for %s: %s", video_url, exc)
        return None

    views = info.get("view_count")
    if views is None:
        return None

    metrics: TikTokMetrics = {
        "views": int(views),
        "likes": int(info.get("like_count") or 0),
        "comments": int(info.get("comment_count") or 0),
        "shares": int(info.get("repost_count") or 0),
    }
    title = _normalize_title(info.get("title") or info.get("description"))
    if title:
        metrics["title"] = title
    published = _published_at_from_unix(info.get("timestamp"))
    if published is None:
        published = _published_at_from_upload_date(info.get("upload_date"))
    if published:
        metrics["platform_published_at"] = published
    canonical_url = info.get("webpage_url") or info.get("original_url")
    if canonical_url:
        metrics["canonical_url"] = resolve_tiktok_video_url(canonical_url)
    return metrics


def _fetch_via_page_html(video_url: str, *, canonical_url: str) -> TikTokMetrics | None:
    html = _fetch_html(video_url)
    if not html:
        return None
    parsed = _parse_stats_from_html(html)
    if parsed:
        parsed["canonical_url"] = canonical_url
    return parsed


def fetch_public_tiktok_metrics(video_url: str) -> TikTokMetrics | None:
    """Best-effort public stats — parallel strategies with a hard time budget."""
    resolved_url = resolve_tiktok_video_url(video_url)

    strategies = (
        lambda: _fetch_via_page_html(resolved_url, canonical_url=resolved_url),
        lambda: _fetch_via_ytdlp(resolved_url),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(strategy) for strategy in strategies]
        try:
            for future in as_completed(futures, timeout=OVERALL_TIMEOUT_SECONDS):
                try:
                    result = future.result()
                except Exception as exc:
                    logger.debug("TikTok metrics strategy failed: %s", exc)
                    continue
                if result:
                    result.setdefault("canonical_url", resolved_url)
                    for pending in futures:
                        pending.cancel()
                    return result
        except TimeoutError:
            logger.warning(
                "TikTok metrics timed out after %ss for %s",
                OVERALL_TIMEOUT_SECONDS,
                resolved_url,
            )

    return None
