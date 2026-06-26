"""File security utilities for BookAI.

Provides path traversal protection, filename sanitization,
and safe file operations for user-uploaded content.

Usage::

    from bookai.file_security import resolve_safe_path, sanitize_filename
    safe = resolve_safe_path("/app/output", "../../../etc/passwd")  # raises ValueError
    name = sanitize_filename("../../evil.sh")  # "evil.sh"
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path


def resolve_safe_path(
    base_dir: str,
    unsafe_path: str,
    *,
    require_file: bool = True,
    require_exists: bool = True,
) -> str:
    """Resolve a path safely within a base directory.

    Prevents path traversal attacks by ensuring the resolved path
    stays within the allowed base directory.

    Args:
        base_dir: The allowed base directory
        unsafe_path: User-provided path (may contain ../ etc.)
        require_file: If True, require the path to be a regular file
        require_exists: If True, require the path to exist

    Returns:
        The resolved absolute path

    Raises:
        ValueError: If the path is outside the allowed directory or invalid
    """
    if not unsafe_path:
        raise ValueError("Empty path is not allowed")

    base_real = os.path.realpath(base_dir)

    # Handle both absolute and relative paths
    if os.path.isabs(unsafe_path):
        candidate = unsafe_path
    else:
        candidate = os.path.join(base_real, unsafe_path)

    resolved = os.path.realpath(candidate)

    # Check if resolved path is within base directory
    try:
        common = os.path.commonpath([base_real, resolved])
    except ValueError:
        # Different drives on Windows
        raise ValueError("Path is outside the allowed directory")

    if common != base_real:
        raise ValueError("Path is outside the allowed directory")

    if require_exists and not os.path.exists(resolved):
        raise ValueError(f"Path does not exist: {resolved}")

    if require_file and require_exists and not os.path.isfile(resolved):
        raise ValueError(f"Path is not a regular file: {resolved}")

    return resolved


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize a filename to prevent security issues.

    Removes directory separators, null bytes, control characters,
    and normalizes Unicode.

    Args:
        filename: The filename to sanitize
        max_length: Maximum filename length

    Returns:
        Sanitized filename
    """
    if not filename:
        return "unnamed"

    # Normalize Unicode
    name = unicodedata.normalize("NFC", filename)

    # Remove null bytes
    name = name.replace("\x00", "")

    # Get just the basename (remove directory parts)
    name = os.path.basename(name)

    # Remove control characters
    name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', name)

    # Remove/replace dangerous characters
    name = re.sub(r'[<>:"|?*\\]', '_', name)

    # Remove leading dots (hidden files) and spaces
    name = name.lstrip('. ')

    # Remove trailing dots and spaces (Windows issue)
    name = name.rstrip('. ')

    # Truncate
    if len(name) > max_length:
        stem, ext = os.path.splitext(name)
        name = stem[:max_length - len(ext)] + ext

    return name or "unnamed"


def is_safe_path(base_dir: str, path: str) -> bool:
    """Check if a path is safely within a base directory.

    Non-raising version of resolve_safe_path.

    Args:
        base_dir: The allowed base directory
        path: Path to check

    Returns:
        True if path is safe, False otherwise
    """
    try:
        resolve_safe_path(base_dir, path, require_file=False, require_exists=False)
        return True
    except ValueError:
        return False


ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".mkv"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".epub", ".txt", ".md"}


def validate_file_type(
    filename: str,
    allowed_extensions: set[str] | None = None,
) -> bool:
    """Validate file type by extension.

    Args:
        filename: Filename to check
        allowed_extensions: Set of allowed extensions (with dot prefix)

    Returns:
        True if file type is allowed
    """
    if allowed_extensions is None:
        allowed_extensions = (
            ALLOWED_VIDEO_EXTENSIONS
            | ALLOWED_AUDIO_EXTENSIONS
            | ALLOWED_IMAGE_EXTENSIONS
            | ALLOWED_DOCUMENT_EXTENSIONS
        )

    ext = os.path.splitext(filename)[1].lower()
    return ext in allowed_extensions
