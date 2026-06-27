"""Unified material management for BookAI video pipeline.

Manages video/image materials from multiple sources:
- Stock APIs (Pexels, Pixabay, Coverr) with keyword search
- Local folders (recursive scan with categorization)
- Mixed mode (local priority + stock supplement)

Inspired by MoneyPrinterTurbo's material.py and task.py flow.

Usage:
    from bookai.material_manager import MaterialManager, MaterialConfig

    mgr = MaterialManager(MaterialConfig(
        source_mode="mixed",
        local_dir="/path/to/materials",
        local_priority=True,
    ))
    paths = mgr.collect(
        search_terms=["reading book", "sunrise"],
        audio_duration=30.0,
        output_dir="output/",
    )
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
ALL_MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS

# Suggested local folder structure
CATEGORY_FOLDERS = {
    "hooks": "hooks",           # Videos/images for hook sections
    "backgrounds": "backgrounds",  # Background footage
    "book_covers": "book_covers",  # Book cover images
    "overlays": "overlays",     # Text overlays, watermarks
    "intros": "intros",         # Intro clips
    "outros": "outros",         # Outro clips
    "general": "general",       # General purpose materials
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class MaterialConfig:
    """Configuration for material collection."""

    # Source mode
    source_mode: str = "stock"
    # "stock" — only use stock APIs
    # "local" — only use local folder
    # "mixed" — combine local + stock

    # Stock API settings
    stock_provider: str = "pexels"  # "pexels", "pixabay", "coverr"
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    coverr_api_key: str = ""
    max_results_per_term: int = 3
    min_clip_duration: int = 3
    max_clip_duration: int = 7
    video_aspect: str = "9:16"

    # Local settings
    local_dir: str = ""
    local_priority: bool = True  # In mixed mode, use local first
    scan_recursive: bool = True
    min_resolution: int = 480  # Minimum width/height

    # Material matching
    match_mode: str = "ordered"  # "ordered", "random", "smart"

    # Cache
    cache_dir: str = ""


@dataclass
class MaterialItem:
    """Represents a single material file with metadata."""
    path: str = ""
    source: str = ""         # "local", "pexels", "pixabay", "coverr"
    media_type: str = ""     # "video" or "image"
    duration: float = 0.0    # Duration for videos (seconds)
    width: int = 0
    height: int = 0
    category: str = ""       # e.g., "hooks", "backgrounds", "general"
    search_term: str = ""    # Keyword used to find this material


# ---------------------------------------------------------------------------
# Local material scanning
# ---------------------------------------------------------------------------

def scan_local_directory(
    material_dir: str,
    recursive: bool = True,
    min_resolution: int = 0,
) -> list[MaterialItem]:
    """Scan a local directory for video and image materials.

    Args:
        material_dir: Path to the material directory.
        recursive: Whether to scan subdirectories.
        min_resolution: Minimum width/height in pixels (0 = no check).

    Returns:
        List of MaterialItem objects.
    """
    if not material_dir or not os.path.isdir(material_dir):
        logger.warning(f"Material directory not found: {material_dir}")
        return []

    materials = []
    base_path = Path(material_dir)

    if recursive:
        file_iter = base_path.rglob("*")
    else:
        file_iter = base_path.glob("*")

    for file_path in sorted(file_iter):
        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()
        if ext not in ALL_MEDIA_EXTENSIONS:
            continue

        if file_path.stat().st_size == 0:
            continue

        # Determine media type
        media_type = "video" if ext in VIDEO_EXTENSIONS else "image"

        # Determine category from parent folder name
        category = "general"
        rel_path = file_path.relative_to(base_path)
        if len(rel_path.parts) > 1:
            parent = rel_path.parts[0].lower()
            for cat_key, cat_folder in CATEGORY_FOLDERS.items():
                if parent == cat_folder or parent == cat_key:
                    category = cat_key
                    break

        # Check resolution if ffprobe available
        duration = 0.0
        width, height = 0, 0
        if media_type == "video":
            try:
                duration, width, height = _probe_media(str(file_path))
            except Exception:
                pass

        item = MaterialItem(
            path=str(file_path),
            source="local",
            media_type=media_type,
            duration=duration,
            width=width,
            height=height,
            category=category,
        )
        materials.append(item)

    logger.info(f"Scanned {len(materials)} local materials from {material_dir}")

    # Log category breakdown
    cats = {}
    for m in materials:
        cats[m.category] = cats.get(m.category, 0) + 1
    logger.info(f"Categories: {cats}")

    return materials


def _probe_media(path: str) -> tuple[float, int, int]:
    """Get duration, width, height using ffprobe."""
    import subprocess

    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if result.returncode != 0:
        return 0.0, 0, 0

    import json
    data = json.loads(result.stdout)

    # Get duration from format
    duration = float(data.get("format", {}).get("duration", 0))

    # Get resolution from first video stream
    width, height = 0, 0
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            if not duration:
                duration = float(stream.get("duration", 0))
            break

    return duration, width, height


# ---------------------------------------------------------------------------
# Material matching
# ---------------------------------------------------------------------------

def match_materials_to_sections(
    materials: list[MaterialItem],
    section_keywords: list[dict],
    match_mode: str = "ordered",
    audio_duration: float = 0.0,
    max_clip_duration: int = 7,
) -> list[MaterialItem]:
    """Match materials to script sections based on keywords.

    Args:
        materials: Available materials.
        section_keywords: From keyword_generator.generate_section_keywords().
        match_mode: "ordered", "random", or "smart".
        audio_duration: Total audio duration to cover.
        max_clip_duration: Max seconds per clip.

    Returns:
        Ordered list of MaterialItems matching the script timeline.
    """
    if not materials:
        return []

    if match_mode == "random":
        result = list(materials)
        random.shuffle(result)
        return _trim_to_duration(result, audio_duration, max_clip_duration)

    if match_mode == "ordered" and section_keywords:
        # Round-robin across sections (like MPT's _download_videos_by_script_order)
        result = []
        used = set()

        for section in section_keywords:
            keywords = section.get("keywords", [])
            section_materials = []

            for mat in materials:
                if mat.path in used:
                    continue
                # Check if material matches any keyword
                if mat.search_term and any(
                    kw.lower() in mat.search_term.lower()
                    for kw in keywords
                ):
                    section_materials.append(mat)
                    used.add(mat.path)

            # If no keyword match, take next unused material
            if not section_materials:
                for mat in materials:
                    if mat.path not in used:
                        section_materials.append(mat)
                        used.add(mat.path)
                        break

            result.extend(section_materials)

        # Add remaining unused materials if needed
        for mat in materials:
            if mat.path not in used:
                result.append(mat)
                used.add(mat.path)

        return _trim_to_duration(result, audio_duration, max_clip_duration)

    # Default: return in order
    return _trim_to_duration(materials, audio_duration, max_clip_duration)


def _trim_to_duration(
    materials: list[MaterialItem],
    target_duration: float,
    max_clip_duration: int,
) -> list[MaterialItem]:
    """Keep only enough materials to cover the target duration."""
    if target_duration <= 0:
        return materials

    result = []
    total = 0.0
    for mat in materials:
        clip_dur = min(max_clip_duration, mat.duration) if mat.duration > 0 else max_clip_duration
        result.append(mat)
        total += clip_dur
        if total >= target_duration:
            break

    return result


# ---------------------------------------------------------------------------
# Material Manager
# ---------------------------------------------------------------------------

class MaterialManager:
    """Central manager for collecting materials from all sources.

    Supports stock APIs, local folders, and mixed mode with priority control.
    """

    def __init__(self, config: MaterialConfig | None = None):
        self.config = config or MaterialConfig()
        self._local_cache: list[MaterialItem] | None = None

    def collect(
        self,
        search_terms: list[str],
        audio_duration: float = 0.0,
        output_dir: str = "",
        section_keywords: list[dict] | None = None,
    ) -> list[str]:
        """Collect material file paths from configured sources.

        Args:
            search_terms: English keywords for stock search.
            audio_duration: Total seconds to cover.
            output_dir: Directory for downloaded stock materials.
            section_keywords: Optional section-level keywords for ordered matching.

        Returns:
            List of local file paths to materials.
        """
        config = self.config

        if config.source_mode == "local":
            return self._collect_local_only(audio_duration)

        if config.source_mode == "stock":
            return self._collect_stock_only(
                search_terms, audio_duration, output_dir,
            )

        # Mixed mode
        return self._collect_mixed(
            search_terms, audio_duration, output_dir, section_keywords,
        )

    def _collect_local_only(self, audio_duration: float) -> list[str]:
        """Collect materials from local folder only."""
        materials = self._scan_local()
        if not materials:
            logger.warning("No local materials found")
            return []

        # Optional: trim to duration
        if audio_duration > 0:
            materials = _trim_to_duration(
                materials, audio_duration, self.config.max_clip_duration,
            )

        paths = [m.path for m in materials if os.path.exists(m.path)]
        logger.info(f"Collected {len(paths)} local materials")
        return paths

    def _collect_stock_only(
        self,
        search_terms: list[str],
        audio_duration: float,
        output_dir: str,
    ) -> list[str]:
        """Download stock materials using keyword search."""
        try:
            from bookai.stock_video import search_and_download, StockVideoConfig
        except ImportError:
            logger.error("stock_video module not available")
            return []

        stock_cfg = StockVideoConfig(
            provider=self.config.stock_provider,
            pexels_api_key=self.config.pexels_api_key,
            pixabay_api_key=self.config.pixabay_api_key,
            coverr_api_key=self.config.coverr_api_key,
            min_duration=self.config.min_clip_duration,
            max_results_per_term=self.config.max_results_per_term,
            cache_dir=self.config.cache_dir or os.path.join(output_dir, "stock_cache"),
        )

        materials = search_and_download(
            search_terms=search_terms,
            video_aspect=self.config.video_aspect,
            output_dir=os.path.join(output_dir, "materials"),
            config=stock_cfg,
        )

        paths = [m.local_path for m in materials
                 if m.local_path and os.path.exists(m.local_path)]
        logger.info(f"Downloaded {len(paths)} stock materials")
        return paths

    def _collect_mixed(
        self,
        search_terms: list[str],
        audio_duration: float,
        output_dir: str,
        section_keywords: list[dict] | None = None,
    ) -> list[str]:
        """Mixed mode: combine local and stock materials."""
        local_materials = self._scan_local()
        local_paths = [m.path for m in local_materials if os.path.exists(m.path)]

        # Calculate how much duration local covers
        local_duration = sum(
            min(self.config.max_clip_duration, m.duration) if m.duration > 0
            else self.config.max_clip_duration
            for m in local_materials
        )

        remaining_duration = max(0, audio_duration - local_duration)

        if self.config.local_priority:
            # Local first, stock fills the gap
            if remaining_duration > 0 and search_terms:
                stock_paths = self._collect_stock_only(
                    search_terms, remaining_duration, output_dir,
                )
                all_paths = local_paths + stock_paths
            else:
                all_paths = local_paths
        else:
            # Stock first, local supplements
            stock_paths = self._collect_stock_only(
                search_terms, audio_duration, output_dir,
            )
            if len(stock_paths) < 3:  # Not enough stock, supplement with local
                all_paths = stock_paths + local_paths
            else:
                all_paths = stock_paths

        logger.info(
            f"Mixed mode: {len(local_paths)} local + "
            f"{len(all_paths) - len(local_paths)} stock = {len(all_paths)} total"
        )
        return all_paths

    def _scan_local(self) -> list[MaterialItem]:
        """Scan local directory (with caching)."""
        if self._local_cache is not None:
            return self._local_cache

        self._local_cache = scan_local_directory(
            material_dir=self.config.local_dir,
            recursive=self.config.scan_recursive,
            min_resolution=self.config.min_resolution,
        )
        return self._local_cache

    def get_categorized_materials(self) -> dict[str, list[MaterialItem]]:
        """Get local materials organized by category.

        Returns:
            Dict mapping category name to list of MaterialItems.
            e.g., {"hooks": [...], "backgrounds": [...], "general": [...]}
        """
        materials = self._scan_local()
        categorized: dict[str, list[MaterialItem]] = {}

        for mat in materials:
            cat = mat.category or "general"
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(mat)

        return categorized

    def clear_cache(self):
        """Clear the local scan cache."""
        self._local_cache = None
