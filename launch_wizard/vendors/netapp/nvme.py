from typing import List, Optional

import typer
from netapp_ontap import HostConnection, config
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
from launch_wizard.vendors.netapp.nvme_utils import (
    netapp_add_host_to_subsystems,
    netapp_get_nvme_interfaces,
    netapp_get_nvme_subsystems,
    netapp_get_subsystems_with_matching_nvme_interfaces,
)


def nvme(
    ctx: typer.Context,
    netapp_management_ip: Annotated[
        str,
        typer.Option(prompt=True, help="NetApp ONTAP management IP", metavar="IP_ADDRESS", callback=validate_ip),
    ],
    netapp_username: Annotated[str, typer.Option(prompt=True, help="NetApp ONTAP management username")],
    netapp_password: Annotated[
        str,
        typer.Option(prompt=True, hide_input=True, help="NetApp ONTAP management password"),
    ],
    host_nqn: Annotated[Optional[str], typer.Option(help="Host NVMe Qualified Name (NQN)")] = None,
    subsystem_names: Annotated[Optional[List[str]], typer.Option(help="Names of NVMe subsystems to connect to")] = None,
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
    Configure and launch an EC2 instance with NetApp ONTAP NVMe storage connectivity.

    This command configures NetApp ONTAP storage systems for NVMe-over-TCP connectivity and launches
    an EC2 instance with the appropriate configuration. It automatically generates a host NQN if not
    provided, adds the host to specified NVMe subsystems, and configures the instance to use the
    NetApp cluster as a discovery controller for automatic NVMe namespace connectivity.

    The launched instance will have user data configured to install nvme-cli and automatically
    connect to all available NVMe subsystems. Note that this may connect to more subsystems than
    specified if there are subsystems configured to allow any host instead of using allowlists.

    Important: The instance must have access to appropriate package repositories for nvme-cli
    installation. For Outpost Servers using public repositories, ensure NAT Gateway connectivity
    is available since instances with multiple network interfaces cannot have public IPs at launch.

    Args:
        ctx: Typer context object containing shared configuration data.
        netapp_management_ip: IP address of the NetApp ONTAP management interface.
        netapp_username: Username for NetApp ONTAP management authentication.
        netapp_password: Password for NetApp ONTAP management authentication.
        host_nqn: NVMe Host Qualified Name for the EC2 instance (optional, will be generated if not provided).
        subsystem_names: List of NVMe subsystem names to connect to (optional, will display available if not provided).
        subsystem_endpoints: List of NVMe subsystem endpoint IP addresses (optional).
        auth_secret_names_raw_input: List of AWS Secrets Manager secret names for subsystem authentication (optional).
        enable_dm_multipath: Whether to enable Device Mapper Multipath for redundant storage paths (optional).

    Raises:
        typer.Exit: If the feature is not supported, NetApp configuration fails, or the user cancels the operation.
    """

    feature_name = ctx.obj["feature_name"]
    guest_os_type = ctx.obj["guest_os_type"]
    validate_feature(feature_name, guest_os_type, StorageProtocol.NVME)

    # Establish a connection to the NetApp cluster
    # TODO: make verify=False optional, currently required as we generally use self signed certs
    config.CONNECTION = HostConnection(netapp_management_ip, netapp_username, netapp_password, verify=False)

    # Verify we have subsystem names, if not provide a list of available ones.
    nvme_subsystems = netapp_get_nvme_subsystems(subsystem_names)

    # If there is no host NQN, generate one or get from user input
    if not host_nqn:
        host_nqn = generate_or_input_host_nqn()
    Console().print(f"Using host NQN: {style_var(host_nqn)}.")

    # Add the host NQN to the subsystems
    nvme_subsystem_uuids = [nvme_subsystem["uuid"] for nvme_subsystem in nvme_subsystems]
    netapp_add_host_to_subsystems(host_nqn, nvme_subsystem_uuids)

    nvme_interfaces = netapp_get_nvme_interfaces(subsystem_endpoints)

    subsystems = netapp_get_subsystems_with_matching_nvme_interfaces(nvme_subsystems, nvme_interfaces)

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
