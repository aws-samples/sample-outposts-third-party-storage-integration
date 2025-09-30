from typing import List, Optional

import typer
from PyPowerStore.powerstore_conn import PowerStoreConn
from rich.console import Console
from typing_extensions import Annotated

from launch_wizard.aws.aws_client import AWSClient
from launch_wizard.aws.ec2 import launch_instance_helper_nvme
from launch_wizard.common.constants import OPTIONAL_VALUE_NONE_PLACEHOLDER
from launch_wizard.common.enums import FeatureName, OperationSystemType, StorageProtocol
from launch_wizard.common.error_codes import ERR_USER_ABORT
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip, validate_ip_list
from launch_wizard.utils.san_utils import generate_or_input_host_nqn
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit
from launch_wizard.utils.user_data_utils import (
    integrate_data_volumes_into_guest_os_scripts,
    process_guest_os_scripts_input,
)
from launch_wizard.utils.validation_utils import (
    assign_auth_secret_names_to_targets,
    validate_auth_secret_names_for_targets,
    validate_enable_dm_multipath,
    validate_feature,
    validate_storage_target_count,
)
from launch_wizard.utils.workflow_orchestrator import (
    check_is_secondary_workflow,
    prompt_for_data_volumes_configuration,
    should_prompt_for_data_volumes_configuration,
)
from launch_wizard.vendors.dell.data_volumes_workflow import execute_data_volumes_workflow
from launch_wizard.vendors.dell.nvme_utils import dell_create_nvme_host, dell_get_nvme_subsystem_endpoints_and_nqns
from launch_wizard.vendors.dell.shared_utils import (
    dell_create_host_group,
    dell_get_host_group_name,
    dell_get_host_name,
    dell_get_volume_ids,
    dell_map_volumes_to_host,
    dell_map_volumes_to_host_group,
)


