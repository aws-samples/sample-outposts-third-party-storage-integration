"""File utility functions for VM Import/Export operations."""

import tempfile
from pathlib import Path

from vmie.common import COMPRESSED_EXTENSIONS, ERR_FILE_UNSUPPORTED_FORMAT, SUPPORTED_FORMATS, ImageFormat
from vmie.utils.logging_utils import error_and_exit


def detect_image_format(filename: str) -> ImageFormat:
    """Detect image format from filename."""
    filename_lower = filename.lower()

    # Remove compression extensions
    for ext in COMPRESSED_EXTENSIONS:
        if filename_lower.endswith(ext):
            filename_lower = filename_lower[: -len(ext)]
            break

    # Check supported formats
    for format_name, extensions in SUPPORTED_FORMATS.items():
        for ext in extensions:
            if filename_lower.endswith(ext):
                return ImageFormat(format_name)

    supported_formats = []
    for format_name, extensions in SUPPORTED_FORMATS.items():
        supported_formats.extend(extensions)

    error_and_exit(
        f"Unsupported image format: {filename}",
        f"Supported formats: {', '.join(supported_formats)}",
        "Please convert your image to a supported format",
        code=ERR_FILE_UNSUPPORTED_FORMAT,
    )


def get_file_size(file_path: Path) -> int:
    """Get file size in bytes."""
    return file_path.stat().st_size


def format_bytes(bytes_count: int) -> str:
    """Format bytes as human-readable string."""
    bytes_float = float(bytes_count)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_float < 1024.0:
            return f"{bytes_float:.1f} {unit}"
        bytes_float /= 1024.0
    return f"{bytes_float:.1f} PB"


def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    size_float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} PB"


def create_temp_directory() -> Path:
    """Create a temporary directory for VMIE operations."""
    temp_dir = Path(tempfile.mkdtemp(prefix="vmie_"))
    return temp_dir


def cleanup_temp_directory(temp_dir: Path) -> None:
    """Clean up temporary directory."""
    try:
        import shutil

        shutil.rmtree(temp_dir)
    except Exception as e:
        # Import here to avoid circular imports
        from vmie.common.enums import LogLevel
        from vmie.utils.logging_utils import log_message

        log_message(LogLevel.WARN, f"Failed to clean up temporary directory {temp_dir}: {e}")
