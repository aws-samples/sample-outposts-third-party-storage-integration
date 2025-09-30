from typing import Dict, List, Optional

from PyPowerStore.powerstore_conn import PowerStoreConn
from PyPowerStore.utils.exception import PowerStoreException
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.constants import DELL_ISCSI_SERVICE_NAME
from launch_wizard.common.enums import OperationSystemType
from launch_wizard.common.error_codes import ERR_DELL_API, ERR_ENDPOINT_NOT_FOUND, ERR_INPUT_INVALID
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip_list
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def dell_create_iscsi_host(
    powerstore_connection: PowerStoreConn, host_name: str, initiator_iqn: str, os_type: OperationSystemType
) -> str:
    """
    Create a new Dell PowerStore iSCSI host or add an initiator to an existing one.

    This function creates a new host with the specified name and iSCSI initiator IQN, or adds
    the initiator IQN to an existing host if one with the same name already exists.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_name: Name of the host to create or modify.
        initiator_iqn: iSCSI Initiator Qualified Name to associate with the host.
        os_type: Operating system type of the host (Linux or Windows).

    Returns:
        The ID of the created or modified host.

    Raises:
        typer.Exit: If host creation fails or if a PowerStore API error occurs.
    """

    Console().print(
        f"Creating the iSCSI host {style_var(host_name)} with the initiator IQN {style_var(initiator_iqn)}..."
    )

    try:
        Console().print("Checking for an existing host with the same name...")
        hosts_with_matching_name = powerstore_connection.provisioning.get_host_by_name(host_name=host_name)
        if hosts_with_matching_name:
            Console().print(f"The host {style_var(host_name)} already exists.")
            Console().print(f"Adding the initiator IQN {style_var(initiator_iqn)} to the existing host...")
            return dell_modify_iscsi_host(powerstore_connection, host_name, initiator_iqn)
        else:
            Console().print(
                f"Creating the new host {style_var(host_name)} with the OS type {style_var(os_type.value)}..."
            )
            initiator = {
                "port_name": initiator_iqn,
                "port_type": "iSCSI",
            }
            os_type_string = "Linux" if os_type == OperationSystemType.LINUX else "Windows"
            host = powerstore_connection.provisioning.create_host(
                name=host_name, os_type=os_type_string, initiators=[initiator]
            )
            Console().print(
                f"{style_var('✓', color='green')} Successfully created the host {style_var(host_name)} with ID {style_var(host['id'])}."
            )
            return host["id"]
    except PowerStoreException as e:
        error_and_exit(
            f"Failed to create the iSCSI host {style_var(host_name, color='yellow')} with the initiator IQN {style_var(initiator_iqn, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )


def dell_modify_iscsi_host(powerstore_connection: PowerStoreConn, host_name: str, initiator_iqn: str) -> str:
    """
    Add an iSCSI initiator IQN to an existing Dell PowerStore host.

    This function adds the specified iSCSI initiator IQN to an existing host. If the initiator
    is already associated with the host, it reports this without error.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_name: Name of the existing host to modify.
        initiator_iqn: iSCSI Initiator Qualified Name to add to the host.

    Returns:
        The ID of the modified host.

    Raises:
        typer.Exit: If host modification fails or if a PowerStore API error occurs.
    """

    Console().print(f"Modifying the host {style_var(host_name)} to add the initiator IQN {style_var(initiator_iqn)}...")

    try:
        Console().print("Retrieving the host details...")
        host = powerstore_connection.provisioning.get_host_by_name(host_name)[0]
        host_id = host["id"]

        Console().print("Checking the existing iSCSI initiators...")
        host_details = powerstore_connection.provisioning.get_host_details(host_id=host_id)
        if host_details["initiators"]:
            for initiator in host_details["initiators"]:
                if initiator["port_name"] == initiator_iqn:
                    Console().print(
                        f"The initiator IQN {style_var(initiator_iqn)} is already associated with the host {style_var(host_name)}."
                    )
                    Console().print(f"{style_var('✓', color='green')} No changes are needed.")
                    return host_id

        Console().print(f"Adding a new initiator IQN {style_var(initiator_iqn)} to the host...")
        initiator = {
            "port_name": initiator_iqn,
            "port_type": "iSCSI",
        }
        powerstore_connection.provisioning.modify_host(host_id, add_initiators=[initiator])
        Console().print(
            f"{style_var('✓', color='green')} Successfully added the initiator IQN {style_var(initiator_iqn)} to the host {style_var(host_name)}."
        )
        return host_id
    except PowerStoreException as e:
        error_and_exit(
            f"Failed to add the initiator IQN {style_var(initiator_iqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )


def dell_get_iscsi_target_endpoints_and_iqns(
    powerstore_connection: PowerStoreConn, target_endpoints: Optional[List[str]]
) -> List[Dict[str, str]]:
    """
    Retrieve and validate Dell PowerStore iSCSI target endpoints and their IQNs.

    This function gets all available iSCSI target endpoints from the PowerStore system and
    validates that the specified endpoints exist. If no endpoints are provided, it displays
    available options and prompts the user to select them.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        target_endpoints: List of target endpoint IP addresses. If None, user will be prompted.

    Returns:
        List of dictionaries containing 'ip' and 'iqn' keys for each target endpoint.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints don't exist,
                    or if a PowerStore API error occurs.
    """

    Console().print("Retrieving and validating iSCSI target endpoints...")

    Console().print("Fetching available iSCSI target endpoints...")
    available_iscsi_target_endpoints_and_iqns = dell_get_available_iscsi_target_endpoints_and_iqns(
        powerstore_connection
    )

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


def dell_get_available_iscsi_target_endpoints_and_iqns(powerstore_connection: PowerStoreConn) -> List[Dict[str, str]]:
    """
    Retrieve all available Dell PowerStore iSCSI target endpoints and their IQNs.

    This function queries the PowerStore system to get all IP pool addresses configured
    for iSCSI service and retrieves their corresponding target IQNs.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.

    Returns:
        List of dictionaries containing 'ip' and 'iqn' keys for each available target endpoint.

    Raises:
        typer.Exit: If target endpoints cannot be retrieved or if a PowerStore API error occurs.
    """

    Console().print("Scanning IP pool addresses for iSCSI services...")
    available_iscsi_target_endpoints_and_iqns = []
    try:
        ip_pool_addresses = powerstore_connection.config_mgmt.get_ip_pool_address()
        Console().print(f"Found {style_var(len(ip_pool_addresses))} IP pool addresses to examine.")

        for ip_pool_address in ip_pool_addresses:
            # If the IP pool address is used for iSCSI and the IP port ID property exists,
            # use the IP port ID to look up the details
            if DELL_ISCSI_SERVICE_NAME in ip_pool_address["purposes"] and ip_pool_address["ip_port_id"]:
                ip_address = ip_pool_address["address"]
                Console().print(f"  Processing the iSCSI endpoint {style_var(ip_address)}...")

                ip_port_id = ip_pool_address["ip_port_id"]
                ip_port_details = powerstore_connection.config_mgmt.get_ip_port_details(ip_port_id=ip_port_id)
                target_iqn = ip_port_details["target_iqn"]

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
    except PowerStoreException as e:
        error_and_exit(
            "Failed to retrieve available iSCSI target endpoints and IQNs.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )

    return available_iscsi_target_endpoints_and_iqns
