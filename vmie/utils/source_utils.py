"""Source utility functions for VM Import/Export operations."""

import json
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from rich.rule import Rule

from vmie.common import ERR_JSON_LOAD_FAILED, ImageSourceType
from vmie.utils.logging_utils import error_and_exit


def get_s3_info_from_url(url: str) -> Tuple[str, str]:
    """
    Extract bucket and key from s3 url.

    Args:
        url: The S3 URL to validate

    Returns:
        Tuple[str, str]: Bucket name and key
    """
    parsed = urlparse(url)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    return bucket, key


def extract_filename_from_url(url: str) -> str:
    """Extract filename from URL."""
    parsed = urlparse(url)
    return Path(parsed.path).name or "downloaded_image"


def get_image_source_type(source: str) -> ImageSourceType:
    """Determine the image source type from the source string."""
    if source.startswith("s3://"):
        return ImageSourceType.S3
    elif source.startswith(("http://", "https://")):
        return ImageSourceType.URL
    elif source.lower().endswith(".json"):
        return ImageSourceType.JSON
    else:
        return ImageSourceType.LOCAL


def load_disk_containers_from_json(json_path: str) -> List[Dict]:
    """
    Load disk containers from JSON file.

    Args:
        json_path: Path to the JSON file

    Returns:
        List[Dict]: List of disk containers for AWS import_image

    Raises:
        ValidationError: If the JSON file is invalid
    """
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        error_and_exit(
            f"Failed to load disk containers from JSON file: {json_path}",
            Rule(),
            str(e),
            code=ERR_JSON_LOAD_FAILED,
        )
