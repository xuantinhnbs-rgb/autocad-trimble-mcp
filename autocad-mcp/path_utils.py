"""
Path validation utilities for secure file operations.

Prevents path injection attacks and ensures only valid file paths
are passed to AutoCAD COM methods.
"""

import os
from pathlib import Path


def _validate_file_path(path: str, allow_unc: bool = False) -> str:
    """
    Validate and normalize a file path for safe AutoCAD operations.

    :param path: The file path to validate
    :param allow_unc: Whether to allow UNC paths (network shares)
    :return: The normalized, validated path
    :raises ValueError: If the path is invalid or unsafe
    """
    if not path or not isinstance(path, str):
        raise ValueError("Path must be a non-empty string")

    # Normalize to absolute path
    try:
        normalized = str(Path(path).resolve())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid path: {exc}")

    # Block UNC paths (network shares) by default
    if not allow_unc and normalized.startswith("\\\\"):
        raise ValueError("UNC paths (network shares) are not allowed")

    # Ensure the path is on a local drive (not a network mapped drive root like \\?\UNC\)
    if normalized.startswith("\\\\?\\UNC\\"):
        raise ValueError("Network UNC paths are not allowed")

    # Verify parent directory exists or can be created
    parent = Path(normalized).parent
    if not parent.exists():
        raise ValueError(f"Parent directory does not exist: {parent}")

    # Check for suspicious patterns
    _check_suspicious_patterns(normalized)

    return normalized


def _validate_dwg_path(path: str) -> str:
    """
    Validate a .dwg file path specifically.

    :param path: The file path to validate
    :return: The normalized, validated path
    :raises ValueError: If the path is invalid or not a .dwg file
    """
    normalized = _validate_file_path(path)

    # Check file extension
    if not normalized.lower().endswith(".dwg"):
        raise ValueError("File must have .dwg extension")

    return normalized


def _check_suspicious_patterns(path: str) -> None:
    """
    Check for suspicious patterns in a path.

    :param path: The path to check
    :raises ValueError: If suspicious patterns are detected
    """
    # Check for path traversal attempts
    if ".." in path.split(os.sep):
        raise ValueError("Path traversal (..) is not allowed")

    # Check for null bytes
    if "\x00" in path:
        raise ValueError("Null bytes in path are not allowed")

    # Check for suspicious environment variables in path
    if "$" in path or "%" in path:
        raise ValueError("Environment variable references in paths are not allowed")
