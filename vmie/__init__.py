"""VM Import/Export Tool for AWS EC2.

A comprehensive solution for importing VM images to AWS EC2 and exporting AMIs to RAW format,
with support for sanbootable installation for sanboot support.
"""

# AWS integration
from .aws import AWSClient, AWSWaiter

# Core functionality
from .core import SanbootableInstaller, SourceProcessor, VMIECore

__version__ = "1.0.0"

__all__ = [
    # Core classes
    "VMIECore",
    "SourceProcessor",
    "SanbootableInstaller",
    # AWS classes
    "AWSClient",
    "AWSWaiter",
]
