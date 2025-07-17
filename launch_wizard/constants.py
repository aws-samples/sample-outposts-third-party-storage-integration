"""
This module defines project-level constants.
"""

from launch_wizard.enums import FeatureName

# Error codes
# General errors (-10000 to -10099)
ERR_GENERAL_UNKNOWN = -10000
ERR_USER_ABORT = -10001
ERR_FEATURE_NOT_SUPPORTED = -10002
ERR_INPUT_INVALID = -10003
ERR_USER_DATA_NOT_FOUND = -10004

# AWS errors (-10100 to -10199)
ERR_AWS_CLIENT = -10100
ERR_AWS_AMI_NOT_FOUND = -10101
ERR_AWS_INSTANCE_PROFILE_NOT_FOUND = -10102
ERR_AWS_INSTANCE_TYPE_UNSUPPORTED = -10103
ERR_AWS_KEY_PAIR_NOT_FOUND = -10104
ERR_AWS_SECURITY_GROUP_NOT_FOUND = -10105
ERR_AWS_SUBNET_LNI_CONFIG_INVALID = -10106
ERR_AWS_SUBNET_NOT_FOUND = -10107
ERR_AWS_UNSUPPORTED_HARDWARE_TYPE = -10108

# Storage system errors (-10200 to -10299)
ERR_ENDPOINT_NOT_FOUND = -10200
ERR_LUN_NOT_FOUND = -10201
ERR_SUBSYSTEM_NOT_FOUND = -10202
ERR_VOLUME_NOT_FOUND = -10203

# Vendor-specific errors (-10300 to -10399)
ERR_NETAPP_API = -10320
ERR_NETAPP_ISCSI_NOT_ENABLED = -10321
ERR_PURE_API = -10330

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
