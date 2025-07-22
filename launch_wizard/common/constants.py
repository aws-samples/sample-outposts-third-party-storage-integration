"""
This module defines project-level constants.
"""

from launch_wizard.common.enums import FeatureName

# Vendor-specific errors from SDKs
NETAPP_DUPLICATE_NQN_ERR_CODE = 72089705
NETAPP_DUPLICATE_IQN_ERR_CODE = 5374035
NETAPP_DUPLICATE_LUN_MAP_ERR_CODE = 1254207

VERIFIED_AMIS = [
    {"family": "Amazon Linux", "includes": ["al2023-ami-"]},
    {"family": "iPXE", "includes": ["iPXE-"]},  # Temporary name
    {"family": "LocalBoot", "includes": ["localboot-ami-"]},  # Temporary name
    {"family": "Red Hat", "includes": ["RHEL-9", "RHEL-10"]},
    {"family": "Windows", "includes": ["Windows_Server-2022-", "Windows_Server-2025-"]},
]

DEFAULT_MINIMUM_ROOT_VOLUME_SIZE = 1  # GiB

ALLOWED_STORAGE_TARGET_LIMITS = {FeatureName.DATA_VOLUMES: None, FeatureName.LOCALBOOT: 1, FeatureName.SANBOOT: 1}

AWS_DEFAULT_REGION = "us-west-2"
AWS_IQN_PREFIX = "iqn.2006-03.com.amazon.aws"
AWS_NQN_PREFIX = "nqn.2014-08.org.nvmexpress:uuid"

NETAPP_ISCSI_PROTOCOL_NAME = "iscsi"
NETAPP_NVME_TCP_PROTOCOL_NAME = "nvme_tcp"
NETAPP_MIXED_PROTOCOL_NAME = "mixed"
NETAPP_ISCSI_DATA_SERVICE = "data_iscsi"

# The input placeholder for None values
OPTIONAL_VALUE_NONE_PLACEHOLDER = "[none]"
