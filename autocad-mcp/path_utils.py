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


# ============================================================================
# Array/Coordinate Validation
# ============================================================================


def validate_2d_coordinates(coordinates, name: str = "coordinates") -> None:
    """
    Validate 2D coordinates array [x1,y1, x2,y2, ...].

    :param coordinates: Array of flat coordinates
    :param name: Parameter name for error messages
    :raises ValueError: If coordinates are invalid
    """
    if not isinstance(coordinates, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple, got {type(coordinates).__name__}")
    if len(coordinates) < 4 or len(coordinates) % 2 != 0:
        raise ValueError(
            f"{name} must have even length (pairs x,y), got {len(coordinates)} numbers. "
            f"Minimum 2 points (4 numbers) required."
        )
    try:
        [float(v) for v in coordinates]
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} contains non-numeric value: {exc}")


def validate_3d_coordinates(coordinates, name: str = "coordinates") -> None:
    """
    Validate 3D coordinates array [x1,y1,z1, x2,y2,z2, ...].

    :param coordinates: Array of flat coordinates
    :param name: Parameter name for error messages
    :raises ValueError: If coordinates are invalid
    """
    if not isinstance(coordinates, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple, got {type(coordinates).__name__}")
    if len(coordinates) < 3 or len(coordinates) % 3 != 0:
        raise ValueError(
            f"{name} must have length divisible by 3 (triplets x,y,z), got {len(coordinates)} numbers. "
            f"Minimum 1 point (3 numbers) required."
        )
    try:
        [float(v) for v in coordinates]
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} contains non-numeric value: {exc}")


def validate_flat_coordinates(coordinates, expected_pairs: int, name: str = "coordinates") -> None:
    """
    Validate flat coordinates with specific expected number of pairs.

    :param coordinates: Array of flat coordinates
    :param expected_pairs: Expected number of x,y pairs
    :param name: Parameter name for error messages
    :raises ValueError: If coordinates are invalid
    """
    if not isinstance(coordinates, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple, got {type(coordinates).__name__}")
    expected_length = expected_pairs * 2
    if len(coordinates) != expected_length:
        raise ValueError(
            f"{name} must have exactly {expected_length} numbers ({expected_pairs} pairs), "
            f"got {len(coordinates)} numbers."
        )
    try:
        [float(v) for v in coordinates]
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} contains non-numeric value: {exc}")


def validate_handles(handles, name: str = "handles") -> None:
    """
    Validate a list of entity handles.

    :param handles: List of handle strings
    :param name: Parameter name for error messages
    :raises ValueError: If handles are invalid
    """
    if not isinstance(handles, (list, tuple)):
        raise ValueError(f"{name} must be a list or tuple, got {type(handles).__name__}")
    if len(handles) == 0:
        raise ValueError(f"{name} cannot be empty")
    for i, handle in enumerate(handles):
        if not isinstance(handle, str) or not handle:
            raise ValueError(f"{name}[{i}] must be a non-empty string, got {repr(handle)}")
