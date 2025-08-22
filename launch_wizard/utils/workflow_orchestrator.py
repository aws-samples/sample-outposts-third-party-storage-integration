"""
Workflow orchestration utilities for managing multi-stage CLI workflows.

This module handles the coordination of complex workflows that involve multiple stages,
such as the sanboot/localboot workflows that optionally include data volumes configuration.
"""

from typing import Any, Dict, cast

import typer
from rich.console import Console

from launch_wizard.common.enums import FeatureName, StorageProtocol
from launch_wizard.utils.display_utils import style_var
from launch_wizard.utils.ui_utils import auto_confirm, prompt_with_trim


def should_prompt_for_data_volumes_configuration(feature_name: FeatureName) -> bool:
    """
    Determine if the current feature should prompt for data volumes configuration.

    Args:
        feature_name: The current feature being executed.

    Returns:
        True if this feature should prompt for data volumes, False otherwise.
    """

    return feature_name in [FeatureName.SANBOOT, FeatureName.LOCALBOOT]


def prompt_for_data_volumes_configuration() -> bool:
    """
    Prompt the user to determine if they want to attach additional data volumes.

    This function is called at the end of sanboot and localboot workflows to ask
    if the user wants to configure additional data volumes that will be attached
    after the boot process completes.

    Returns:
        True if the user wants to configure data volumes, False otherwise.
    """

    Console().print()
    Console().print(style_var("Data Volumes Configuration"))
    Console().print(
        "You can optionally configure additional data volumes that will be attached to your instance after the boot process completes."
    )

    return auto_confirm("Would you like to configure additional data volumes?")


def check_is_secondary_workflow(ctx: typer.Context) -> bool:
    """
    Check if the current workflow is a secondary (data volumes) workflow.

    Args:
        ctx: The Typer context object.

    Returns:
        True if this is a secondary workflow, False otherwise.
    """

    return bool(ctx.obj and ctx.obj.get("is_secondary_workflow", False))


def prompt_for_storage_protocol(default_protocol: StorageProtocol) -> StorageProtocol:
    """
    Prompt the user to choose a storage protocol for data volumes.

    Args:
        default_protocol: The default storage protocol to use.

    Returns:
        The selected storage protocol.
    """

    Console().print()
    Console().print("Please choose the storage protocol for your data volumes:")

    # Display protocol options with descriptions
    Console().print(
        f'  {style_var(StorageProtocol.ISCSI.value)} - iSCSI protocol{" (default)" if default_protocol == StorageProtocol.ISCSI else ""}'
    )
    Console().print(
        f'  {style_var(StorageProtocol.NVME.value)} - NVMe over TCP protocol{" (default)" if default_protocol == StorageProtocol.NVME else ""}'
    )

    # Prompt for protocol selection
    choice = cast(str, prompt_with_trim("Enter protocol", default=default_protocol.value, prompt_type=str))

    # Validate and return the selected protocol
    if choice.casefold() == StorageProtocol.ISCSI.value.casefold():
        selected_protocol = StorageProtocol.ISCSI
    elif choice.casefold() == StorageProtocol.NVME.value.casefold():
        selected_protocol = StorageProtocol.NVME
    else:
        Console().print(
            style_var(f'Invalid choice "{choice}". Using default protocol: {default_protocol.value}', color="yellow")
        )
        selected_protocol = default_protocol
    return selected_protocol


def prepare_secondary_workflow_context(
    original_ctx: typer.Context, data_volumes_feature: FeatureName = FeatureName.DATA_VOLUMES
) -> Dict[str, Any]:
    """
    Prepare context for a secondary data volumes workflow.

    This function takes the original workflow context and prepares a new context
    object for executing a data volumes workflow while preserving the necessary
    configuration from the original workflow.

    Args:
        original_ctx: The original Typer context from sanboot/localboot workflow.
        data_volumes_feature: The feature name for the secondary workflow (default: data_volumes).

    Returns:
        A dictionary containing the prepared context for the secondary workflow.
    """

    if not original_ctx.obj:
        raise ValueError("Original context object is missing")

    original_obj = original_ctx.obj

    # Create new context preserving AWS configuration but changing feature
    secondary_context = {
        "is_secondary_workflow": True,
        # Change feature to data_volumes for secondary workflow
        "feature_name": data_volumes_feature,
        "guest_os_type": original_obj.get("guest_os_type"),
        # Preserve AWS configuration
        "aws_client": original_obj.get("aws_client"),
        "outpost_hardware_type": original_obj.get("outpost_hardware_type"),
        "ami_id": original_obj.get("ami_id"),
        "instance_type": original_obj.get("instance_type"),
        "subnet_id": original_obj.get("subnet_id"),
        "key_name": original_obj.get("key_name"),
        "security_group_id": original_obj.get("security_group_id"),
        "instance_profile_name": original_obj.get("instance_profile_name"),
        "instance_name": original_obj.get("instance_name"),
        "root_volume_device_name": original_obj.get("root_volume_device_name"),
        "root_volume_size": original_obj.get("root_volume_size"),
        "root_volume_type": original_obj.get("root_volume_type"),
        # Data volumes workflow specific settings
        "save_user_data_path": None,  # Don't save intermediate user data
        "save_user_data_only": True,  # Only generate user data, don't launch
    }

    return secondary_context
