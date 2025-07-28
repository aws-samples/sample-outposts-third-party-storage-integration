"""
Utils package for vmie.

This package contains utility functions organized into specialized modules:

- decompression_utils: File decompression utilities
- file_utils: File operations and format detection utilities
- logging_utils: Logging configuration and display utilities
- source_utils: Image source processing utilities
- validation_utils: Input validation utilities (AMI IDs, URLs, file paths)
"""

from .decompression_utils import decompress_file, get_decompressed_filename, get_decompressed_path, is_compressed_file

# Import from new utils modules
from .file_utils import (
    cleanup_temp_directory,
    create_temp_directory,
    detect_image_format,
    format_bytes,
    format_file_size,
    get_file_size,
)
from .logging_utils import (
    _setup_file_logging,
    display_summary,
    error_and_exit,
    log_message,
    log_section,
    log_step,
    wait_with_progress,
)
from .source_utils import (
    extract_filename_from_url,
    get_image_source_type,
    get_s3_info_from_url,
    load_disk_containers_from_json,
)
from .validation_utils import (
    validate_ami_id,
    validate_image_source,
    validate_json_file,
    validate_license_type,
    validate_local_file,
    validate_s3_url,
    validate_url,
    validate_usage_operation,
)

__all__ = [
    # Utils
    "decompress_file",
    "get_decompressed_path",
    "get_decompressed_filename",
    "is_compressed_file",
    "wait_with_progress",
    "error_and_exit",
    "display_summary",
    "log_message",
    "log_section",
    "log_step",
    "detect_image_format",
    "get_file_size",
    "format_bytes",
    "format_file_size",
    "create_temp_directory",
    "cleanup_temp_directory",
    "_setup_file_logging",
    "log_message",
    "get_s3_info_from_url",
    "extract_filename_from_url",
    "get_image_source_type",
    "validate_ami_id",
    "validate_image_source",
    "validate_url",
    "validate_s3_url",
    "validate_local_file",
    "validate_json_file",
    "validate_license_type",
    "validate_usage_operation",
    "load_disk_containers_from_json",
]