def nvme(
    ctx: typer.Context,
    dell_management_ip: Annotated[
        str,
        typer.Option(
            prompt=True, help="Dell PowerStore management IP address", metavar="IP_ADDRESS", callback=validate_ip
        ),
    ],
    dell_username: Annotated[str, typer.Option(prompt=True, help="Dell PowerStore management username")],
    dell_password: Annotated[
        str,
        typer.Option(prompt=True, hide_input=True, help="Dell PowerStore management password"),
    ],
    host_group_name: Annotated[Optional[str], typer.Option(help="Name of the host group to use or create")] = None,
    host_name: Annotated[Optional[str], typer.Option(help="Name of the host to use or create")] = None,
    host_nqn: Annotated[Optional[str], typer.Option(help="Host NVMe Qualified Name (NQN)")] = None,
    volume_names: Annotated[
        Optional[List[str]], typer.Option("--volume-name", help="Name of the volume to map")
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
) -> Optional[str]:
    """
    Configure and launch an EC2 instance with Dell PowerStore NVMe storage connectivity.

    This command configures Dell PowerStore storage arrays for NVMe-over-TCP connectivity and launches
    an EC2 instance with the appropriate configuration. It handles host creation, volume mapping,
    subsystem discovery, and authentication setup for high-performance storage integration.

    Args:
        ctx: Typer context object containing shared configuration data.
        dell_management_ip: IP address of the Dell PowerStore management interface.
        dell_username: Username for Dell PowerStore management authentication.
        dell_password: Password for Dell PowerStore management authentication.
        host_group_name: Name of the host group to use or create (optional).
        host_name: Name of the host to use or create (optional).
        host_nqn: NVMe Host Qualified Name for the EC2 instance (optional, will be generated if not provided).
        volume_names: List of volume names to map to the host (optional).
        subsystem_endpoints: List of NVMe subsystem endpoint IP addresses (optional).
        auth_secret_names_raw_input: List of AWS Secrets Manager secret names for subsystem authentication (optional).
        enable_dm_multipath: Whether to enable Device Mapper Multipath for redundant storage paths (optional).
        guest_os_script_paths: List of paths to additional guest OS script files to execute (optional).

    Returns:
        The user data script on the data volumes workflow for SAN boot or LocalBoot.

    Raises:
        typer.Exit: If the feature is not supported, configuration fails, or the user cancels the operation.
    """

    feature_name: FeatureName = ctx.obj["feature_name"]
    guest_os_type: OperationSystemType = ctx.obj["guest_os_type"]
    aws_client: AWSClient = ctx.obj["aws_client"]

    Console().print(f"Starting the Dell NVMe workflow for {style_var(feature_name.value)}...")

    validate_feature(feature_name, guest_os_type, StorageProtocol.NVME)

    Console().print(f"Connecting to the Dell storage device at {style_var(dell_management_ip)}...")
    powerstore_connection = PowerStoreConn(username=dell_username, password=dell_password, server_ip=dell_management_ip)

    volume_ids = dell_get_volume_ids(powerstore_connection, volume_names)

    host_group_name = dell_get_host_group_name(powerstore_connection, host_group_name)

    host_name = dell_get_host_name(powerstore_connection, host_name)

    # If there is no host NQN, generate one or get from user input
    if not host_nqn:
        host_nqn = generate_or_input_host_nqn()
    Console().print(f"{style_var('✓', color='green')} Using the host NQN {style_var(host_nqn)}.")

    # Create a host with the specified name and add the specified host NQN to it
    host_id = dell_create_nvme_host(powerstore_connection, host_name, host_nqn, guest_os_type)
    if host_group_name:
        # Create a host group with the specified name and add the specified host name to it
        host_group_id = dell_create_host_group(powerstore_connection, host_group_name, host_name)

    if host_group_name:
        # Map the volumes to the host group
        dell_map_volumes_to_host_group(powerstore_connection, volume_ids, host_group_name, host_group_id)
    else:
        # Map the volumes to the host
        dell_map_volumes_to_host(powerstore_connection, volume_ids, host_name, host_id)

    subsystems = dell_get_nvme_subsystem_endpoints_and_nqns(powerstore_connection, subsystem_endpoints)

    # Validate storage target count
    validate_storage_target_count(subsystems, feature_name, StorageProtocol.NVME)

    auth_secret_names = validate_auth_secret_names_for_targets(
        auth_secret_names_raw_input, subsystems, "subsystems", aws_client
    )

    # Assign auth secret names to subsystems
    assign_auth_secret_names_to_targets(subsystems, auth_secret_names)

    print_table_with_multiple_columns("NVMe subsystems to be used", subsystems, sort_by="ip")

    if not auto_confirm("Would you like to proceed with launching the instance?", default=True):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    enable_dm_multipath = validate_enable_dm_multipath(enable_dm_multipath)

    # Process guest OS scripts if provided (only applicable for localboot and sanboot)
    guest_os_scripts = process_guest_os_scripts_input(guest_os_script_paths, feature_name, guest_os_type)

    # Check if the user should be prompted for data volumes (for sanboot and localboot workflows)
    if should_prompt_for_data_volumes_configuration(feature_name) and prompt_for_data_volumes_configuration():
        # Execute the data volumes workflow
        data_volumes_script = execute_data_volumes_workflow(
            ctx=ctx,
            default_protocol=StorageProtocol.NVME,
            dell_management_ip=dell_management_ip,
            dell_username=dell_username,
            dell_password=dell_password,
        )

        if data_volumes_script:
            guest_os_scripts = integrate_data_volumes_into_guest_os_scripts(
                guest_os_scripts, data_volumes_script, guest_os_type
            )

    # Check if this is a data volumes workflow that should return user data
    should_return_user_data = check_is_secondary_workflow(ctx)

    return launch_instance_helper_nvme(
        feature_name=feature_name,
        guest_os_type=guest_os_type,
        ec2_client=aws_client.ec2,
        outpost_hardware_type=ctx.obj["outpost_hardware_type"],
        ami_id=ctx.obj["ami_id"],
        instance_type=ctx.obj["instance_type"],
        subnet_id=ctx.obj["subnet_id"],
        key_name=ctx.obj["key_name"],
        security_group_id=ctx.obj["security_group_id"],
        instance_profile_name=ctx.obj["instance_profile_name"],
        instance_name=ctx.obj["instance_name"],
        root_volume_device_name=ctx.obj["root_volume_device_name"],
        root_volume_size=ctx.obj["root_volume_size"],
        root_volume_type=ctx.obj["root_volume_type"],
        host_nqn=host_nqn,
        subsystems=subsystems,
        enable_dm_multipath=enable_dm_multipath,
        guest_os_scripts=guest_os_scripts,
        save_user_data_path=ctx.obj["save_user_data_path"],
        save_user_data_only=ctx.obj["save_user_data_only"],
        should_return_user_data=should_return_user_data,
    )
