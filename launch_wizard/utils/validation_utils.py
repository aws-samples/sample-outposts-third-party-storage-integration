"""
Validation utility functions for launch wizard operations.

This module provides comprehensive validation functions for features, storage configurations,
authentication secrets, and other parameters used throughout the launch wizard. It ensures
that user inputs are valid and compatible with the selected features and storage protocols.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from rich.console import Console
from rich.rule import Rule

from launch_wizard.aws.aws_client import AWSClient
from launch_wizard.aws.secrets_manager import get_available_secret_names
from launch_wizard.common.constants import ALLOWED_STORAGE_TARGET_LIMITS, OPTIONAL_VALUE_NONE_PLACEHOLDER
from launch_wizard.common.enums import FeatureName, OperationSystemType, StorageProtocol
from launch_wizard.common.error_codes import ERR_FEATURE_NOT_SUPPORTED, ERR_INPUT_INVALID

from .display_utils import print_table_with_single_column, style_var
from .ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def validate_feature(feature_name: FeatureName, guest_os_type: OperationSystemType, protocol: StorageProtocol) -> None:
    """
    Validates that a feature is supported by the guest OS and protocol.

    Args:
        feature_name: The feature to validate.
        guest_os_type: The guest operating system type.
        protocol: The storage protocol.

    Raises:
        typer.Exit: If the feature is not supported for the given combination.
    """

    def is_feature_valid(
        feature_name: FeatureName, guest_os_type: OperationSystemType, protocol: StorageProtocol
    ) -> bool:
        # Data volumes on Windows does not support NVMe
        # SAN boot does not support NVMe
        # Everything else is supported
        if (
            feature_name == FeatureName.DATA_VOLUMES
            and guest_os_type == OperationSystemType.WINDOWS
            and protocol == StorageProtocol.NVME
        ):
            return False
        if feature_name == FeatureName.SANBOOT and protocol == StorageProtocol.NVME:
            return False

        return True

    if not is_feature_valid(feature_name, guest_os_type, protocol):
        error_and_exit(
            f"The feature {style_var(feature_name, color='yellow')} is not supported for {style_var(guest_os_type, color='yellow')} using the {style_var(protocol, color='yellow')} protocol.",
            code=ERR_FEATURE_NOT_SUPPORTED,
        )


def validate_lun(lun: Union[int, str]) -> int:
    """
    Validates the given LUN.

    Args:
        lun: The LUN to validate.

    Raises:
        ValueError: If the LUN is invalid.
    """

    if isinstance(lun, str):
        try:
            lun = int(lun)
        except ValueError as e:
            raise ValueError(f"LUN must be an integer: {lun}") from e

    # LUNs are typically 0-255 for most storage systems
    # Some systems support up to 16383 (14-bit), but 255 is the most common limit
    if not (0 <= lun <= 255):
        raise ValueError(f"LUN must be between 0 and 255: {lun}")

    return lun


def validate_lun_for_feature(lun: Optional[int], feature_name: FeatureName) -> Optional[int]:
    """
    Validate and process LUN parameter based on the feature type.

    This function handles LUN validation differently depending on the feature:
    - For DATA_VOLUMES: LUN is ignored as it's not applicable
    - For SANBOOT/LOCALBOOT: LUN is required and validated, defaults to 0 if not provided
    - For other features: LUN is returned as-is

    Args:
        lun: The Logical Unit Number to validate (0-255), or None.
        feature_name: The feature that will use this LUN.

    Returns:
        The validated LUN value, None if not applicable for the feature, or 0 as default for boot features.

    Raises:
        typer.Exit: If the LUN value is invalid or the user cancels when prompted for a LUN.
    """

    # Handle LUN parameter based on feature type
    if feature_name == FeatureName.DATA_VOLUMES and lun is not None:
        Console().print(style_var("LUN is specified but will be ignored for the data volumes feature.", color="yellow"))
        return None
    elif feature_name in [FeatureName.SANBOOT, FeatureName.LOCALBOOT]:
        if lun is None:
            # Prompt user to confirm proceeding without LUN
            if not auto_confirm(
                "No LUN (Logical Unit Number) specified. Would you like to proceed with the default LUN 0?"
            ):
                lun = prompt_with_trim("Please enter a LUN value", default=0)

        if lun is not None:
            try:
                # Validate the LUN
                validate_lun(lun)
                Console().print(f"Using LUN {style_var(lun)} for {style_var(feature_name.value)}.")
            except ValueError as e:
                error_and_exit("Invalid LUN value.", Rule(), str(e), code=ERR_INPUT_INVALID)

        return lun
    else:
        return None


def validate_storage_target_count(targets: List[Any], feature_name: FeatureName, protocol: StorageProtocol) -> None:
    """
    Validates that the number of storage targets doesn't exceed the allowed limit for the given feature.

    Args:
        targets: List of storage targets (can be iSCSI targets, NVMe subsystems, etc.)
        feature_name: The feature name
        protocol: The storage protocol (e.g. iSCSI, NVMe)

    Raises:
        typer.Exit: If the number of targets exceeds the allowed limit for the feature.
    """

    allowed_storage_target_limit = get_storage_target_limit(feature_name)
    if allowed_storage_target_limit is not None and len(targets) > allowed_storage_target_limit:
        target_type = "targets" if protocol == StorageProtocol.ISCSI else "subsystems"
        error_and_exit(
            f"Too many {target_type}. The {style_var(feature_name.value, color='yellow')} feature allows a maximum of {style_var(allowed_storage_target_limit, color='yellow')} {target_type}.",
            code=ERR_INPUT_INVALID,
        )


def get_storage_target_limit(feature_name: FeatureName) -> Optional[int]:
    """
    Gets the allowed storage target limit for the given feature.

    Args:
        feature_name: The feature name

    Returns:
        The maximum allowed number of targets, or None if unlimited
    """

    return ALLOWED_STORAGE_TARGET_LIMITS.get(feature_name)


def assign_lun_to_targets(targets: List[Dict[str, str]], lun: Optional[int]) -> None:
    """
    Assigns the LUN to all targets if LUN is specified.

    Args:
        targets: List of target dictionaries
        lun: The LUN to assign, or None to skip assignment

    Note:
        This function modifies the targets list in-place by adding the "lun" key to each target.
    """

    if lun is not None:
        for target in targets:
            target["lun"] = str(lun)


def validate_auth_secret_names_for_targets(
    auth_secret_names_raw_input: Optional[List[str]],
    targets: List[Dict[str, Any]],
    target_type: Union[Literal["discovery portals"], Literal["subsystems"], Literal["targets"]],
    aws_client: AWSClient,
) -> List[Optional[str]]:
    """
    Validates and adjusts auth secret names to match the number of targets/subsystems.

    Args:
        auth_secret_names_raw_input: The raw auth_secret_names input
        targets: List of target/subsystem dictionaries
        target_type: Type of targets displayed in messages (e.g., "targets", "subsystems")
        aws_client: AWS client wrapper

    Returns:
        Validated list of auth secret names matching the number of targets

    Raises:
        typer.Exit: If the number of auth secret names exceeds the number of targets
    """

    auth_secret_names = process_auth_secret_names(auth_secret_names_raw_input)

    if not auth_secret_names and auto_confirm(
        f"No authentication secrets specified for the {target_type}. Would you like to proceed without authentication?"
    ):
        return [None] * len(targets)

    available_secret_names = get_available_secret_names(aws_client.secrets_manager)

    if not auth_secret_names:
        print_table_with_single_column(
            "Available secrets in AWS Secrets Manager", available_secret_names, "Secret Name"
        )

        auth_secret_names = []

        for target in targets:
            auth_secret_name = prompt_with_trim(
                f"Please enter the authentication secret name for {target_type} {str(target)}. Press Enter if no authentication is required.",
                default="",
            )
            auth_secret_names.append(auth_secret_name if auth_secret_name else None)

    num_targets = len(targets)
    num_auth_secrets = len(auth_secret_names)

    # If more auth secret names than targets, that's an error
    if num_auth_secrets > num_targets:
        error_and_exit(
            f"Too many authentication secrets specified. You provided {style_var(num_auth_secrets, color='yellow')} authentication secrets but only have {style_var(num_targets, color='yellow')} {target_type}.",
            code=ERR_INPUT_INVALID,
        )

    # If fewer auth secret names than targets, pad with None values
    if num_auth_secrets < num_targets:
        Console().print(
            f"Only {style_var(num_auth_secrets, color='yellow')} authentication secrets specified for {style_var(num_targets, color='yellow')} {target_type}. The remaining {style_var(num_targets - num_auth_secrets, color='yellow')} {target_type} will not have authentication configured."
        )
        # Pad the list with None values to match the number of targets
        auth_secret_names.extend([None] * (num_targets - num_auth_secrets))

    # Validate that specified secret names exist (only if we have available secret names)
    for auth_secret_name in auth_secret_names:
        if auth_secret_name and auth_secret_name not in available_secret_names:
            error_and_exit(
                f"The authentication secret {style_var(auth_secret_name, color='yellow')} is not available in AWS Secrets Manager.",
                code=ERR_INPUT_INVALID,
            )

    return auth_secret_names


def assign_auth_secret_names_to_targets(targets: List[Dict[str, str]], auth_secret_names: List[Optional[str]]) -> None:
    """
    Assigns auth secret names to targets/subsystems based on their index position.

    Args:
        targets: List of target/subsystem dictionaries
        auth_secret_names: List of auth secret names (already processed by callback)

    Note:
        This function modifies the targets list in-place by adding the "auth_secret_name" key to each target.
        The function assumes that auth_secret_names and targets have the same length.
        auth_secret_names[i] will be assigned to targets[i]["auth_secret_name"].
        If auth_secret_names[i] is None, the "auth_secret_name" key will be set to None.
    """

    for i, auth_secret_name in enumerate(auth_secret_names):
        if auth_secret_name and i < len(targets):  # Safety check to prevent index out of bounds
            targets[i]["auth_secret_name"] = auth_secret_name


def validate_enable_dm_multipath(enable_dm_multipath: Optional[bool]) -> bool:
    """
    Validates the enable_dm_multipath flag.

    Args:
        enable_dm_multipath: The enable_dm_multipath flag.

    Returns:
        The validated enable_dm_multipath flag.
    """

    if enable_dm_multipath is None:
        if not auto_confirm(
            "Device Mapper Multipath (DM Multipath) is not specified. Would you like to proceed without enabling it? (DM Multipath provides redundant paths to storage devices)"
        ):
            enable_dm_multipath = True

    if enable_dm_multipath:
        Console().print("Device Mapper Multipath (DM Multipath) will be enabled for redundant storage paths.")
        return True
    else:
        Console().print("Device Mapper Multipath (DM Multipath) will not be enabled.")
        return False


def process_auth_secret_names(auth_secret_names_raw_input: Optional[List[str]]) -> List[Optional[str]]:
    """
    Callback function to process the raw input of auth_secret_names CLI option.

    Args:
        auth_secret_names_raw_input: The raw auth_secret_names input

    Returns:
        Processed list where:
            - Returns empty list [] if input is None
            - Converts string AUTH_SECRET_NONE_PLACEHOLDER to Python None value
            - Preserves all other string inputs
    """

    if auth_secret_names_raw_input is None:
        return []

    processed_list = [None if item == OPTIONAL_VALUE_NONE_PLACEHOLDER else item for item in auth_secret_names_raw_input]

    return processed_list
