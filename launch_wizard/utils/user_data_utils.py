"""
User data template rendering and processing utility functions.
"""

import os
from typing import Any, Dict, List, Optional, cast

import chevron
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.enums import FeatureName, OperationSystemType, OutpostHardwareType, StorageProtocol
from launch_wizard.common.error_codes import (
    ERR_GUEST_OS_SCRIPT_NOT_FOUND,
    ERR_GUEST_OS_SCRIPT_READ_FAILED,
    ERR_USER_ABORT,
    ERR_USER_DATA_NOT_FOUND,
)

from .data_utils import snake_to_camel, transform_keys
from .display_utils import style_var
from .ui_utils import auto_confirm, error_and_exit, prompt_with_trim


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


def generate_user_data_iscsi(
    feature_name: FeatureName,
    guest_os_type: OperationSystemType,
    outpost_hardware_type: OutpostHardwareType,
    initiator_iqn: str,
    targets: List[Dict[str, str]],
    portals: List[Dict[str, str]],
    guest_os_scripts: Optional[List[Dict[str, str]]],
) -> str:
    """
    Generate user data script for iSCSI storage connectivity.

    This function creates a user data script specifically configured for iSCSI storage
    connections based on the provided configuration parameters.

    Args:
        feature_name: The storage feature being configured (data_volumes, localboot, or sanboot).
        guest_os_type: The operating system type (linux or windows).
        outpost_hardware_type: The type of Outpost hardware (RACK or SERVER).
        initiator_iqn: The iSCSI initiator qualified name for the instance.
        targets: List of iSCSI target configurations.
        portals: List of iSCSI portal configurations for discovery.
        guest_os_scripts: List of additional guest OS scripts to include in user data (optional).

    Returns:
        The generated user data script as a string.
    """

    # Render userdata from template
    user_data_inputs: Dict[str, Any] = {
        "initiatorIQN": initiator_iqn,
        "portals": portals,
        "targets": targets,
        "guestOsScripts": guest_os_scripts,
        "isOutpostServer": outpost_hardware_type == OutpostHardwareType.SERVER,
        "lniIndex": 1,
    }

    return render_user_data(feature_name, guest_os_type, StorageProtocol.ISCSI, user_data_inputs)


def generate_user_data_nvme(
    feature_name: FeatureName,
    guest_os_type: OperationSystemType,
    host_nqn: str,
    subsystems: List[Dict[str, str]],
    enable_dm_multipath: Optional[bool],
    guest_os_scripts: Optional[List[Dict[str, str]]],
) -> str:
    """
    Generate user data script for NVMe storage connectivity.

    This function creates a user data script specifically configured for NVMe storage
    connections based on the provided configuration parameters.

    Args:
        feature_name: The storage feature being configured (data_volumes, localboot, or sanboot).
        guest_os_type: The operating system type (linux or windows).
        host_nqn: The NVMe host qualified name for the instance.
        subsystems: List of NVMe subsystem configurations.
        enable_dm_multipath: Whether to enable Device Mapper Multipath (optional).
        guest_os_scripts: List of additional guest OS scripts to include in user data (optional).

    Returns:
        The generated user data script as a string.
    """

    # Render userdata from template
    user_data_inputs: Dict[str, Any] = {
        "hostNQN": host_nqn,
        "subsystems": subsystems,
        "guestOsScripts": guest_os_scripts,
        "dmMultipath": enable_dm_multipath,
    }

    return render_user_data(feature_name, guest_os_type, StorageProtocol.NVME, user_data_inputs)


def save_user_data_path_to_file(user_data: str, file_path: str) -> str:
    """
    Save user data script to a local file.

    This function saves the generated user data script to a local file. If no file path
    is provided, it prompts the user to enter one. It creates the directory if it doesn't exist.

    Args:
        user_data: The user data script content to save.
        file_path: The file path to save to.

    Returns:
        The actual file path where the user data was saved.

    Raises:
        typer.Exit: If file writing fails or the user cancels the operation.
    """

    # Expand user directory (~) if present
    file_path = os.path.expanduser(file_path)

    # Create directory if it doesn't exist
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        try:
            os.makedirs(directory, exist_ok=True)
            Console().print(f"Created directory: {style_var(directory)}")
        except OSError as e:
            error_and_exit(f"Failed to create directory {directory}: {e}", code=ERR_GUEST_OS_SCRIPT_READ_FAILED)

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(user_data)
        Console().print(f"User data script saved to: {style_var(file_path)}")
        return file_path
    except OSError as e:
        error_and_exit(f"Failed to save user data to {file_path}: {e}", code=ERR_GUEST_OS_SCRIPT_READ_FAILED)


