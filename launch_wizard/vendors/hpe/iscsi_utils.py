from typing import Dict, List, Optional

from hpe3parclient import exceptions
from hpe3parclient.client import HPE3ParClient
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.enums import OperationSystemType
from launch_wizard.common.error_codes import ERR_ENDPOINT_NOT_FOUND, ERR_HPE_API, ERR_INPUT_INVALID
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip_list
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def hpe_create_iscsi_host(
    hpe_client: HPE3ParClient, host_name: str, initiator_iqn: str, os_type: OperationSystemType
) -> None:
    """
    Create a new HPE iSCSI host or add an initiator to an existing one.

    This function creates a new host with the specified name and iSCSI initiator IQN, or adds
    the initiator IQN to an existing host if one with the same name already exists.

    Args:
        hpe_client: Active connection to the HPE system.
        host_name: Name of the host to create or modify.
        initiator_iqn: iSCSI Initiator Qualified Name to associate with the host.
        os_type: Operating system type of the host (Linux or Windows).

    Raises:
        typer.Exit: If host creation fails or if an HPE API error occurs.
    """

    Console().print(
        f"Creating the iSCSI host {style_var(host_name)} with the initiator IQN {style_var(initiator_iqn)}..."
    )

    try:
        Console().print("Checking for an existing host with the same name...")
        try:
            hpe_client.getHost(name=host_name)
            Console().print(f"The host {style_var(host_name)} already exists.")
            Console().print(f"Adding the initiator IQN {style_var(initiator_iqn)} to the existing host...")
            hpe_modify_iscsi_host(hpe_client, host_name, initiator_iqn)
        except exceptions.HTTPNotFound:
            Console().print(
                f"Creating the new host {style_var(host_name)} with the OS type {style_var(os_type.value)}..."
            )
            # Host does not exist
            # Create a new one
            hpe_client.createHost(
                name=host_name, iscsiNames=[initiator_iqn], optional={"descriptors": {"os": os_type.value}}
            )
            Console().print(f"{style_var('✓', color='green')} Successfully created the host {style_var(host_name)}.")
    except Exception as e:
        error_and_exit(
            f"Failed to create the iSCSI host {style_var(host_name, color='yellow')} with the initiator IQN {style_var(initiator_iqn, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )


def hpe_modify_iscsi_host(hpe_client: HPE3ParClient, host_name: str, initiator_iqn: str) -> None:
    """
    Add an iSCSI initiator IQN to an existing HPE host.

    This function adds the specified iSCSI initiator IQN to an existing host. If the initiator
    is already associated with the host, it reports this without error.

    Args:
        hpe_client: Active connection to the HPE system.
        host_name: Name of the existing host to modify.
        initiator_iqn: iSCSI Initiator Qualified Name to add to the host.

    Raises:
        typer.Exit: If host modification fails or if an HPE API error occurs.
    """

    Console().print(f"Modifying the host {style_var(host_name)} to add the initiator IQN {style_var(initiator_iqn)}...")

    try:
        Console().print("Retrieving the host details...")
        host = hpe_client.getHost(name=host_name)

        Console().print("Checking the existing iSCSI initiators...")
        existing_initiator_iqns = [iscsi_path.get("name") for iscsi_path in host.get("iSCSIPaths", [])]
        if initiator_iqn in existing_initiator_iqns:
            Console().print(
                f"The initiator IQN {style_var(initiator_iqn)} is already associated with the host {style_var(host_name)}."
            )
            Console().print(f"{style_var('✓', color='green')} No changes are needed.")
            return

        Console().print(f"Adding a new initiator IQN {style_var(initiator_iqn)} to the host...")
        hpe_client.modifyHost(
            name=host_name, mod_request={"pathOperation": HPE3ParClient.HOST_EDIT_ADD, "iSCSINames": [initiator_iqn]}
        )
        Console().print(
            f"{style_var('✓', color='green')} Successfully added the initiator IQN {style_var(initiator_iqn)} to the host {style_var(host_name)}."
        )
    except Exception as e:
        error_and_exit(
            f"Failed to add the initiator IQN {style_var(initiator_iqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )


def hpe_get_iscsi_target_endpoints_and_iqns(
    hpe_client: HPE3ParClient, target_endpoints: Optional[List[str]]
) -> List[Dict[str, str]]:
    """
    Retrieve and validate HPE iSCSI target endpoints and their IQNs.

    This function gets all available iSCSI target endpoints from the HPE system and
    validates that the specified endpoints exist. If no endpoints are provided, it displays
    available options and prompts the user to select them.

    Args:
        hpe_client: Active connection to the HPE system.
        target_endpoints: List of target endpoint IP addresses. If None, user will be prompted.

    Returns:
        List of dictionaries containing 'ip' and 'iqn' keys for each target endpoint.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints don't exist,
                    or if an HPE API error occurs.
    """

    Console().print("Retrieving and validating iSCSI target endpoints...")

    Console().print("Fetching available iSCSI target endpoints...")
    available_iscsi_target_endpoints_and_iqns = hpe_get_available_iscsi_target_endpoints_and_iqns(hpe_client)

    if not target_endpoints:
        Console().print(
            f"Found {style_var(len(available_iscsi_target_endpoints_and_iqns))} available iSCSI target endpoints."
        )
        print_table_with_multiple_columns(
            "Available iSCSI target endpoints and IQNs", available_iscsi_target_endpoints_and_iqns, sort_by="ip"
        )
        if auto_confirm("Would you like to use all the listed iSCSI targets?", default=True):
            Console().print(f"{style_var('✓', color='green')} Using all available iSCSI target endpoints.")
            return available_iscsi_target_endpoints_and_iqns
        else:
            target_endpoints = []
            Console().print("Enter the target endpoints one by one. Press Enter on an empty line when finished.")
            while True:
                target_endpoint = prompt_with_trim(
                    "Target endpoint IP address",
                    default="",
                    show_default=False,
                )
                if target_endpoint == "":
                    break
                target_endpoints.append(target_endpoint)
        Console().print("Validating the manually entered IP addresses...")
        validate_ip_list(target_endpoints)

    if len(target_endpoints) == 0:
        error_and_exit(
            "You must specify at least one iSCSI target endpoint to continue.",
            code=ERR_INPUT_INVALID,
        )

    Console().print(f"Validating {style_var(len(target_endpoints))} specified iSCSI target endpoints...")
    selected_target_endpoints_and_iqns = []
    for target_endpoint in target_endpoints:
        Console().print(f"  Checking the endpoint {style_var(target_endpoint)}...")
        selected_target_endpoint_and_iqn = find_first_by_property(
            items=available_iscsi_target_endpoints_and_iqns, key="ip", value=target_endpoint
        )
        if selected_target_endpoint_and_iqn:
            selected_target_endpoints_and_iqns.append(selected_target_endpoint_and_iqn)
            Console().print(
                f"    {style_var('✓', color='green')} Found the iSCSI target IQN {style_var(selected_target_endpoint_and_iqn['iqn'])}."
            )
        else:
            error_and_exit(
                f"The iSCSI target endpoint {style_var(target_endpoint, color='yellow')} is not available.",
                code=ERR_ENDPOINT_NOT_FOUND,
            )

    Console().print(
        f"{style_var('✓', color='green')} Successfully validated {style_var(len(selected_target_endpoints_and_iqns))} iSCSI target endpoints."
    )
    return selected_target_endpoints_and_iqns


def hpe_get_available_iscsi_target_endpoints_and_iqns(hpe_client: HPE3ParClient) -> List[Dict[str, str]]:
    """
    Retrieve all available HPE iSCSI target endpoints and their IQNs.

    This function queries the HPE system to get all IP pool addresses configured
    for iSCSI service and retrieves their corresponding target IQNs.

    Args:
        hpe_client: Active connection to the HPE system.

    Returns:
        List of dictionaries containing 'ip' and 'iqn' keys for each available target endpoint.

    Raises:
        typer.Exit: If target endpoints cannot be retrieved or if an HPE API error occurs.
    """

    Console().print("Scanning ports for iSCSI services...")
    available_iscsi_target_endpoints_and_iqns = []
    try:
        ports_response = hpe_client.getPorts()
        ports = ports_response.get("members", [])
        Console().print(f"Found {style_var(len(ports))} ports to examine.")

        for port in ports:
            if (
                port.get("protocol") == HPE3ParClient.PORT_PROTO_ISCSI
                and port.get("linkState") == HPE3ParClient.PORT_STATE_READY
            ):
                ip_address = port.get("IPAddr")
                target_iqn = port.get("iSCSIName")

                Console().print(f"  Processing the iSCSI endpoint {style_var(ip_address)}...")
                available_iscsi_target_endpoints_and_iqns.append(
                    {
                        "ip": ip_address,
                        "iqn": target_iqn,
                    }
                )
                Console().print(
                    f"    {style_var('✓', color='green')} Found the iSCSI target IQN {style_var(target_iqn)}."
                )

        Console().print(
            f"{style_var('✓', color='green')} Successfully discovered {style_var(len(available_iscsi_target_endpoints_and_iqns))} iSCSI target endpoints."
        )
    except Exception as e:
        error_and_exit(
            "Failed to retrieve available iSCSI target endpoints and IQNs.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )

    return available_iscsi_target_endpoints_and_iqns
