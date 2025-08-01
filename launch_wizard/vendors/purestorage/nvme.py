from typing import List, Optional

import typer
from pypureclient import flasharray
from rich.console import Console
from typing_extensions import Annotated

from launch_wizard.aws.ec2 import launch_instance_helper_nvme
from launch_wizard.common.constants import OPTIONAL_VALUE_NONE_PLACEHOLDER
from launch_wizard.common.enums import StorageProtocol
from launch_wizard.common.error_codes import ERR_USER_ABORT
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip, validate_ip_list
from launch_wizard.utils.san_utils import generate_or_input_host_nqn
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit
from launch_wizard.utils.user_data_utils import process_guest_os_scripts_input
from launch_wizard.utils.validation_utils import (
    assign_auth_secret_names_to_targets,
    validate_auth_secret_names_for_targets,
    validate_enable_dm_multipath,
    validate_feature,
    validate_storage_target_count,
)
from launch_wizard.vendors.purestorage.nvme_utils import (
    pure_create_nvme_host,
    pure_get_nvme_subsystem_endpoints_and_nqns,
)
from launch_wizard.vendors.purestorage.shared_utils import (
    pure_connect_volumes_to_host,
    pure_connect_volumes_to_host_group,
    pure_create_host_group,
    pure_get_host_group_name,
    pure_get_host_name,
    pure_get_volume_uuids,
)


def nvme(
    ctx: typer.Context,
    pure_management_ip: Annotated[
        str,
        typer.Option(
            prompt=True,
            help="Pure Storage FlashArray management IP",
            metavar="IP_ADDRESS",
            callback=validate_ip,
        ),
    ],
    pure_api_key: Annotated[
        str,
        typer.Option(
            prompt=True,
            hide_input=True,
            help="API token from Pure Storage web GUI",
        ),
    ],
    host_group_name: Annotated[Optional[str], typer.Option(help="Name of the host group to use or create")] = None,
    host_name: Annotated[Optional[str], typer.Option(help="Name of the host to use or create")] = None,
    host_nqn: Annotated[Optional[str], typer.Option(help="Host NVMe Qualified Name (NQN)")] = None,
    volume_names: Annotated[
        Optional[List[str]], typer.Option("--volume-name", help="Name of the volume to connect")
    ] = None,
    subsystem_endpoints: Annotated[
        Optional[List[str]],
        typer.Option(
            "--subsystem-endpoint",
            metavar="IP_ADDRESS",
            help="IP address of the NVMe subsystem endpoint",
            callback=validate_ip_list,
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
) -> None:
    """
    Configure and launch an EC2 instance with Pure Storage FlashArray NVMe connectivity.

    This command configures Pure Storage FlashArray systems for NVMe-over-TCP connectivity and launches
    an EC2 instance with the appropriate configuration. It automatically generates a host NQN if not
    provided, creates or validates hosts and host groups, connects specified volumes, and configures
    the instance to use the FlashArray as a discovery controller for automatic NVMe namespace connectivity.

    The launched instance will have user data configured to install nvme-cli and automatically
    connect to all available NVMe subsystems. Note that this may connect to more subsystems than
    specified if there are subsystems configured to allow any host instead of using allowlists.

    Important: The instance must have access to appropriate package repositories for nvme-cli
    installation. For Outpost Servers using public repositories, ensure NAT Gateway connectivity
    is available since instances with multiple network interfaces cannot have public IPs at launch.

    Args:
        ctx: Typer context object containing shared configuration data.
        pure_management_ip: IP address of the Pure Storage FlashArray management interface.
        pure_api_key: API token for Pure Storage FlashArray authentication (obtained from web GUI).
        host_group_name: Name of the host group to use or create (optional).
        host_name: Name of the host to use or create (optional).
        host_nqn: NVMe Host Qualified Name for the EC2 instance (optional, will be generated if not provided).
        volume_names: List of volume names to connect to the host (optional, will display available if not provided).
        subsystem_endpoints: List of NVMe subsystem endpoint IP addresses (optional).
        auth_secret_names_raw_input: List of AWS Secrets Manager secret names for subsystem authentication (optional).
        enable_dm_multipath: Whether to enable Device Mapper Multipath for redundant storage paths (optional).

    Raises:
        typer.Exit: If the feature is not supported, Pure Storage configuration fails, or the user cancels the operation.
    """

    feature_name = ctx.obj["feature_name"]
    guest_os_type = ctx.obj["guest_os_type"]
    validate_feature(feature_name, guest_os_type, StorageProtocol.NVME)

    # Create a client instance to communicate with the Pure Storage FlashArray
    pure_client = flasharray.Client(target=pure_management_ip, api_token=pure_api_key)

    # Get the volume UUIDs from the names
    volume_uuids = pure_get_volume_uuids(pure_client, volume_names)

    host_group_name = pure_get_host_group_name(pure_client, host_group_name)

    host_name = pure_get_host_name(pure_client, host_name)

    # If there is no host NQN, generate one or get from user input
    if not host_nqn:
        host_nqn = generate_or_input_host_nqn()
    Console().print(f"Using host NQN: {style_var(host_nqn)}.")

    # Create a host with the specified name and add the specified host NQN to it
    pure_create_nvme_host(pure_client, host_name, host_nqn)
    if host_group_name:
        # Create a host group with the specified name and add the specified host name to it
        pure_create_host_group(pure_client, host_group_name, host_name)

    if host_group_name:
        # Connect the volumes to the host group
        pure_connect_volumes_to_host_group(pure_client, volume_uuids, host_group_name)
    else:
        # Connect the volumes to the host
        pure_connect_volumes_to_host(pure_client, volume_uuids, host_name)

    subsystems = pure_get_nvme_subsystem_endpoints_and_nqns(pure_client, subsystem_endpoints)

    # Validate storage target count
    validate_storage_target_count(subsystems, feature_name, StorageProtocol.NVME)

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