def process_guest_os_scripts(script_paths: Optional[List[str]]) -> List[Dict[str, str]]:
    """
    Process guest OS script files and return them in the format expected by user data templates.

    This function reads script files from the provided paths and determines their content type
    based on the file extension or content. The returned format matches the TypeScript interface:
    {type: "text/cloud-config" | "text/x-shellscript"; content: string}[]

    Args:
        script_paths: List of file paths to script files. Can be None or empty.

    Returns:
        List of dictionaries with 'type' and 'content' keys for each script.

    Raises:
        typer.Exit: If a script file cannot be read or has an unsupported format.
    """

    if not script_paths:
        return []

    guest_os_scripts = []

    for script_path in script_paths:
        try:
            # Check if file exists
            if not os.path.exists(script_path):
                error_and_exit(
                    f"Guest OS script file not found: {style_var(script_path, color='yellow')}",
                    code=ERR_GUEST_OS_SCRIPT_NOT_FOUND,
                )

            # Read file content
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                Console().print(f"Warning: Guest OS script file {style_var(script_path)} is empty, skipping.")
                continue

            # Determine content type based on file extension and content
            content_type = _determine_script_content_type(script_path, content)

            guest_os_scripts.append({"type": content_type, "content": content})

            Console().print(f"Added guest OS script: {style_var(script_path)} (type: {style_var(content_type)})")
        except IOError as e:
            error_and_exit(
                f"Failed to read guest OS script file {style_var(script_path, color='yellow')}",
                Rule(),
                str(e),
                code=ERR_GUEST_OS_SCRIPT_READ_FAILED,
            )

    return guest_os_scripts


def _determine_script_content_type(file_path: str, content: str) -> str:
    """
    Determine the MIME content type for a script based on file extension and content.

    Args:
        file_path: Path to the script file.
        content: Content of the script file.

    Returns:
        The MIME content type string.
    """

    # Get file extension
    _, ext = os.path.splitext(file_path.lower())

    # Check for cloud-config based on extension or content
    if ext in [".yml", ".yaml"] or content.startswith("#cloud-config"):
        return "text/cloud-config"

    # Check for shell script based on extension or shebang
    if ext in [".sh", ".bash"] or content.startswith("#!/"):
        return "text/x-shellscript"

    # Default to shell script for unknown types
    Console().print(f"Warning: Unknown script type for {style_var(file_path)}, treating as shell script.")
    return "text/x-shellscript"


def process_guest_os_scripts_input(
    guest_os_script_paths: Optional[List[str]], feature_name: FeatureName
) -> List[Dict[str, str]]:
    """
    Process guest OS scripts for vendor subcommands with feature validation.

    This function handles the common pattern of processing guest OS scripts in vendor subcommands,
    including validation that scripts are only used with localboot and sanboot features.
    If no scripts are provided and the feature supports scripts, the user will be prompted
    interactively to either proceed without scripts or provide script file paths.

    Args:
        guest_os_script_paths: List of file paths to script files. Can be None or empty.
        feature_name: The current feature being used.

    Returns:
        List of dictionaries with 'type' and 'content' keys for each script.
        Returns empty list if no scripts provided or feature doesn't support scripts.

    Raises:
        typer.Exit: If a script file cannot be read or has an unsupported format,
                   or if the user aborts the operation.
    """

    guest_os_scripts: List[Dict[str, str]] = []

    # Check if the feature supports guest OS scripts
    if feature_name not in [FeatureName.LOCALBOOT, FeatureName.SANBOOT]:
        if guest_os_script_paths:
            Console().print(
                f"Warning: Guest OS scripts are only supported for {style_var('localboot')} and {style_var('sanboot')} features. Scripts will be ignored."
            )
        return guest_os_scripts

    # If no scripts provided and feature supports them, prompt the user
    if not guest_os_script_paths:
        Console().print(
            f"No guest OS scripts specified. Guest OS scripts can be used to customize the guest OS configuration after {style_var('LocalBoot')} or {style_var('SAN boot')}."
        )

        if auto_confirm("Would you like to proceed without specifying guest OS scripts?"):
            return guest_os_scripts

        # User wants to specify scripts, prompt for them
        Console().print("Please provide guest OS script file paths. Press Enter on an empty line when finished.")
        script_paths: List[str] = []

        while True:
            script_path = prompt_with_trim(
                f"Guest OS script file path {len(script_paths) + 1} (or press Enter to finish)", default=""
            )

            if not script_path:
                break

            # Validate the file exists
            if not os.path.exists(script_path):
                Console().print(f"Warning: File {style_var(script_path)} does not exist. Please try again.")
                continue

            script_paths.append(script_path)
            Console().print(f"Added script: {style_var(script_path)}")

        if not script_paths:
            if auto_confirm("No scripts were specified. Would you like to proceed without guest OS scripts?"):
                return guest_os_scripts
            else:
                error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

        guest_os_script_paths = script_paths

    # Process the provided scripts
    if guest_os_script_paths:
        guest_os_scripts = process_guest_os_scripts(guest_os_script_paths)

    return guest_os_scripts
