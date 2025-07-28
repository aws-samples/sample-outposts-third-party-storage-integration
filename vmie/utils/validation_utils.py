"""Validation utility functions for VMIE operations."""

import json
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from vmie.common import ImageSourceType

from .source_utils import get_image_source_type


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def validate_ami_id(ami_id: Optional[str]) -> str:
    """
    Validate AMI ID format.

    Args:
        ami_id: The AMI ID to validate

    Returns:
        str: The validated AMI ID

    Raises:
        ValidationError: If the AMI ID is invalid
    """
    if not ami_id:
        raise ValidationError("AMI ID is required")

    pattern = r"^ami-[a-f0-9]{8,17}$"
    if not bool(re.match(pattern, ami_id)):
        raise ValidationError(f"Invalid AMI ID format: {ami_id}")
    return ami_id


def validate_image_source(image_source: Optional[str]) -> str:
    """
    Validate image source format and accessibility.

    Args:
        image_source: The image source to validate

    Returns:
        str: The validated image source

    Raises:
        ValidationError: If the image source is invalid
    """
    if not image_source:
        raise ValidationError("Image source is required for import operations")

    image_source_type = get_image_source_type(image_source)
    if image_source_type == ImageSourceType.URL:
        return validate_url(image_source)
    elif image_source_type == ImageSourceType.S3:
        return validate_s3_url(image_source)
    elif image_source_type == ImageSourceType.JSON:
        return validate_json_file(image_source)
    else:
        return validate_local_file(image_source)


def validate_url(url: str) -> str:
    """
    Validate URL format.

    Args:
        url: The URL to validate

    Returns:
        str: The validated URL

    Raises:
        ValidationError: If the URL is invalid
    """
    try:
        result = urlparse(url)
    except Exception as e:
        raise ValidationError(f"Invalid URL format: {url}") from e

    if not all([result.scheme, result.netloc]):
        raise ValidationError(f"Invalid URL format: {url}")
    return url


def validate_s3_url(url: str) -> str:
    """
    Validate S3 URL.

    Args:
        url: The S3 URL to validate

    Returns:
        str: The validated S3 URL

    Raises:
        ValidationError: If S3 URL is invalid
    """
    if not url.startswith("s3://"):
        raise ValidationError("Invalid S3 URL format: S3 URL must start with s3://")

    try:
        parsed = urlparse(url)
        source_bucket = parsed.netloc
    except Exception as e:
        raise ValidationError(f"Invalid S3 URL format: {url}") from e

    if not source_bucket:
        raise ValidationError("Invalid S3 URL format: S3 bucket name is required")

    return url


def validate_local_file(local_path: str) -> str:
    """
    Validate local file path.

    Args:
        local_path: The local file path to validate

    Returns:
        str: The validated local file path

    Raises:
        ValidationError: If the local file is invalid
    """
    try:
        source_path = Path(local_path).resolve()
    except Exception as e:
        raise ValidationError(f"Invalid local file path: {local_path}") from e

    # Validate source file exists
    if not source_path.exists():
        raise ValidationError(f"Invalid local file: Local file not found: {source_path}")

    if not source_path.is_file():
        raise ValidationError(f"Invalid local file: Path is not a file: {source_path}")

    # Get file size for validation
    file_size = source_path.stat().st_size
    if file_size == 0:
        raise ValidationError(f"Invalid local file: Local file is empty: {source_path}")
    return local_path


def validate_json_file(json_path: str) -> str:
    """
    Validate JSON file containing disk containers for import.

    Args:
        json_path: The JSON file path to validate

    Returns:
        str: The validated JSON file path

    Raises:
        ValidationError: If the JSON file is invalid
    """
    validate_local_file(json_path)

    # Validate JSON content
    try:
        with open(Path(json_path).resolve(), "r", encoding="utf-8") as f:
            json.load(f)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON file: Failed to parse JSON: {e}") from e
    except Exception as e:
        raise ValidationError(f"Invalid JSON file: Failed to read file: {e}") from e

    return json_path


def validate_license_type(license_type: Optional[str]) -> Optional[str]:
    """
    Validate license type parameter.

    Args:
        license_type: The license type to validate

    Returns:
        Optional[str]: The validated license type

    Raises:
        ValidationError: If the license type is invalid
    """
    if license_type is None:
        return None

    valid_license_types = ["AWS", "BYOL"]
    if license_type not in valid_license_types:
        raise ValidationError(
            f"Invalid license type: {license_type}. " f"Valid values are: {', '.join(valid_license_types)}"
        )

    return license_type


def validate_usage_operation(usage_operation: Optional[str]) -> Optional[str]:
    """
    Validate usage operation parameter.

    Args:
        usage_operation: The usage operation to validate

    Returns:
        Optional[str]: The validated usage operation

    Raises:
        ValidationError: If the usage operation is invalid
    """
    if usage_operation is None:
        return None

    if not usage_operation.startswith("RunInstances"):
        raise ValidationError(
            f"Invalid usage operation: {usage_operation}. " "Usage operation must start with 'RunInstances'"
        )

    return usage_operation
