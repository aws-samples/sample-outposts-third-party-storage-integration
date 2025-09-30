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


def hpe_create_nvme_host(
    hpe_client: HPE3ParClient, host_name: str, host_nqn: str, os_type: OperationSystemType
) -> None:
    """
    Create a new HPE NVMe host or add a host NQN to an existing one.

    This function creates a new host with the specified name and NVMe host NQN, or adds
    the host NQN to an existing host if one with the same name already exists.

    Args:
        hpe_client: Active connection to the HPE system.
        host_name: Name of the host to create or modify.
        host_nqn: NVMe Host Qualified Name to associate with the host.
        os_type: Operating system type of the host (Linux or Windows).

    Raises:
        typer.Exit: If host creation fails or if an HPE API error occurs.
    """

    Console().print(f"Creating the NVMe host {style_var(host_name)} with the host NQN {style_var(host_nqn)}...")

    try:
        Console().print("Checking for an existing host with the same name...")
        try:
            hpe_client.getHost(name=host_name)
            Console().print(f"The host {style_var(host_name)} already exists.")
            Console().print(f"Adding the host NQN {style_var(host_nqn)} to the existing host...")
            hpe_modify_nvme_host(hpe_client, host_name, host_nqn)
        except exceptions.HTTPNotFound:
            Console().print(
                f"Creating the new host {style_var(host_name)} with the OS type {style_var(os_type.value)}..."
            )
            # Host does not exist
            # Create a new one
            hpe_client.createHost(
                name=host_name, nqn=host_nqn, optional={"descriptors": {"os": os_type.value}, "transportType": 2}
            )  # 2 is for NVMe/TCP
            Console().print(f"{style_var('✓', color='green')} Successfully created the host {style_var(host_name)}.")
    except Exception as e:
        error_and_exit(
            f"Failed to create the NVMe host {style_var(host_name, color='yellow')} with the host NQN {style_var(host_nqn, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )


def hpe_modify_nvme_host(hpe_client: HPE3ParClient, host_name: str, host_nqn: str) -> None:
    """
    Add an NVMe host NQN to an existing HPE host.

    This function adds the specified NVMe host NQN to an existing host. If the host NQN
    is already associated with the host, it reports this without error.

    Args:
        hpe_client: Active connection to the HPE system.
        host_name: Name of the existing host to modify.
        host_nqn: NVMe Host Qualified Name to add to the host.

    Raises:
        typer.Exit: If host modification fails or if an HPE API error occurs.
    """

    Console().print(f"Modifying the host {style_var(host_name)} to add the host NQN {style_var(host_nqn)}...")

    try:
        Console().print("Retrieving the host details...")
        host = hpe_client.getHost(name=host_name)

        Console().print("Checking the existing NVMe hosts...")
        existing_host_nqns = [nvme_paths.get("NQN") for nvme_paths in host.get("NVMETCPPaths", [])]
        if host_nqn in existing_host_nqns:
            Console().print(
                f"The host NQN {style_var(host_nqn)} is already associated with the host {style_var(host_name)}."
            )
            Console().print(f"{style_var('✓', color='green')} No changes are needed.")
            return

        error_and_exit(
            f"The host {style_var(host_name, color='yellow')} already exists and is associated with a different NQN {style_var(existing_host_nqns[0], color='yellow')}.",
            "Only one NVMe host NQN can be associated with a host.",
            code=ERR_INPUT_INVALID,
        )
    except Exception as e:
        error_and_exit(
            f"Failed to add the host NQN {style_var(host_nqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )


def hpe_get_nvme_subsystem_endpoints_and_nqns(
    hpe_client: HPE3ParClient, subsystem_endpoints: Optional[List[str]], host_name: str
) -> List[Dict[str, str]]:
    """
    Retrieve and validate HPE NVMe subsystem endpoints and their NQNs.

    This function gets all available NVMe subsystem endpoints from the HPE system and
    validates that the specified endpoints exist. If no endpoints are provided, it displays
    available options and prompts the user to select them.

    Args:
        hpe_client: Active connection to the HPE system.
        subsystem_endpoints: List of subsystem endpoint IP addresses. If None, user will be prompted.
        host_name: Name of the host to get subsystem endpoints for.

    Returns:
        List of dictionaries containing 'ip' and 'nqn' keys for each subsystem endpoint.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints don't exist,
                    or if an HPE API error occurs.
    """

    Console().print("Retrieving and validating NVMe subsystem endpoints...")

    Console().print("Fetching available NVMe subsystem endpoints...")
    available_nvme_subsystem_endpoints_and_nqns = hpe_get_available_nvme_subsystem_endpoints_and_nqns(
        hpe_client, host_name
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


def hpe_get_available_nvme_subsystem_endpoints_and_nqns(
    hpe_client: HPE3ParClient, host_name: str
) -> List[Dict[str, str]]:
    """
    Retrieve all available HPE NVMe subsystem endpoints and their NQNs.

    This function queries the HPE system to get all IP pool addresses configured
    for NVMe-over-TCP service and retrieves their corresponding subsystem NQNs from
    cluster details.

    Args:
        hpe_client: Active connection to the HPE system.
        host_name: Name of the host to get subsystem endpoints for.

    Returns:
        List of dictionaries containing 'ip' and 'nqn' keys for each available subsystem endpoint.

    Raises:
        typer.Exit: If subsystem endpoints cannot be retrieved or if an HPE API error occurs.
    """

    Console().print("Scanning ports for NVMe services...")
    available_nvme_subsystem_endpoints_and_nqns = []

    try:
        Console().print("Retrieving existing ports...")
        existing_ports = hpe_client.getPorts().get("members", [])
    except Exception as e:
        error_and_exit(
            "Failed to retrieve existing ports.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )

    Console().print(f"Found {style_var(len(existing_ports))} ports to examine.")
    available_ips = set()
    for port in existing_ports:
        if (
            port.get("protocol") == HPE3ParClient.PORT_PROTO_NVME
            and port.get("linkState") == HPE3ParClient.PORT_STATE_READY
        ):
            node_wwn = port.get("nodeWWN")
            Console().print(f"  Processing the NVMe endpoint {style_var(node_wwn)}...")
            available_ips.add(node_wwn)
            Console().print(f"    {style_var('✓', color='green')} Found available NVMe port.")

    Console().print("Retrieving existing VLUNs...")
    try:
        available_vluns = hpe_client.getVLUNs().get("members", [])
    except Exception as e:
        error_and_exit(
            "Failed to retrieve existing VLUNs.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )

    Console().print(f"Found {style_var(len(available_vluns))} VLUNs to examine.")
    available_nqns = set()
    for vlun in available_vluns:
        if vlun.get("hostname") == host_name:
            subsystem_nqn = vlun.get("Subsystem_NQN")
            Console().print(f"  Processing VLUN for host {style_var(host_name)}...")
            available_nqns.add(subsystem_nqn)
            Console().print(f"    {style_var('✓', color='green')} Found the subsystem NQN {style_var(subsystem_nqn)}.")

    Console().print("Creating endpoint combinations from available IPs and NQNs...")
    # Create a Cartesian product of available IPs and NQNs
    for ip in available_ips:
        for nqn in available_nqns:
            available_nvme_subsystem_endpoints_and_nqns.append({"ip": ip, "nqn": nqn})

    Console().print(
        f"{style_var('✓', color='green')} Successfully discovered {style_var(len(available_nvme_subsystem_endpoints_and_nqns))} NVMe subsystem endpoints."
    )
    return available_nvme_subsystem_endpoints_and_nqns
