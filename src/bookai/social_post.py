"""Cross-platform auto-post via Upload-Post API.

Supports posting generated videos to:
- TikTok
- Instagram Reels
- YouTube Shorts
- Facebook Reels

Uses the Upload-Post service (https://docs.upload-post.com).
Also provides a generic webhook poster for custom integrations.

Usage::

    from bookai.social_post import cross_post_video, SocialPostConfig

    cfg = SocialPostConfig(
        api_key="your-key",
        username="your-username",
        platforms=["tiktok", "instagram"],
    )
    result = cross_post_video(
        video_path="output/video.mp4",
        title="5 Cuốn Sách Hay Nhất 2024 📚",
        config=cfg,
    )
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Config
# ---------------------------------------------------------------------------

class SocialPlatform(str, Enum):
    """Supported social platforms."""
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"

    @classmethod
    def all(cls) -> list[str]:
        return [p.value for p in cls]


class PrivacyLevel(str, Enum):
    """Video privacy levels."""
    PUBLIC = "PUBLIC_TO_EVERYONE"
    FRIENDS = "MUTUAL_FOLLOW_FRIENDS"
    PRIVATE = "SELF_ONLY"


@dataclass
class SocialPostConfig:
    """Configuration for social posting."""
    # Upload-Post credentials
    api_key: str = ""
    username: str = ""
    enabled: bool = True

    # Default platforms
    platforms: list[str] = field(default_factory=lambda: ["tiktok", "instagram"])

    # YouTube-specific
    youtube_privacy: str = "public"  # public, unlisted, private
    youtube_ai_content_flag: bool = True  # Flag as AI-generated

    # Auto-post after video generation
    auto_upload: bool = False

    # Webhook for custom integrations
    webhook_url: str = ""
    webhook_headers: dict[str, str] = field(default_factory=dict)

    # API settings
    api_base: str = "https://api.upload-post.com"
    timeout: int = 300  # Upload timeout in seconds

    @classmethod
    def from_env(cls) -> SocialPostConfig:
        """Create config from environment variables."""
        return cls(
            api_key=os.getenv("UPLOAD_POST_API_KEY", ""),
            username=os.getenv("UPLOAD_POST_USERNAME", ""),
            enabled=os.getenv("UPLOAD_POST_ENABLED", "false").lower() == "true",
            platforms=os.getenv("UPLOAD_POST_PLATFORMS", "tiktok,instagram").split(","),
            youtube_privacy=os.getenv("UPLOAD_POST_YT_PRIVACY", "public"),
            auto_upload=os.getenv("UPLOAD_POST_AUTO_UPLOAD", "false").lower() == "true",
            webhook_url=os.getenv("BOOKAI_WEBHOOK_URL", ""),
        )

    @classmethod
    def from_dict(cls, d: dict) -> SocialPostConfig:
        """Create config from a dictionary (e.g., TOML section)."""
        return cls(
            api_key=d.get("upload_post_api_key", ""),
            username=d.get("upload_post_username", ""),
            enabled=d.get("upload_post_enabled", False),
            platforms=d.get("upload_post_platforms", ["tiktok", "instagram"]),
            youtube_privacy=d.get("upload_post_youtube_privacy_status", "public"),
            youtube_ai_content_flag=d.get("youtube_ai_content_flag", True),
            auto_upload=d.get("upload_post_auto_upload", False),
            webhook_url=d.get("webhook_url", ""),
            api_base=d.get("upload_post_api_base", "https://api.upload-post.com"),
            timeout=d.get("upload_post_timeout", 300),
        )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PostResult:
    """Result of a social post operation."""
    ok: bool = False
    request_id: str = ""
    platforms: list[str] = field(default_factory=list)
    message: str = ""
    error: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "request_id": self.request_id,
            "platforms": self.platforms,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class YouTubeExtra:
    """YouTube-specific upload parameters."""
    title: str = ""  # Max 100 chars
    description: str = ""
    tags: list[str] = field(default_factory=list)
    privacy_status: str = "public"  # public, unlisted, private
    contains_synthetic_media: bool = True  # AI-generated content flag


# ---------------------------------------------------------------------------
# Core upload function
# ---------------------------------------------------------------------------

def upload_video(
    video_path: str,
    title: str,
    config: Optional[SocialPostConfig] = None,
    platforms: Optional[list[str]] = None,
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    youtube_extra: Optional[YouTubeExtra] = None,
) -> PostResult:
    """Upload a video to social platforms via Upload-Post API.

    Args:
        video_path: Path to the video file
        title: Video title/caption (max 2200 chars)
        config: Social post configuration
        platforms: Override default platforms
        privacy_level: Privacy level for the post
        youtube_extra: YouTube-specific parameters

    Returns:
        PostResult with upload status
    """
    cfg = config or SocialPostConfig.from_env()

    if not cfg.api_key or not cfg.username:
        return PostResult(
            ok=False,
            error="Upload-Post API key and username not configured",
        )

    if not cfg.enabled:
        return PostResult(ok=False, error="Upload-Post is disabled")

    vpath = Path(video_path)
    if not vpath.exists():
        return PostResult(ok=False, error=f"Video file not found: {video_path}")

    if not vpath.suffix.lower() in (".mp4", ".mov", ".avi", ".webm"):
        return PostResult(ok=False, error=f"Unsupported video format: {vpath.suffix}")

    target_platforms = platforms or cfg.platforms
    if not target_platforms:
        return PostResult(ok=False, error="No platforms specified")

    logger.info(f"Cross-posting to {', '.join(target_platforms)} via Upload-Post...")

    try:
        with open(video_path, "rb") as video_file:
            files = {"video": (vpath.name, video_file, "video/mp4")}

            data: list[tuple[str, str]] = [
                ("user", cfg.username),
                ("title", title[:2200]),
                ("privacy_level", privacy_level),
            ]

            for platform in target_platforms:
                data.append(("platform[]", platform))

            # YouTube-specific fields
            if youtube_extra and any(p.startswith("youtube") for p in target_platforms):
                if youtube_extra.title:
                    data.append(("youtube_title", youtube_extra.title[:100]))
                if youtube_extra.description:
                    data.append(("youtube_description", youtube_extra.description))
                for tag in youtube_extra.tags:
                    data.append(("tags[]", tag))
                data.append(("privacyStatus", youtube_extra.privacy_status))
                if youtube_extra.contains_synthetic_media:
                    data.append(("containsSyntheticMedia", "true"))
            elif any(p.startswith("youtube") for p in target_platforms):
                # Auto-flag AI content for YouTube
                if cfg.youtube_ai_content_flag:
                    data.append(("containsSyntheticMedia", "true"))
                data.append(("privacyStatus", cfg.youtube_privacy))

            headers = {"Authorization": f"Apikey {cfg.api_key}"}

            response = requests.post(
                f"{cfg.api_base}/api/upload",
                headers=headers,
                data=data,
                files=files,
                timeout=cfg.timeout,
            )

            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                logger.info(
                    f"✅ Video cross-posted! Request ID: {result.get('request_id')}"
                )
                return PostResult(
                    ok=True,
                    request_id=result.get("request_id", ""),
                    platforms=target_platforms,
                    message="Video cross-posted successfully",
                    raw_response=result,
                )
            else:
                msg = result.get("message", "Unknown error")
                logger.warning(f"Cross-post failed: {msg}")
                return PostResult(ok=False, error=msg, raw_response=result)

    except requests.exceptions.Timeout:
        return PostResult(ok=False, error="Upload timed out")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to cross-post video: {e}")
        return PostResult(ok=False, error=str(e))


def check_upload_status(
    request_id: str,
    config: Optional[SocialPostConfig] = None,
) -> dict:
    """Check the status of an upload request.

    Args:
        request_id: The request ID from upload
        config: Social post configuration

    Returns:
        dict with status information
    """
    cfg = config or SocialPostConfig.from_env()

    try:
        headers = {"Authorization": f"Apikey {cfg.api_key}"}
        response = requests.get(
            f"{cfg.api_base}/api/uploadposts/status",
            params={"request_id": request_id},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to check status: {e}")
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Webhook poster
# ---------------------------------------------------------------------------

def post_webhook(
    video_path: str,
    metadata: dict,
    config: Optional[SocialPostConfig] = None,
) -> PostResult:
    """Post video info to a custom webhook (Zapier, n8n, Make, etc.).

    Args:
        video_path: Path to the video file
        metadata: Video metadata dict (title, description, tags, etc.)
        config: Configuration with webhook_url

    Returns:
        PostResult
    """
    cfg = config or SocialPostConfig.from_env()

    if not cfg.webhook_url:
        return PostResult(ok=False, error="No webhook URL configured")

    payload = {
        "video_path": str(video_path),
        "video_exists": Path(video_path).exists(),
        "video_size_mb": round(Path(video_path).stat().st_size / 1024 / 1024, 2)
        if Path(video_path).exists()
        else 0,
        **metadata,
    }

    try:
        headers = {"Content-Type": "application/json"}
        headers.update(cfg.webhook_headers)

        response = requests.post(
            cfg.webhook_url,
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        return PostResult(
            ok=True,
            message=f"Webhook posted to {cfg.webhook_url}",
            raw_response={"status_code": response.status_code},
        )
    except requests.exceptions.RequestException as e:
        return PostResult(ok=False, error=str(e))


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def cross_post_video(
    video_path: str,
    title: str,
    config: Optional[SocialPostConfig] = None,
    platforms: Optional[list[str]] = None,
    youtube_extra: Optional[YouTubeExtra] = None,
) -> PostResult:
    """Convenience function to cross-post a video.

    This is the main entry point for auto-posting.
    """
    return upload_video(
        video_path=video_path,
        title=title,
        config=config,
        platforms=platforms,
        youtube_extra=youtube_extra,
    )
