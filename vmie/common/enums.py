"""
This module defines enums for VMIE operations.
"""

from enum import Enum


class OperationMode(str, Enum):
    """Operation modes for VMIE."""

    IMPORT_ONLY = "import-only"
    EXPORT_ONLY = "export-only"
    FULL = "full"


class ImageFormat(str, Enum):
    """Supported VM image formats."""

    OVA = "ova"
    VMDK = "vmdk"
    VHD = "vhd"
    VHDX = "vhdx"
    RAW = "raw"


class LogLevel(str, Enum):
    """Log levels for VMIE operations."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARN = "WARN"
    ERROR = "ERROR"


class ImageSourceType(str, Enum):
    """Image source types for import operations."""

    LOCAL = "LOCAL"
    S3 = "S3"
    URL = "URL"
    JSON = "JSON"
