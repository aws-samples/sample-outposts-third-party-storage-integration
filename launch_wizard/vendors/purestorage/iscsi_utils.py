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


def pure_create_iscsi_host(pure_client: flasharray.Client, host_name: str, initiator_iqn: str) -> None:
    """
    Create a Pure Storage FlashArray iSCSI host with the specified initiator IQN.

    This function creates a new host with the given name and associates it with the
    specified iSCSI initiator IQN. If the host already exists, it adds the IQN to
    the existing host. If the IQN is already in use by another host, it reports an error.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        host_name: Name of the host to create.
        initiator_iqn: iSCSI Initiator Qualified Name to associate with the host.

    Raises:
        typer.Exit: If the host cannot be created, the IQN is already in use by another host,
                   or if a Pure Storage API error occurs.
    """

    try:
        response = pure_client.post_hosts(host=flasharray.HostPost(iqns=[initiator_iqn]), names=[host_name])
        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "Host already exists.":
                Console().print(f"The host {style_var(host_name)} already exists.")
                Console().print("Adding the initiator iSCSI Qualified Name (IQN) to the host.")
                pure_patch_iscsi_host(pure_client, host_name, initiator_iqn)
            elif response.errors[0].message == "The specified IQN is already in use.":
                error_and_exit(
                    f"The initiator iSCSI Qualified Name (IQN) {style_var(initiator_iqn, color='yellow')} is already used by a different host. Please try with a new initiator IQN.",
                    code=ERR_PURE_API,
                )
            else:
                error_and_exit(
                    f"Failed to create iSCSI host {style_var(host_name, color='yellow')} with initiator IQN {style_var(initiator_iqn, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to create iSCSI host {style_var(host_name, color='yellow')} with initiator IQN {style_var(initiator_iqn, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )


def pure_patch_iscsi_host(pure_client: flasharray.Client, host_name: str, initiator_iqn: str) -> None:
    """
    Add an iSCSI initiator IQN to an existing Pure Storage FlashArray host.

    This function adds the specified iSCSI initiator IQN to an existing host.
    If the IQN is already associated with the host, it reports this without error.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        host_name: Name of the existing host to modify.
        initiator_iqn: iSCSI Initiator Qualified Name to add to the host.

    Raises:
        typer.Exit: If the IQN cannot be added to the host or if a Pure Storage API error occurs.
    """

    try:
        response = pure_client.patch_hosts(host=flasharray.HostPatch(add_iqns=[initiator_iqn]), names=[host_name])
        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "The specified IQN is already in use.":
                error_and_exit(
                    f"The initiator iSCSI Qualified Name (IQN) {style_var(initiator_iqn, color='yellow')} is already used by a different host. Please try with a new initiator IQN.",
                    code=ERR_PURE_API,
                )
            else:
                error_and_exit(
                    f"Failed to add the initiator iSCSI Qualified Name (IQN) {style_var(initiator_iqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to add the initiator iSCSI Qualified Name (IQN) {style_var(initiator_iqn, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )


def pure_get_iscsi_target_endpoints_and_iqns(
    pure_client: flasharray.Client, target_endpoints: Optional[List[str]]
) -> List[Dict[str, str]]:
    """
    Retrieve and validate Pure Storage FlashArray iSCSI target endpoints and their IQNs.

    This function gets all available iSCSI target endpoints from the FlashArray and validates
    that the specified endpoints exist. If no endpoints are provided, it displays available
    options and prompts the user to select them.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        target_endpoints: List of target endpoint IP addresses to validate. If None, user will be prompted.

    Returns:
        List of dictionaries containing 'ip', 'port', and 'iqn' keys for each selected target.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints are not available,
                   or if a Pure Storage API error occurs.
    """

    available_iscsi_target_endpoints_and_iqns = pure_get_available_iscsi_target_endpoints_and_iqns(pure_client)

    if not target_endpoints:
        print_table_with_multiple_columns(
            "Available iSCSI target endpoints and IQNs", available_iscsi_target_endpoints_and_iqns
        )
        if auto_confirm("Would you like to use all the listed iSCSI targets?"):
            return available_iscsi_target_endpoints_and_iqns
        else:
            target_endpoints = []
            Console().print("Please enter target endpoints one by one. Press Enter on an empty line when finished.")
            while True:
                target_endpoint = prompt_with_trim(
                    "iSCSI target endpoint (IP address)",
                    default="",
                )
                if target_endpoint == "":
                    break
                target_endpoints.append(target_endpoint)
        validate_ip_list(target_endpoints)

    if len(target_endpoints) == 0:
        error_and_exit(
            "There must be at least one iSCSI target endpoint specified.",
            code=ERR_INPUT_INVALID,
        )

    selected_target_endpoints_and_iqns = []
    for target_endpoint in target_endpoints:
        selected_target_endpoint_and_iqn = find_first_by_property(
            items=available_iscsi_target_endpoints_and_iqns, key="ip", value=target_endpoint
        )
        if selected_target_endpoint_and_iqn:
            selected_target_endpoints_and_iqns.append(selected_target_endpoint_and_iqn)
        else:
            error_and_exit(
                f"Target endpoint {style_var(target_endpoint, color='yellow')} is not available.",
                code=ERR_ENDPOINT_NOT_FOUND,
            )

    return selected_target_endpoints_and_iqns


def pure_get_available_iscsi_target_endpoints_and_iqns(pure_client: flasharray.Client) -> List[Dict[str, str]]:
    """
    Retrieve all available Pure Storage FlashArray iSCSI target endpoints and their IQNs.

    This function queries all network interface ports on the FlashArray and filters them
    to return only those configured for iSCSI, providing the endpoint details needed
    for target configuration.

    Args:
        pure_client: Pure Storage FlashArray client instance.

    Returns:
        List of dictionaries containing 'ip', 'port', and 'iqn' keys for each iSCSI target.

    Raises:
        typer.Exit: If iSCSI target endpoints cannot be retrieved or if a Pure Storage API error occurs.
    """

    available_iscsi_target_endpoints_and_iqns = []
    try:
        network_interface_port_items = pure_client.get_ports().items
        for network_interface_port_item in network_interface_port_items:
            # The properties are "name", "iqn", "nqn", "portal", etc.
            if hasattr(network_interface_port_item, "iqn"):
                ip, port = parse_ip_and_port(network_interface_port_item.portal)
                available_iscsi_target_endpoints_and_iqns.append(
                    {"ip": ip, "port": port, "iqn": network_interface_port_item.iqn}
                )
    except PureError as e:
        error_and_exit(
            "Failed to retrieve available iSCSI target endpoints and IQNs.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )

    return available_iscsi_target_endpoints_and_iqns
