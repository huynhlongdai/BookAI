"""Stock video material search and download for BookAI.

Downloads free HD video clips from Pexels, Pixabay, and Coverr to use as
B-roll footage in book-based videos. Search terms come from BookAI's
storyboard visual prompts (already in English).

Inspired by MoneyPrinterTurbo material.py.

Usage::

    from bookai.stock_video import search_and_download, StockVideoConfig

    cfg = StockVideoConfig(provider="pexels", pexels_api_key="...")
    materials = search_and_download(
        search_terms=["reading book", "sunrise motivation"],
        video_aspect="9:16",
        output_dir="output/materials",
        config=cfg,
    )
"""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class MaterialInfo:
    """Metadata for a downloaded video material."""

    provider: str = "pexels"
    url: str = ""
    local_path: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    search_term: str = ""


@dataclass
class StockVideoConfig:
    """Configuration for stock video search and download."""

    provider: str = "pexels"          # pexels, pixabay, coverr
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    coverr_api_key: str = ""
    min_duration: int = 3             # minimum clip duration in seconds
    max_results_per_term: int = 5
    cache_dir: str = "resource/stock_cache"
    proxy: dict = field(default_factory=dict)  # {"http": "...", "https": "..."}
    timeout: tuple = (15, 60)


# ---------------------------------------------------------------------------
# Retry session
# ---------------------------------------------------------------------------


