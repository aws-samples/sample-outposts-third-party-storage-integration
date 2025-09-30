from typing import Dict, List, Optional

from PyPowerStore.powerstore_conn import PowerStoreConn
from PyPowerStore.utils import constants as powerstore_constants
from PyPowerStore.utils import helpers as powerstore_helpers
from PyPowerStore.utils.exception import PowerStoreException
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.constants import DELL_NVME_TCP_SERVICE_NAME
from launch_wizard.common.enums import OperationSystemType
from launch_wizard.common.error_codes import ERR_DELL_API, ERR_ENDPOINT_NOT_FOUND, ERR_INPUT_INVALID
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip_list
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def dell_create_nvme_host(
    powerstore_connection: PowerStoreConn, host_name: str, host_nqn: str, os_type: OperationSystemType
) -> str:
    """
    Create a new Dell PowerStore NVMe host or add a host NQN to an existing one.

    This function creates a new host with the specified name and NVMe host NQN, or adds
    the host NQN to an existing host if one with the same name already exists.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_name: Name of the host to create or modify.
        host_nqn: NVMe Host Qualified Name to associate with the host.
        os_type: Operating system type of the host (Linux or Windows).

    Returns:
        The ID of the created or modified host.

    Raises:
        typer.Exit: If host creation fails or if a PowerStore API error occurs.
    """

    Console().print(f"Creating the NVMe host {style_var(host_name)} with the host NQN {style_var(host_nqn)}...")

    try:
        Console().print("Checking for an existing host with the same name...")
        hosts_with_matching_name = powerstore_connection.provisioning.get_host_by_name(host_name=host_name)
        if hosts_with_matching_name:
            Console().print(f"The host {style_var(host_name)} already exists.")
            Console().print(f"Adding the host NQN {style_var(host_nqn)} to the existing host...")
            return dell_modify_nvme_host(powerstore_connection, host_name, host_nqn)
        else:
            Console().print(
                f"Creating the new host {style_var(host_name)} with the OS type {style_var(os_type.value)}..."
            )
            initiator = {
                "port_name": host_nqn,
                "port_type": "NVMe",
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
            f"Failed to create the NVMe host {style_var(host_name, color='yellow')} with the host NQN {style_var(host_nqn, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )


def dell_modify_nvme_host(powerstore_connection: PowerStoreConn, host_name: str, host_nqn: str) -> str:
    """
    Add an NVMe host NQN to an existing Dell PowerStore host.

    This function adds the specified NVMe host NQN to an existing host. If the host NQN
    is already associated with the host, it reports this without error.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_name: Name of the existing host to modify.
        host_nqn: NVMe Host Qualified Name to add to the host.

    Returns:
        The ID of the modified host.

    Raises:
        typer.Exit: If host modification fails or if a PowerStore API error occurs.
    """

    Console().print(f"Modifying the host {style_var(host_name)} to add the host NQN {style_var(host_nqn)}...")

    try:
        Console().print("Retrieving the host details...")
        host = powerstore_connection.provisioning.get_host_by_name(host_name)[0]
        host_id = host["id"]

        Console().print("Checking the existing NVMe hosts...")
        host_details = powerstore_connection.provisioning.get_host_details(host_id=host_id)
        if host_details["initiators"]:
            for initiator in host_details["initiators"]:
                if initiator["port_name"] == host_nqn:
                    Console().print(
                        f"The host NQN {style_var(host_nqn)} is already associated with the host {style_var(host_name)}."
                    )
                    Console().print(f"{style_var('✓', color='green')} No changes are needed.")
                    return host_id

        Console().print(f"Adding a new host NQN {style_var(host_nqn)} to the host...")
        initiator = {
            "port_name": host_nqn,
            "port_type": "NVMe",
        }
        powerstore_connection.provisioning.modify_host(host_id=host_id, add_initiators=[initiator])
        Console().print(
            f"{style_var('✓', color='green')} Successfully added the host NQN {style_var(host_nqn)} to the host {style_var(host_name)}."
        )
        return host_id
    except PowerStoreException as e:
        error_and_exit(
            f"Failed to add the host NQN {style_var(host_nqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )


def dell_get_nvme_subsystem_endpoints_and_nqns(
    powerstore_connection: PowerStoreConn, subsystem_endpoints: Optional[List[str]]
) -> List[Dict[str, str]]:
    """
    Retrieve and validate Dell PowerStore NVMe subsystem endpoints and their NQNs.

    This function gets all available NVMe subsystem endpoints from the PowerStore system and
    validates that the specified endpoints exist. If no endpoints are provided, it displays
    available options and prompts the user to select them.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        subsystem_endpoints: List of subsystem endpoint IP addresses. If None, user will be prompted.

    Returns:
        List of dictionaries containing 'ip' and 'nqn' keys for each subsystem endpoint.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints don't exist,
                    or if a PowerStore API error occurs.
    """

    Console().print("Retrieving and validating NVMe subsystem endpoints...")

    Console().print("Fetching available NVMe subsystem endpoints...")
    available_nvme_subsystem_endpoints_and_nqns = dell_get_available_nvme_subsystem_endpoints_and_nqns(
        powerstore_connection
    )

    if not subsystem_endpoints:
        Console().print(
            f"Found {style_var(len(available_nvme_subsystem_endpoints_and_nqns))} available NVMe subsystem endpoints."
        )
        print_table_with_multiple_columns(
            "Available NVMe subsystem endpoints and NQNs", available_nvme_subsystem_endpoints_and_nqns, sort_by="ip"
        )
        if auto_confirm("Would you like to use all the listed NVMe subsystems?", default=True):
            Console().print(f"{style_var('✓', color='green')} Using all available NVMe subsystem endpoints.")
            return available_nvme_subsystem_endpoints_and_nqns
        else:
            subsystem_endpoints = []
            Console().print("Enter the subsystem endpoints one by one. Press Enter on an empty line when finished.")
            while True:
                subsystem_endpoint = prompt_with_trim(
                    "Subsystem endpoint IP address",
                    default="",
                    show_default=False,
                )
                if subsystem_endpoint == "":
                    break
                subsystem_endpoints.append(subsystem_endpoint)
        Console().print("Validating the manually entered IP addresses...")
        validate_ip_list(subsystem_endpoints)

    if len(subsystem_endpoints) == 0:
        error_and_exit("You must specify at least one NVMe subsystem endpoint to continue.", code=ERR_INPUT_INVALID)

    Console().print(f"Validating {style_var(len(subsystem_endpoints))} specified NVMe subsystem endpoints...")
    selected_subsystem_endpoints_and_nqns = []
    for subsystem_endpoint in subsystem_endpoints:
        Console().print(f"  Checking the endpoint {style_var(subsystem_endpoint)}...")
        selected_subsystem_endpoint_and_nqn = find_first_by_property(
            items=available_nvme_subsystem_endpoints_and_nqns, key="ip", value=subsystem_endpoint
        )
        if selected_subsystem_endpoint_and_nqn:
            selected_subsystem_endpoints_and_nqns.append(selected_subsystem_endpoint_and_nqn)
            Console().print(
                f"    {style_var('✓', color='green')} Found the NVMe subsystem NQN {style_var(selected_subsystem_endpoint_and_nqn['nqn'])}."
            )
        else:
            error_and_exit(
                f"The NVMe subsystem endpoint {style_var(subsystem_endpoint, color='yellow')} is not available.",
                code=ERR_ENDPOINT_NOT_FOUND,
            )

    Console().print(
        f"{style_var('✓', color='green')} Successfully validated {style_var(len(selected_subsystem_endpoints_and_nqns))} NVMe subsystem endpoints."
    )
    return selected_subsystem_endpoints_and_nqns


def dell_get_available_nvme_subsystem_endpoints_and_nqns(powerstore_connection: PowerStoreConn) -> List[Dict[str, str]]:
    """
    Retrieve all available Dell PowerStore NVMe subsystem endpoints and their NQNs.

    This function queries the PowerStore system to get all IP pool addresses configured
    for NVMe-over-TCP service and retrieves their corresponding subsystem NQNs from
    cluster details.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.

    Returns:
        List of dictionaries containing 'ip' and 'nqn' keys for each available subsystem endpoint.

    Raises:
        typer.Exit: If subsystem endpoints cannot be retrieved or if a PowerStore API error occurs.
    """

    Console().print("Retrieving cluster details for NVMe subsystem details...")
    cluster_details_list = []
    try:
        for cluster in powerstore_connection.config_mgmt.get_clusters():
            cluster_details = dell_get_cluster_details_with_nvme_subsystem_nqn(powerstore_connection, cluster["id"])
            cluster_details_list.append(cluster_details)
    except PowerStoreException as e:
        error_and_exit("Failed to retrieve the cluster details.", Rule(), str(e), code=ERR_DELL_API)

    Console().print("Scanning IP pool addresses for NVMe services...")
    available_nvme_subsystem_endpoints_and_nqns = []
    try:
        ip_pool_addresses = powerstore_connection.config_mgmt.get_ip_pool_address()
        Console().print(f"Found {style_var(len(ip_pool_addresses))} IP pool addresses to examine.")

        for ip_pool_address in ip_pool_addresses:
            # If the IP pool address is used for NVMe/TCP,
            # use its IP address
            if DELL_NVME_TCP_SERVICE_NAME in ip_pool_address["purposes"]:
                ip_address = ip_pool_address["address"]
                Console().print(f"  Processing the NVMe endpoint {style_var(ip_address)}...")

                cluster_details_with_matching_appliance_id = find_first_by_property(
                    items=cluster_details_list, key="master_appliance_id", value=ip_pool_address["appliance_id"]
                )
                if cluster_details_with_matching_appliance_id:
                    subsystem_nqn = cluster_details_with_matching_appliance_id["nvm_subsystem_nqn"]
                    available_nvme_subsystem_endpoints_and_nqns.append(
                        {
                            "ip": ip_address,
                            "nqn": subsystem_nqn,
                        }
                    )
                    Console().print(
                        f"    {style_var('✓', color='green')} Found the NVMe subsystem NQN {style_var(subsystem_nqn)}."
                    )
                else:
                    Console().print(
                        f"The NVMe subsystem NQN is not available for IP pool address {style_var(ip_pool_address['name'])}."
                    )

        Console().print(
            f"{style_var('✓', color='green')} Successfully discovered {style_var(len(available_nvme_subsystem_endpoints_and_nqns))} NVMe subsystem endpoints."
        )
    except PowerStoreException as e:
        error_and_exit(
            "Failed to retrieve available NVMe subsystem endpoints and NQNs.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )

    return available_nvme_subsystem_endpoints_and_nqns


def dell_get_cluster_details_with_nvme_subsystem_nqn(
    powerstore_connection: PowerStoreConn, cluster_id: str
) -> Dict[str, str]:
    """
    Retrieve Dell PowerStore cluster details including the NVMe subsystem NQN.

    This function extends the standard cluster details query to include the NVMe subsystem NQN,
    which is required for NVMe-over-TCP connectivity configuration.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        cluster_id: ID of the cluster to retrieve details for.

    Returns:
        Dictionary containing cluster details including the NVMe subsystem NQN.

    Raises:
        PowerStoreException: If the cluster details cannot be retrieved.
    """

    # Copied from the original get_cluster_details() function
    querystring = powerstore_constants.CLUSTER_DETAILS_QUERY
    if powerstore_helpers.is_foot_hill_or_higher():
        querystring = {
            "select": "id,global_id,name,management_address,"
            "storage_discovery_address,master_appliance_id,"
            "appliance_count,physical_mtu,is_encryption_enabled,"
            "compatibility_level,state,state_l10n,system_time",
        }

    # Add nvm_subsystem_nqn to the querystring to get the subsystem NQN
    querystring["select"] += ",nvm_subsystem_nqn"

    # Copied from the original get_cluster_details() function
    return powerstore_connection.config_mgmt.config_client.request(
        powerstore_constants.GET,
        powerstore_constants.GET_CLUSTER_DETAILS_URL.format(powerstore_connection.config_mgmt.server_ip, cluster_id),
        querystring=querystring,
    )
