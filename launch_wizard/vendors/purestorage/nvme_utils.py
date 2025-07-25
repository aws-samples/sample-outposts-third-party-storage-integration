from typing import Dict, List, Optional

from pypureclient import flasharray
from pypureclient.exceptions import PureError
from pypureclient.responses import ErrorResponse
from rich.console import Console
from rich.pretty import Pretty
from rich.rule import Rule

from launch_wizard.common.error_codes import ERR_ENDPOINT_NOT_FOUND, ERR_INPUT_INVALID, ERR_PURE_API
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import parse_ip_and_port, validate_ip_list
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def pure_create_nvme_host(pure_client: flasharray.Client, host_name: str, host_nqn: str) -> None:
    """
    Create a Pure Storage FlashArray NVMe host with the specified host NQN.

    This function creates a new host with the given name and associates it with the
    specified NVMe host NQN. If the host already exists, it adds the NQN to the
    existing host. If the NQN is already in use by another host, it reports an error.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        host_name: Name of the host to create.
        host_nqn: NVMe Host Qualified Name to associate with the host.

    Raises:
        typer.Exit: If the host cannot be created, the NQN is already in use by another host,
                   or if a Pure Storage API error occurs.
    """

    try:
        response = pure_client.post_hosts(host=flasharray.HostPost(nqns=[host_nqn]), names=[host_name])
        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "Host already exists.":
                Console().print(f"The host {style_var(host_name)} already exists.")
                Console().print("Adding the NVMe Qualified Name (NQN) to the host.")
                pure_patch_nvme_host(pure_client, host_name, host_nqn)
            elif response.errors[0].message == "The specified host NQN is already in use.":
                error_and_exit(
                    f"The NVMe Qualified Name (NQN) {style_var(host_nqn, color='yellow')} is already used by a different host. Please try with a new host NQN.",
                    code=ERR_PURE_API,
                )
            else:
                error_and_exit(
                    f"Failed to create NVMe host {style_var(host_name, color='yellow')} with NQN {style_var(host_nqn, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to create NVMe host {style_var(host_name, color='yellow')} with NQN {style_var(host_nqn, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )


def pure_patch_nvme_host(pure_client: flasharray.Client, host_name: str, host_nqn: str) -> None:
    """
    Add an NVMe host NQN to an existing Pure Storage FlashArray host.

    This function adds the specified NVMe host NQN to an existing host.
    If the NQN is already associated with the host, it reports this without error.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        host_name: Name of the existing host to modify.
        host_nqn: NVMe Host Qualified Name to add to the host.

    Raises:
        typer.Exit: If the NQN cannot be added to the host or if a Pure Storage API error occurs.
    """

    try:
        response = pure_client.patch_hosts(host=flasharray.HostPatch(add_nqns=[host_nqn]), names=[host_name])
        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "The specified NQN is already in use.":
                error_and_exit(
                    f"The NVMe Qualified Name (NQN) {style_var(host_nqn, color='yellow')} is already used by a different host. Please try with a new host NQN.",
                    code=ERR_PURE_API,
                )
            else:
                error_and_exit(
                    f"Failed to add the NVMe Qualified Name (NQN) {style_var(host_nqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to add the NVMe Qualified Name (NQN) {style_var(host_nqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )


def pure_get_nvme_subsystem_endpoints_and_nqns(
    pure_client: flasharray.Client, subsystem_endpoints: Optional[List[str]]
) -> List[Dict[str, str]]:
    """
    Retrieve and validate Pure Storage FlashArray NVMe subsystem endpoints and their NQNs.

    This function gets all available NVMe subsystem endpoints from the FlashArray and validates
    that the specified endpoints exist. If no endpoints are provided, it displays available
    options and prompts the user to select them.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        subsystem_endpoints: List of subsystem endpoint IP addresses to validate. If None, user will be prompted.

    Returns:
        List of dictionaries containing 'ip', 'port', and 'nqn' keys for each selected subsystem.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints are not available,
                   or if a Pure Storage API error occurs.
    """

    available_nvme_subsystem_endpoints_and_nqns = pure_get_available_nvme_subsystem_endpoints_and_nqns(pure_client)

    if not subsystem_endpoints:
        print_table_with_multiple_columns(
            "Available NVMe subsystem endpoints and NQNs", available_nvme_subsystem_endpoints_and_nqns
        )
        if auto_confirm("Would you like to use all the listed NVMe subsystems?"):
            return available_nvme_subsystem_endpoints_and_nqns
        else:
            subsystem_endpoints = []
            Console().print("Please enter subsystem endpoints one by one. Press Enter on an empty line when finished.")
            while True:
                subsystem_endpoint = prompt_with_trim(
                    "NVMe subsystem endpoint (IP address)",
                    default="",
                )
                if subsystem_endpoint == "":
                    break
                subsystem_endpoints.append(subsystem_endpoint)
        validate_ip_list(subsystem_endpoints)

    if len(subsystem_endpoints) == 0:
        error_and_exit("There must be at least one NVMe subsystem endpoint specified.", code=ERR_INPUT_INVALID)

    selected_subsystem_endpoints_and_nqns = []
    for subsystem_endpoint in subsystem_endpoints:
        selected_subsystem_endpoint_and_nqn = find_first_by_property(
            items=available_nvme_subsystem_endpoints_and_nqns, key="ip", value=subsystem_endpoint
        )
        if selected_subsystem_endpoint_and_nqn:
            selected_subsystem_endpoints_and_nqns.append(selected_subsystem_endpoint_and_nqn)
        else:
            error_and_exit(
                f"Subsystem endpoint {style_var(subsystem_endpoint, color='yellow')} is not available.",
                code=ERR_ENDPOINT_NOT_FOUND,
            )

    return selected_subsystem_endpoints_and_nqns


def pure_get_available_nvme_subsystem_endpoints_and_nqns(pure_client: flasharray.Client) -> List[Dict[str, str]]:
    """
    Retrieve all available Pure Storage FlashArray NVMe subsystem endpoints and their NQNs.

    This function queries all network interface ports on the FlashArray and filters them
    to return only those configured for NVMe, providing the endpoint details needed
    for subsystem configuration.

    Args:
        pure_client: Pure Storage FlashArray client instance.

    Returns:
        List of dictionaries containing 'ip', 'port', and 'nqn' keys for each NVMe subsystem.

    Raises:
        typer.Exit: If NVMe subsystem endpoints cannot be retrieved or if a Pure Storage API error occurs.
    """

    available_nvme_subsystem_endpoints_and_nqns = []
    try:
        network_interface_port_items = pure_client.get_ports().items
        for network_interface_port_item in network_interface_port_items:
            # The properties are "name", "iqn", "nqn", "portal", etc.
            if hasattr(network_interface_port_item, "nqn"):
                ip, port = parse_ip_and_port(network_interface_port_item.portal)
                available_nvme_subsystem_endpoints_and_nqns.append(
                    {"ip": ip, "port": port, "nqn": network_interface_port_item.nqn}
                )
    except PureError as e:
        error_and_exit(
            "Failed to retrieve available NVMe subsystem endpoints and NQNs.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )

    return available_nvme_subsystem_endpoints_and_nqns
