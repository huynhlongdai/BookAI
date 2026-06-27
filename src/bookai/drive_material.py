"""Google Drive material integration for BookAI.

Allows fetching video/image materials from Google Drive shared folders.
Supports both public shared links and service account authentication.

Usage::

    from bookai.drive_material import DriveConfig, DriveMaterialManager

    mgr = DriveMaterialManager(DriveConfig(
        folder_url="https://drive.google.com/drive/folders/1ABC...",
    ))
    files = mgr.list_files()
    mgr.download_all(output_dir="/path/to/materials")

Supports:
  - Public shared folders (no auth needed)
  - Service account JSON key file
  - OAuth2 token
  - Direct file links (drive.google.com/file/d/...)
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class DriveConfig:
    """Google Drive connection config."""
    folder_url: str = ""          # Shared folder URL
    folder_id: str = ""           # Direct folder ID (alternative to URL)
    api_key: str = ""             # Google API key (for public folders)
    service_account_json: str = ""  # Path to service account JSON
    oauth_token: str = ""          # OAuth2 access token
    download_dir: str = "materials/drive"
    max_files: int = 50
    file_types: list[str] = field(default_factory=lambda: [
        "video/mp4", "video/quicktime", "video/x-msvideo", "video/webm",
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "audio/mpeg", "audio/wav",
    ])


# ---------------------------------------------------------------------------
# Drive File Info
# ---------------------------------------------------------------------------


@dataclass
class DriveFile:
    """Info about a file on Google Drive."""
    id: str
    name: str
    mime_type: str
    size_bytes: int = 0
    thumbnail_url: str = ""
    web_view_url: str = ""
    local_path: str = ""
    downloaded: bool = False
    category: str = "general"  # hooks, backgrounds, book_covers, overlays, intros, outros, general

    @property
    def is_video(self) -> bool:
        return self.mime_type.startswith("video/")

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")

    @property
    def is_audio(self) -> bool:
        return self.mime_type.startswith("audio/")

    @property
    def extension(self) -> str:
        ext = mimetypes.guess_extension(self.mime_type)
        return ext or os.path.splitext(self.name)[1] or ".bin"


# ---------------------------------------------------------------------------
# URL Parsing
# ---------------------------------------------------------------------------


def extract_folder_id(url: str) -> str:
    """Extract Google Drive folder ID from URL.

    Handles:
      - https://drive.google.com/drive/folders/FOLDER_ID
      - https://drive.google.com/drive/folders/FOLDER_ID?usp=sharing
      - https://drive.google.com/drive/u/0/folders/FOLDER_ID
    """
    if not url:
        return ""

    patterns = [
        r"/folders/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    # If it looks like a bare folder ID
    if re.match(r"^[a-zA-Z0-9_-]{10,}$", url):
        return url

    return ""


def extract_file_id(url: str) -> str:
    """Extract Google Drive file ID from URL.

    Handles:
      - https://drive.google.com/file/d/FILE_ID/view
      - https://drive.google.com/open?id=FILE_ID
    """
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


# ---------------------------------------------------------------------------
# Drive Material Manager
# ---------------------------------------------------------------------------


class DriveMaterialManager:
    """Manage materials from Google Drive."""

    DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"

    def __init__(self, config: DriveConfig):
        self.config = config
        self._folder_id = config.folder_id or extract_folder_id(config.folder_url)
        self._files: list[DriveFile] = []

    @property
    def folder_id(self) -> str:
        return self._folder_id

    def _get_auth_header(self) -> dict[str, str]:
        """Get authorization header based on config."""
        if self.config.oauth_token:
            return {"Authorization": f"Bearer {self.config.oauth_token}"}
        return {}

    def _api_url(self, endpoint: str, params: dict | None = None) -> str:
        """Build API URL with parameters."""
        url = f"{self.DRIVE_API_BASE}/{endpoint}"
        all_params = dict(params or {})
        if self.config.api_key:
            all_params["key"] = self.config.api_key
        if all_params:
            url += "?" + urllib.parse.urlencode(all_params)
        return url

    def _api_request(self, url: str) -> dict:
        """Make authenticated API request."""
        headers = self._get_auth_header()
        headers["Accept"] = "application/json"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Drive API error {e.code}: {body}") from e

    # ----- List files -----

    def list_files(self, folder_id: str = "") -> list[DriveFile]:
        """List media files in a Google Drive folder.

        Uses Drive API v3.  For public folders, an API key is sufficient.
        For private folders, use service_account_json or oauth_token.
        """
        fid = folder_id or self._folder_id
        if not fid:
            raise ValueError("No folder ID or URL provided")

        # Build MIME type filter
        mime_clauses = " or ".join(
            f"mimeType='{mt}'" for mt in self.config.file_types
        )
        query = f"'{fid}' in parents and trashed=false and ({mime_clauses})"

        params = {
            "q": query,
            "fields": "files(id,name,mimeType,size,thumbnailLink,webViewLink)",
            "pageSize": str(min(self.config.max_files, 100)),
            "orderBy": "name",
        }

        url = self._api_url("files", params)
        data = self._api_request(url)

        files = []
        for item in data.get("files", []):
            df = DriveFile(
                id=item["id"],
                name=item.get("name", "unknown"),
                mime_type=item.get("mimeType", "application/octet-stream"),
                size_bytes=int(item.get("size", 0)),
                thumbnail_url=item.get("thumbnailLink", ""),
                web_view_url=item.get("webViewLink", ""),
                category=self._categorize_file(item.get("name", "")),
            )
            files.append(df)

        self._files = files[:self.config.max_files]
        return self._files

    def list_subfolders(self, folder_id: str = "") -> list[dict]:
        """List subfolders within a Drive folder."""
        fid = folder_id or self._folder_id
        if not fid:
            return []

        query = f"'{fid}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
        params = {
            "q": query,
            "fields": "files(id,name)",
            "pageSize": "50",
        }
        url = self._api_url("files", params)
        data = self._api_request(url)
        return [{"id": f["id"], "name": f["name"]} for f in data.get("files", [])]

    # ----- Download -----

    def download_file(self, file: DriveFile, output_dir: str = "") -> str:
        """Download a single file from Google Drive.

        Returns the local file path.
        """
        out_dir = output_dir or self.config.download_dir
        os.makedirs(out_dir, exist_ok=True)

        # Safe filename
        safe_name = re.sub(r'[^\w\-_. ]', '_', file.name)
        local_path = os.path.join(out_dir, safe_name)

        # Direct download URL
        download_url = f"https://www.googleapis.com/drive/v3/files/{file.id}?alt=media"
        if self.config.api_key:
            download_url += f"&key={self.config.api_key}"

        headers = self._get_auth_header()
        req = urllib.request.Request(download_url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(local_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
        except urllib.error.HTTPError as e:
            # Try fallback: export link for Google Workspace files
            if e.code == 403:
                return self._download_public_file(file.id, local_path)
            raise RuntimeError(f"Download failed for {file.name}: {e.code}") from e

        file.local_path = local_path
        file.downloaded = True
        return local_path

    def _download_public_file(self, file_id: str, local_path: str) -> str:
        """Download using the public download link (no API key needed for shared files)."""
        # Google Drive direct download trick
        url = f"https://drive.google.com/uc?export=download&id={file_id}"

        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(req, timeout=120) as resp:
            # Check for virus scan warning page
            content = resp.read()
            if b"download_warning" in content or b"confirm=" in content:
                # Parse confirmation token
                match = re.search(rb'confirm=([0-9A-Za-z_-]+)', content)
                if match:
                    token = match.group(1).decode()
                    url2 = f"{url}&confirm={token}"
                    req2 = urllib.request.Request(url2)
                    req2.add_header("User-Agent", "Mozilla/5.0")
                    with urllib.request.urlopen(req2, timeout=120) as resp2:
                        content = resp2.read()

            with open(local_path, "wb") as f:
                f.write(content)

        return local_path

    def download_all(
        self,
        output_dir: str = "",
        categories: list[str] | None = None,
        max_files: int = 0,
    ) -> list[str]:
        """Download all (or filtered) files from the folder.

        Args:
            output_dir: Override download directory
            categories: Filter by category (hooks, backgrounds, etc.)
            max_files: Max files to download (0 = all)

        Returns:
            List of local file paths
        """
        if not self._files:
            self.list_files()

        files = self._files
        if categories:
            files = [f for f in files if f.category in categories]
        if max_files > 0:
            files = files[:max_files]

        paths = []
        for file in files:
            try:
                path = self.download_file(file, output_dir)
                paths.append(path)
            except Exception as e:
                print(f"⚠️ Failed to download {file.name}: {e}")

        return paths

    # ----- Categorization -----

    @staticmethod
    def _categorize_file(filename: str) -> str:
        """Auto-categorize file based on name/path patterns."""
        name_lower = filename.lower()

        category_patterns = {
            "hooks": ["hook", "opening", "intro_hook", "teaser"],
            "backgrounds": ["bg", "background", "backdrop", "nền"],
            "book_covers": ["cover", "bìa", "thumbnail"],
            "overlays": ["overlay", "watermark", "logo", "frame"],
            "intros": ["intro", "opening", "mở_đầu"],
            "outros": ["outro", "ending", "kết", "closing"],
        }

        for category, patterns in category_patterns.items():
            for pattern in patterns:
                if pattern in name_lower:
                    return category

        return "general"

    # ----- Sync with MaterialManager -----

    def sync_to_local(self, output_dir: str = "") -> str:
        """Download all files and return the local directory path.

        Useful for integrating with MaterialManager:
            mgr = DriveMaterialManager(config)
            local_dir = mgr.sync_to_local()
            # Then use with MaterialManager(local_dir=local_dir)
        """
        out_dir = output_dir or self.config.download_dir
        os.makedirs(out_dir, exist_ok=True)

        # Create categorized subdirectories
        for cat in ["hooks", "backgrounds", "book_covers", "overlays", "intros", "outros"]:
            os.makedirs(os.path.join(out_dir, cat), exist_ok=True)

        if not self._files:
            self.list_files()

        for file in self._files:
            cat_dir = os.path.join(out_dir, file.category)
            if not os.path.isdir(cat_dir):
                cat_dir = out_dir
            try:
                self.download_file(file, cat_dir)
            except Exception as e:
                print(f"⚠️ {file.name}: {e}")

        return out_dir


# ---------------------------------------------------------------------------
# Convenience: download from a single Drive link
# ---------------------------------------------------------------------------


def download_drive_file(url: str, output_dir: str = "materials/drive") -> str:
    """Download a single file from Google Drive URL.

    Works with:
      - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
      - https://drive.google.com/open?id=FILE_ID
    """
    file_id = extract_file_id(url)
    if not file_id:
        raise ValueError(f"Cannot extract file ID from URL: {url}")

    os.makedirs(output_dir, exist_ok=True)
    local_path = os.path.join(output_dir, f"drive_{file_id}")

    mgr = DriveMaterialManager(DriveConfig())
    df = DriveFile(id=file_id, name=f"drive_{file_id}", mime_type="application/octet-stream")
    return mgr.download_file(df, output_dir)


# ---------------------------------------------------------------------------
# List available Drive folders (from config)
# ---------------------------------------------------------------------------


def list_drive_sources(config_dict: dict) -> list[dict]:
    """List configured Drive material sources from config.

    Expected config format::

        [material.drive]
        folders = [
            {name = "Book Covers", url = "https://drive.google.com/..."},
            {name = "Backgrounds", url = "https://drive.google.com/..."},
        ]
        api_key = "..."
    """
    drive_cfg = config_dict.get("material", {}).get("drive", {})
    folders = drive_cfg.get("folders", [])
    return [
        {
            "name": f.get("name", f"Folder {i+1}"),
            "url": f.get("url", ""),
            "folder_id": extract_folder_id(f.get("url", "")),
        }
        for i, f in enumerate(folders)
    ]
