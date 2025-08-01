from typing import List, Optional

import typer
from rich.console import Console
from typing_extensions import Annotated

from launch_wizard.aws.ec2 import launch_instance_helper_nvme
from launch_wizard.common.constants import OPTIONAL_VALUE_NONE_PLACEHOLDER
from launch_wizard.common.enums import StorageProtocol
from launch_wizard.common.error_codes import ERR_INPUT_INVALID, ERR_USER_ABORT
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip_and_port_list
from launch_wizard.utils.san_utils import generate_or_input_host_nqn
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim
from launch_wizard.utils.user_data_utils import process_guest_os_scripts_input
from launch_wizard.utils.validation_utils import (
    assign_auth_secret_names_to_targets,
    get_storage_target_limit,
    validate_auth_secret_names_for_targets,
    validate_enable_dm_multipath,
    validate_feature,
    validate_storage_target_count,
)


def nvme(
    ctx: typer.Context,
    host_nqn: Annotated[Optional[str], typer.Option(help="Host NVMe Qualified Name (NQN)")] = None,
    subsystem_nqns: Annotated[
        Optional[List[str]], typer.Option("--subsystem-nqn", help="Subsystem NVMe Qualified Name (NQN)")
    ] = None,
    subsystem_endpoints: Annotated[
        Optional[List[str]],
        typer.Option(
            "--subsystem-endpoint",
            metavar="IP_ADDRESS[:PORT]",
            help="IP address and optional port of the NVMe subsystem endpoint (format: IP or IP:PORT)",
            callback=validate_ip_and_port_list,
        ),
    ] = None,
    auth_secret_names_raw_input: Annotated[
        Optional[List[str]],
        typer.Option(
            "--auth-secret-name",
            help=f'Secret name of the NVMe subsystem credentials in AWS Secrets Manager. Use "{OPTIONAL_VALUE_NONE_PLACEHOLDER}" to represent None values.',
        ),
    ] = None,
    enable_dm_multipath: Annotated[
        Optional[bool], typer.Option(help="Enable Device Mapper Multipath for redundant storage paths")
    ] = None,
    guest_os_script_paths: Annotated[
        Optional[List[str]],
        typer.Option(
            "--guest-os-script",
            help="Path to additional guest OS script files to execute (only applicable for localboot and sanboot features)",
        ),
    ] = None,
):
    """
    Configure and launch an EC2 instance with generic NVMe storage connectivity.

    This command configures generic NVMe-over-TCP storage connectivity and launches an EC2 instance
    with the appropriate configuration. It handles host NQN generation, subsystem configuration,
    and authentication setup for high-performance storage integration with any NVMe-compatible
    storage system.

    Args:
        ctx: Typer context object containing shared configuration data.
        host_nqn: NVMe Host Qualified Name for the EC2 instance (optional, will be generated if not provided).
        subsystem_nqns: List of NVMe Subsystem Qualified Names (optional, will prompt if not provided).
        subsystem_endpoints: List of NVMe subsystem endpoint addresses in IP or IP:PORT format (optional, will prompt if not provided).
        auth_secret_names_raw_input: List of AWS Secrets Manager secret names for subsystem authentication (optional).
        enable_dm_multipath: Whether to enable Device Mapper Multipath for redundant storage paths (optional).

    Raises:
        typer.Exit: If the feature is not supported, subsystem configuration is invalid, or the user cancels the operation.
    """

    feature_name = ctx.obj["feature_name"]
    guest_os_type = ctx.obj["guest_os_type"]
    validate_feature(feature_name, guest_os_type, StorageProtocol.NVME)

    if not host_nqn:
        host_nqn = generate_or_input_host_nqn()
        Console().print(f"Please configure your NVMe subsystem to allow the host NQN: {style_var(host_nqn)}.")
    else:
        Console().print(f"Using host NQN: {style_var(host_nqn)}.")

    allowed_storage_target_limit = get_storage_target_limit(feature_name)

    if not subsystem_nqns:
        subsystem_nqns = []
    if not subsystem_endpoints:
        subsystem_endpoints = []
    if len(subsystem_nqns) == 0 and len(subsystem_endpoints) == 0:
        # Prompt for user input
        Console().print("Enter subsystem information one by one. Press Enter on an empty Subsystem NQN when finished.")
        while allowed_storage_target_limit is None or len(subsystem_nqns) < allowed_storage_target_limit:
            # Only if there is no limit or the limit has not been reached
            subsystem_nqn = prompt_with_trim("Subsystem NQN", default="")
            if subsystem_nqn == "" and len(subsystem_nqns) > 0:
                break
            subsystem_nqns.append(subsystem_nqn)

            subsystem_endpoint = prompt_with_trim("Subsystem endpoint (IP or IP:PORT)", default="")
            subsystem_endpoints.append(subsystem_endpoint)
        validate_ip_and_port_list(subsystem_endpoints)
    elif len(subsystem_nqns) != len(subsystem_endpoints):
        error_and_exit(
            "The number of subsystem NQNs must match the number of subsystem endpoints.", code=ERR_INPUT_INVALID
        )
    else:
        # Validate storage target count
        validate_storage_target_count(subsystem_nqns, feature_name, StorageProtocol.NVME)

    subsystems = []
    for subsystem_nqn, subsystem_endpoint in zip(subsystem_nqns, subsystem_endpoints):
        if ":" in subsystem_endpoint:
            ip, port = subsystem_endpoint.split(":")
            subsystems.append({"ip": ip, "port": port, "nqn": subsystem_nqn})
        else:
            subsystems.append({"ip": subsystem_endpoint, "nqn": subsystem_nqn})

    aws_client = ctx.obj["aws_client"]

    auth_secret_names = validate_auth_secret_names_for_targets(
        auth_secret_names_raw_input, subsystems, "subsystems", aws_client
    )

    # Assign auth secret names to subsystems
    assign_auth_secret_names_to_targets(subsystems, auth_secret_names)

    print_table_with_multiple_columns("NVMe subsystems to be used", subsystems)

    if not auto_confirm("Would you like to proceed with launching the instance?"):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    enable_dm_multipath = validate_enable_dm_multipath(enable_dm_multipath)

    # Process guest OS scripts if provided (only applicable for localboot and sanboot)
    guest_os_scripts = process_guest_os_scripts_input(guest_os_script_paths, feature_name)

    ctx.obj["host_nqn"] = host_nqn
    ctx.obj["subsystems"] = subsystems
    ctx.obj["enable_dm_multipath"] = enable_dm_multipath
    ctx.obj["guest_os_scripts"] = guest_os_scripts

    launch_instance_helper_nvme(
        feature_name=feature_name,
        guest_os_type=guest_os_type,
        ec2_client=aws_client.ec2,
        outpost_hardware_type=ctx.obj["outpost_hardware_type"],
        ami_id=ctx.obj["ami_id"],
        instance_type=ctx.obj["instance_type"],
        subnet_id=ctx.obj["subnet_id"],
        key_name=ctx.obj["key_name"],
        enable_dm_multipath=ctx.obj["enable_dm_multipath"],
        security_group_id=ctx.obj["security_group_id"],
        instance_profile_name=ctx.obj["instance_profile_name"],
        instance_name=ctx.obj["instance_name"],
        root_volume_device_name=ctx.obj["root_volume_device_name"],
        root_volume_size=ctx.obj["root_volume_size"],
        root_volume_type=ctx.obj["root_volume_type"],
        host_nqn=ctx.obj["host_nqn"],
        subsystems=ctx.obj["subsystems"],
        guest_os_scripts=ctx.obj["guest_os_scripts"],
        save_user_data_path=ctx.obj["save_user_data_path"],
        save_user_data_only=ctx.obj["save_user_data_only"],
    )