def _get_session(proxy: dict | None = None) -> requests.Session:
    """Create a requests session with retry logic."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if proxy:
        session.proxies.update(proxy)
    return session


# ---------------------------------------------------------------------------
# Pexels
# ---------------------------------------------------------------------------


def search_pexels(
    search_term: str,
    video_aspect: str = "9:16",
    config: StockVideoConfig | None = None,
) -> list[MaterialInfo]:
    """Search Pexels for stock video clips.

    Requires ``config.pexels_api_key`` (free at https://www.pexels.com/api/).
    """
    cfg = config or StockVideoConfig()
    if not cfg.pexels_api_key:
        return []

    orientation_map = {"9:16": "portrait", "16:9": "landscape", "1:1": "square"}
    orientation = orientation_map.get(video_aspect, "portrait")

    w_map = {"9:16": 1080, "16:9": 1920, "1:1": 1080}
    h_map = {"9:16": 1920, "16:9": 1080, "1:1": 1080}
    target_w = w_map.get(video_aspect, 1080)
    target_h = h_map.get(video_aspect, 1920)

    headers = {
        "Authorization": cfg.pexels_api_key,
        "User-Agent": "BookAI/1.0",
    }
    params = {
        "query": search_term,
        "per_page": cfg.max_results_per_term,
        "orientation": orientation,
    }
    url = f"https://api.pexels.com/videos/search?{urlencode(params)}"

    session = _get_session(cfg.proxy)
    try:
        resp = session.get(url, headers=headers, timeout=cfg.timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    materials = []
    for video in data.get("videos", []):
        duration = video.get("duration", 0)
        if duration < cfg.min_duration:
            continue

        # Find best matching video file
        best_file = None
        for vf in video.get("video_files", []):
            vf_w = vf.get("width", 0)
            vf_h = vf.get("height", 0)
            if vf_w >= target_w * 0.8 and vf_h >= target_h * 0.8:
                if best_file is None or vf_w > best_file.get("width", 0):
                    best_file = vf

        if not best_file:
            # Take the highest quality file available
            sorted_files = sorted(
                video.get("video_files", []),
                key=lambda x: x.get("width", 0) * x.get("height", 0),
                reverse=True,
            )
            if sorted_files:
                best_file = sorted_files[0]

        if best_file and best_file.get("link"):
            materials.append(MaterialInfo(
                provider="pexels",
                url=best_file["link"],
                duration=duration,
                width=best_file.get("width", 0),
                height=best_file.get("height", 0),
                search_term=search_term,
            ))

    return materials


# ---------------------------------------------------------------------------
# Pixabay
# ---------------------------------------------------------------------------


def search_pixabay(
    search_term: str,
    video_aspect: str = "9:16",
    config: StockVideoConfig | None = None,
) -> list[MaterialInfo]:
    """Search Pixabay for stock video clips.

    Requires ``config.pixabay_api_key`` (free at https://pixabay.com/api/docs/).
    """
    cfg = config or StockVideoConfig()
    if not cfg.pixabay_api_key:
        return []

    # Pixabay uses "vertical", "horizontal", "all"
    orientation_map = {"9:16": "vertical", "16:9": "horizontal", "1:1": "all"}
    video_type = orientation_map.get(video_aspect, "vertical")

    params = {
        "key": cfg.pixabay_api_key,
        "q": search_term,
        "video_type": "all",
        "orientation": video_type,
        "per_page": cfg.max_results_per_term,
        "safesearch": "true",
    }
    url = f"https://pixabay.com/api/videos/?{urlencode(params)}"

    session = _get_session(cfg.proxy)
    try:
        resp = session.get(url, timeout=cfg.timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    materials = []
    for hit in data.get("hits", []):
        duration = hit.get("duration", 0)
        if duration < cfg.min_duration:
            continue

        videos = hit.get("videos", {})
        # Try large → medium → small
        for quality in ["large", "medium", "small"]:
            vf = videos.get(quality, {})
            if vf.get("url"):
                materials.append(MaterialInfo(
                    provider="pixabay",
                    url=vf["url"],
                    duration=duration,
                    width=vf.get("width", 0),
                    height=vf.get("height", 0),
                    search_term=search_term,
                ))
                break

    return materials


# ---------------------------------------------------------------------------
# Provider: Coverr  (coverr.co — free 4K video clips)
# ---------------------------------------------------------------------------


def search_coverr(
    search_term: str,
    video_aspect: str = "9:16",
    config: StockVideoConfig | None = None,
) -> list[MaterialInfo]:
    """Search Coverr for free stock videos.

    Coverr provides high-quality, free 4K video clips.
    API docs: https://coverr.co/api (Bearer token auth).

    The search endpoint returns hits with ``playback_id`` (Mux-hosted).
    To get a direct CDN download URL, we fetch ``/videos/{id}`` for each
    hit and read ``urls.mp4`` (1080p) or ``urls.mp4_preview`` (360p).
    """
    cfg = config or StockVideoConfig()
    api_key = getattr(cfg, "coverr_api_key", "")
    if not api_key:
        return []

    materials: list[MaterialInfo] = []
    session = _get_session(cfg.proxy)

    # Map aspect to Coverr's is_vertical filter
    orientation_filter = ""
    if video_aspect == "9:16":
        orientation_filter = " AND is_vertical:true"
    elif video_aspect == "16:9":
        orientation_filter = " AND is_vertical:false"

    try:
        resp = session.get(
            "https://api.coverr.co/videos",
            params={
                "query": search_term,
                "page_size": cfg.max_results_per_term,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=cfg.timeout,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        hits = data.get("hits", [])

        for hit in hits:
            vid_id = hit.get("id", "")
            duration = float(hit.get("duration", 0))
            if duration < cfg.min_duration:
                continue

            # Fetch detail to get direct CDN download URL
            try:
                detail_resp = session.get(
                    f"https://api.coverr.co/videos/{vid_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=cfg.timeout,
                )
                if detail_resp.status_code != 200:
                    continue

                detail = detail_resp.json()
                urls = detail.get("urls", {})
                # Prefer 1080p, fallback to preview (360p)
                download_url = urls.get("mp4", urls.get("mp4_preview", ""))
                if not download_url:
                    continue

                materials.append(MaterialInfo(
                    provider="coverr",
                    url=download_url,
                    duration=duration,
                    width=int(hit.get("max_width", 0)),
                    height=int(hit.get("max_height", 0)),
                    search_term=search_term,
                ))

                time.sleep(0.2)  # Be polite to their API

            except Exception:
                continue

    except Exception:
        pass

    return materials


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_material(
    material: MaterialInfo,
    output_dir: str | Path,
    config: StockVideoConfig | None = None,
) -> MaterialInfo:
    """Download a single material to local storage.

    Returns:
        MaterialInfo with ``local_path`` set.
    """
    cfg = config or StockVideoConfig()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check cache
    cache_dir = Path(cfg.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename from URL
    url_hash = _url_to_filename(material.url)
    cache_path = cache_dir / url_hash
    target_path = output_dir / url_hash

    # Use cache if available
    if cache_path.exists():
        import shutil
        shutil.copy2(str(cache_path), str(target_path))
        material.local_path = str(target_path)
        return material

    # Download
    session = _get_session(cfg.proxy)
    try:
        resp = session.get(material.url, stream=True, timeout=cfg.timeout)
        resp.raise_for_status()

        with open(str(cache_path), "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        import shutil
        shutil.copy2(str(cache_path), str(target_path))
        material.local_path = str(target_path)

    except Exception:
        pass

    return material


def _url_to_filename(url: str) -> str:
    """Convert URL to a safe filename."""
    import hashlib
    ext = ".mp4"
    url_lower = url.lower()
    for e in [".mp4", ".mov", ".webm"]:
        if e in url_lower:
            ext = e
            break
    name_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    return f"stock_{name_hash}{ext}"


# ---------------------------------------------------------------------------
# High-level: search + download pipeline
# ---------------------------------------------------------------------------


def search_and_download(
    search_terms: list[str],
    video_aspect: str = "9:16",
    output_dir: str = "output/materials",
    config: StockVideoConfig | None = None,
    max_total: int = 10,
) -> list[MaterialInfo]:
    """Search for stock videos and download them.

    Searches across configured providers, downloads the best matches.

    Args:
        search_terms: List of English search terms (from BookAI storyboard).
        video_aspect: "9:16", "16:9", or "1:1".
        output_dir: Directory to save downloaded clips.
        config: StockVideoConfig.
        max_total: Max total clips to download.

    Returns:
        List of MaterialInfo with local_path set.
    """
    cfg = config or StockVideoConfig()
    all_materials: list[MaterialInfo] = []

    for term in search_terms:
        if len(all_materials) >= max_total:
            break

        # Search based on configured provider
        if cfg.provider == "pexels" or cfg.pexels_api_key:
            results = search_pexels(term, video_aspect, cfg)
            all_materials.extend(results)

        if cfg.provider == "pixabay" or cfg.pixabay_api_key:
            results = search_pixabay(term, video_aspect, cfg)
            all_materials.extend(results)

        if cfg.provider == "coverr" or cfg.coverr_api_key:
            results = search_coverr(term, video_aspect, cfg)
            all_materials.extend(results)

        # Rate limit between API calls
        time.sleep(0.5)

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for m in all_materials:
        if m.url not in seen_urls:
            seen_urls.add(m.url)
            unique.append(m)

    # Limit total
    unique = unique[:max_total]

    # Download all
    downloaded = []
    for m in unique:
        result = download_material(m, output_dir, cfg)
        if result.local_path:
            downloaded.append(result)

    return downloaded


def match_materials_to_script(
    materials: list[MaterialInfo],
    script_sections: list[str],
) -> list[MaterialInfo]:
    """Order materials to match script narrative flow.

    Matches each script section to the most relevant material based on
    search term similarity. Inspired by MPT's match_materials_to_script.

    Args:
        materials: Available materials.
        script_sections: List of script section texts.

    Returns:
        Materials reordered to match script flow.
    """
    if not materials or not script_sections:
        return materials

    ordered = []
    remaining = list(materials)

    for section in script_sections:
        section_lower = section.lower()
        best_match = None
        best_score = -1

        for m in remaining:
            # Score based on search term overlap with section
            term_words = set(m.search_term.lower().split())
            section_words = set(section_lower.split())
            overlap = len(term_words & section_words)
            if overlap > best_score:
                best_score = overlap
                best_match = m

        if best_match:
            ordered.append(best_match)
            remaining.remove(best_match)
        elif remaining:
            ordered.append(remaining.pop(0))

    # Append any remaining materials
    ordered.extend(remaining)
    return ordered
