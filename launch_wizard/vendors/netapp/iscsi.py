from typing import List, Optional

import typer
from netapp_ontap import HostConnection, config
from rich.console import Console
from typing_extensions import Annotated

from launch_wizard.aws.ec2 import launch_instance_helper_iscsi
from launch_wizard.common.constants import OPTIONAL_VALUE_NONE_PLACEHOLDER
from launch_wizard.common.enums import StorageProtocol
from launch_wizard.common.error_codes import ERR_USER_ABORT
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip, validate_ip_list
from launch_wizard.utils.san_utils import generate_discovery_portals, generate_or_input_initiator_iqn
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit
from launch_wizard.utils.user_data_utils import process_guest_os_scripts_input
from launch_wizard.utils.validation_utils import (
    assign_auth_secret_names_to_targets,
    assign_lun_to_targets,
    validate_auth_secret_names_for_targets,
    validate_feature,
    validate_lun_for_feature,
    validate_storage_target_count,
)
from launch_wizard.vendors.netapp.iscsi_utils import (
    netapp_add_initiator_iqn_to_igroup,
    netapp_create_igroup,
    netapp_get_svm_name_and_target_iqn,
    netapp_get_target_endpoints,
    netapp_map_luns_to_igroup,
)


def iscsi(
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
    igroup_name: Annotated[Optional[str], typer.Option(help="Name of the initiator group to use or create")] = None,
    initiator_iqn: Annotated[Optional[str], typer.Option(help="Initiator iSCSI Qualified Name (IQN)")] = None,
    svm_name: Annotated[
        Optional[str],
        typer.Option(help="NetApp Storage Virtual Machine (SVM) that hosts the iSCSI LUNs to connect to"),
    ] = None,
    lun_paths: Annotated[Optional[List[str]], typer.Option("--lun-path", help="Path to the LUN to map")] = None,
    target_endpoints: Annotated[
        Optional[List[str]],
        typer.Option(
            "--target-endpoint",
            metavar="IP_ADDRESS",
            help="IP address of the iSCSI target endpoint",
            callback=validate_ip_list,
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
) -> None:
    """
    Configure and launch an EC2 instance with NetApp ONTAP iSCSI storage connectivity.

    This command configures NetApp ONTAP storage systems for iSCSI connectivity and launches
    an EC2 instance with the appropriate configuration. It handles Storage Virtual Machine (SVM)
    validation, initiator group creation, LUN mapping, and authentication setup for seamless
    integration with NetApp storage arrays.

    Args:
        ctx: Typer context object containing shared configuration data.
        netapp_management_ip: IP address of the NetApp ONTAP management interface.
        netapp_username: Username for NetApp ONTAP management authentication.
        netapp_password: Password for NetApp ONTAP management authentication.
        igroup_name: Name of the initiator group to use or create (optional).
        initiator_iqn: iSCSI Initiator Qualified Name for the EC2 instance (optional, will be generated if not provided).
        svm_name: Name of the Storage Virtual Machine that hosts the iSCSI LUNs (optional).
        lun_paths: List of LUN paths to map to the initiator group (optional).
        target_endpoints: List of iSCSI target endpoint IP addresses (optional).
        auth_secret_names_raw_input: List of AWS Secrets Manager secret names for target authentication (optional).
        discovery_portal_auth_secret_names_raw_input: List of AWS Secrets Manager secret names for discovery portal authentication (optional).
        lun: Logical Unit Number for SAN boot and LocalBoot features (optional, 0-255).

    Raises:
        typer.Exit: If the feature is not supported, NetApp configuration fails, or the user cancels the operation.
    """

    feature_name = ctx.obj["feature_name"]
    guest_os_type = ctx.obj["guest_os_type"]
    validate_feature(feature_name, guest_os_type, StorageProtocol.ISCSI)

    # Establish a connection to the NetApp cluster
    # TODO: make verify=False optional, currently required as we generally use self signed certs
    config.CONNECTION = HostConnection(netapp_management_ip, netapp_username, netapp_password, verify=False)

    target_iqn = ""

    # Validate SVM and grab target iqn for the SVM
    svm_name, target_iqn = netapp_get_svm_name_and_target_iqn(svm_name)

    # Validate igroup name
    igroup_name = netapp_create_igroup(svm_name, igroup_name, guest_os_type)

    # If there is no initiator IQN, generate one or get user input
    if not initiator_iqn:
        initiator_iqn = generate_or_input_initiator_iqn()
    Console().print(f"Using initiator IQN: {style_var(initiator_iqn)}.")

    # Add the initiator IQN to the igroup
    netapp_add_initiator_iqn_to_igroup(svm_name, igroup_name, initiator_iqn)

    # Map specified LUNs to igroup
    netapp_map_luns_to_igroup(svm_name, igroup_name, lun_paths)

    target_endpoints = netapp_get_target_endpoints(svm_name, target_endpoints)

    # Generate config for instance launch
    targets = []
    for target_endpoint in target_endpoints:
        if ":" in target_endpoint:
            ip, port = target_endpoint.split(":")
            targets.append({"ip": ip, "port": port, "iqn": target_iqn})
        else:
            targets.append({"ip": target_endpoint, "iqn": target_iqn})

    # Validate storage target count
    validate_storage_target_count(targets, feature_name, StorageProtocol.ISCSI)

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
