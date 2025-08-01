from typing import List, Optional

import typer
from rich.console import Console
from typing_extensions import Annotated

from launch_wizard.aws.ec2 import launch_instance_helper_iscsi
from launch_wizard.common.constants import OPTIONAL_VALUE_NONE_PLACEHOLDER
from launch_wizard.common.enums import StorageProtocol
from launch_wizard.common.error_codes import ERR_INPUT_INVALID, ERR_USER_ABORT
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip_and_port_list
from launch_wizard.utils.san_utils import generate_discovery_portals, generate_or_input_initiator_iqn
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim
from launch_wizard.utils.user_data_utils import process_guest_os_scripts_input
from launch_wizard.utils.validation_utils import (
    assign_auth_secret_names_to_targets,
    assign_lun_to_targets,
    get_storage_target_limit,
    validate_auth_secret_names_for_targets,
    validate_feature,
    validate_lun_for_feature,
    validate_storage_target_count,
)


def iscsi(
    ctx: typer.Context,
    initiator_iqn: Annotated[Optional[str], typer.Option(help="Initiator iSCSI Qualified Name (IQN)")] = None,
    target_iqns: Annotated[
        Optional[List[str]], typer.Option("--target-iqn", help="Target iSCSI Qualified Name (IQN)")
    ] = None,
    target_endpoints: Annotated[
        Optional[List[str]],
        typer.Option(
            "--target-endpoint",
            metavar="IP_ADDRESS[:PORT]",
            help="IP address and optional port of the iSCSI target endpoint (format: IP or IP:PORT)",
            callback=validate_ip_and_port_list,
        ),
    ] = None,
    auth_secret_names_raw_input: Annotated[
        Optional[List[str]],
        typer.Option(
            "--auth-secret-name",
            help=f'Secret name of the iSCSI target credentials in AWS Secrets Manager. Use "{OPTIONAL_VALUE_NONE_PLACEHOLDER}" to represent None values.',
        ),
    ] = None,
    discovery_portal_auth_secret_names_raw_input: Annotated[
        Optional[List[str]],
        typer.Option(
            "--discovery-portal-auth-secret-name",
            help=f'Secret name of the iSCSI discovery portal credentials in AWS Secrets Manager. Use "{OPTIONAL_VALUE_NONE_PLACEHOLDER}" to represent None values.',
        ),
    ] = None,
    lun: Annotated[
        Optional[int], typer.Option(help="Logical Unit Number (LUN) for SAN boot and LocalBoot (0-255)")
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
    Configure and launch an EC2 instance with generic iSCSI storage connectivity.

    This command configures generic iSCSI storage connectivity and launches an EC2 instance
    with the appropriate configuration. It handles initiator IQN generation, target configuration,
    discovery portal setup, and authentication for flexible storage integration with any
    iSCSI-compatible storage system.

    Args:
        ctx: Typer context object containing shared configuration data.
        initiator_iqn: iSCSI Initiator Qualified Name for the EC2 instance (optional, will be generated if not provided).
        target_iqns: List of iSCSI Target Qualified Names (optional, will prompt if not provided).
        target_endpoints: List of iSCSI target endpoint addresses in IP or IP:PORT format (optional, will prompt if not provided).
        auth_secret_names_raw_input: List of AWS Secrets Manager secret names for target authentication (optional).
        discovery_portal_auth_secret_names_raw_input: List of AWS Secrets Manager secret names for discovery portal authentication (optional).
        lun: Logical Unit Number for SAN boot and LocalBoot features (optional, 0-255).

    Raises:
        typer.Exit: If the feature is not supported, target configuration is invalid, or the user cancels the operation.
    """

    feature_name = ctx.obj["feature_name"]
    guest_os_type = ctx.obj["guest_os_type"]
    validate_feature(feature_name, guest_os_type, StorageProtocol.ISCSI)

    if not initiator_iqn:
        initiator_iqn = generate_or_input_initiator_iqn()
        Console().print(f"Please configure your iSCSI target to allow the initiator IQN: {style_var(initiator_iqn)}.")
    else:
        Console().print(f"Using initiator IQN: {style_var(initiator_iqn)}.")

    allowed_storage_target_limit = get_storage_target_limit(feature_name)

    if not target_iqns:
        target_iqns = []
    if not target_endpoints:
        target_endpoints = []
    if len(target_iqns) == 0 and len(target_endpoints) == 0:
        # Prompt for user input
        Console().print("Enter target information one by one. Press Enter on an empty Target IQN when finished.")
        while allowed_storage_target_limit is None or len(target_iqns) < allowed_storage_target_limit:
            # Only if there is no limit or the limit has not been reached
            target_iqn = prompt_with_trim("Target IQN", default="")
            if target_iqn == "" and len(target_iqns) > 0:
                break
            target_iqns.append(target_iqn)

            target_endpoint = prompt_with_trim("Target endpoint (IP or IP:PORT)", default="")
            target_endpoints.append(target_endpoint)
        validate_ip_and_port_list(target_endpoints)
    elif len(target_iqns) != len(target_endpoints):
        error_and_exit("The number of target IQNs must match the number of target endpoints.", code=ERR_INPUT_INVALID)
    else:
        # Validate storage target count
        validate_storage_target_count(target_iqns, feature_name, StorageProtocol.ISCSI)

    targets = []
    for target_iqn, target_endpoint in zip(target_iqns, target_endpoints):
        if ":" in target_endpoint:
            ip, port = target_endpoint.split(":")
            targets.append({"ip": ip, "port": port, "iqn": target_iqn})
        else:
            targets.append({"ip": target_endpoint, "iqn": target_iqn})

    lun = validate_lun_for_feature(lun, feature_name)

    # Assign LUN to targets if specified
    assign_lun_to_targets(targets, lun)

    aws_client = ctx.obj["aws_client"]

    auth_secret_names = validate_auth_secret_names_for_targets(
        auth_secret_names_raw_input, targets, "targets", aws_client
    )

    # Assign auth secret names to targets
    assign_auth_secret_names_to_targets(targets, auth_secret_names)

    portals = generate_discovery_portals(targets)

    discovery_portal_auth_secret_names = validate_auth_secret_names_for_targets(
        discovery_portal_auth_secret_names_raw_input,
        portals,
        "discovery portals",
        aws_client,
    )

    # Assign auth secret names to discovery portals
    assign_auth_secret_names_to_targets(portals, discovery_portal_auth_secret_names)

    print_table_with_multiple_columns("iSCSI targets to be used", targets)

    print_table_with_multiple_columns("iSCSI discovery portals to be used", portals)

    if not auto_confirm("Would you like to proceed with launching the instance?"):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    # Process guest OS scripts if provided (only applicable for localboot and sanboot)
    guest_os_scripts = process_guest_os_scripts_input(guest_os_script_paths, feature_name)

    ctx.obj["initiator_iqn"] = initiator_iqn
    ctx.obj["targets"] = targets
    ctx.obj["portals"] = portals
    ctx.obj["guest_os_scripts"] = guest_os_scripts

    launch_instance_helper_iscsi(
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
        initiator_iqn=ctx.obj["initiator_iqn"],
        targets=ctx.obj["targets"],
        portals=ctx.obj["portals"],
        guest_os_scripts=ctx.obj["guest_os_scripts"],
        save_user_data_path=ctx.obj["save_user_data_path"],
        save_user_data_only=ctx.obj["save_user_data_only"],
    )
