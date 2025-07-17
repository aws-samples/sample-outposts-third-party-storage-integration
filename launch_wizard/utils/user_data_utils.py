"""
User data template rendering and processing utility functions.
"""

import os
from typing import Any, Dict, List, cast

import chevron
from rich.console import Console

from launch_wizard.constants import ERR_USER_DATA_NOT_FOUND
from launch_wizard.enums import FeatureName, OperationSystemType, StorageProtocol

from .data_utils import snake_to_camel, transform_keys
from .display_utils import style_var
from .ui_utils import error_and_exit


def get_user_data_template_path(
    feature_name: FeatureName, guest_os_type: OperationSystemType, protocol: StorageProtocol
) -> str:
    """
    Returns the path to the user data template for a feature.

    Args:
        feature_name: The feature name.
        guest_os_type: The guest operating system type.
        protocol: The storage protocol.

    Returns:
        The path to the user data template file.

    Raises:
        FileNotFoundError: If the template file is not found.
    """

    directory_path = os.path.normpath("launch_wizard/user_data_templates")
    file_path = ""

    if feature_name == FeatureName.DATA_VOLUMES:
        file_path = os.path.join(
            directory_path, f"{feature_name.value}_{protocol.value}_{guest_os_type.value}.mustache"
        )
    elif feature_name == FeatureName.LOCALBOOT:
        file_path = os.path.join(directory_path, f"{feature_name.value}.mustache")
    elif feature_name == FeatureName.SANBOOT:
        file_path = os.path.join(directory_path, f"{feature_name.value}_{protocol.value}.mustache")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"User data template not found at path: {file_path}.")

    Console().print(f"Using user data template: {style_var(file_path)}.")
    return file_path


def render_user_data(
    feature_name: FeatureName,
    guest_os_type: OperationSystemType,
    protocol: StorageProtocol,
    input_data: Dict[str, Any],
) -> str:
    """
    Renders the user data template for a feature.

    Args:
        feature_name: The feature name.
        guest_os_type: The guest operating system type.
        protocol: The storage protocol.
        input_data: The input data for template rendering.

    Returns:
        The rendered user data string.

    Raises:
        typer.Exit: If no user data template data is provided.
    """

    # Get the path to the user data template
    user_data_template_path = get_user_data_template_path(feature_name, guest_os_type, protocol)

    user_data_template_data = {**input_data}

    if feature_name == FeatureName.SANBOOT:
        user_data_template_data["isMultipart"] = True

    if feature_name == FeatureName.LOCALBOOT:
        user_data_template_data["dataVolumesAttachmentScript"] = render_user_data(
            FeatureName.DATA_VOLUMES,
            OperationSystemType.LINUX,
            protocol,
            {**input_data},
        )
        if protocol == StorageProtocol.ISCSI:
            user_data_template_data["bootTarget"] = cast(List[Dict[str, str]], input_data.get("targets"))[0].get("iqn")
            user_data_template_data["bootLun"] = cast(List[Dict[str, str]], input_data.get("targets"))[0].get("lun")
        elif protocol == StorageProtocol.NVME:
            user_data_template_data["bootTarget"] = cast(List[Dict[str, str]], input_data.get("subsystems"))[0].get(
                "nqn"
            )

    # Some keys, such as `auth_secret_name`, are in snake_case
    # They need to be transformed into camelCase for the user data template
    user_data_template_data = transform_keys(user_data_template_data, snake_to_camel)

    if not user_data_template_data:
        error_and_exit(
            "No user data template data provided. This is required for instance configuration.",
            code=ERR_USER_DATA_NOT_FOUND,
        )

    # Render the template
    with open(user_data_template_path, "r", encoding="utf-8") as template:
        user_data = chevron.render(template, user_data_template_data)
    return user_data
