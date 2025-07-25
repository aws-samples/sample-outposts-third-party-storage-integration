from typing import Dict, List, Optional

from netapp_ontap.error import NetAppRestError
from netapp_ontap.resources import NvmeInterface, NvmeSubsystem, NvmeSubsystemHost
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.constants import NETAPP_DUPLICATE_NQN_ERR_CODE, NETAPP_NVME_TCP_PROTOCOL_NAME
from launch_wizard.common.error_codes import (
    ERR_ENDPOINT_NOT_FOUND,
    ERR_INPUT_INVALID,
    ERR_NETAPP_API,
    ERR_SUBSYSTEM_NOT_FOUND,
    ERR_USER_ABORT,
)
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.network_utils import validate_ip_list
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def netapp_get_nvme_subsystems(nvme_subsystem_names: Optional[List[str]]) -> List[Dict[str, str]]:
    """
    Retrieve and validate NetApp NVMe subsystems by name.

    This function retrieves information about NVMe subsystems from the NetApp cluster.
    If no subsystem names are provided, it displays all available subsystems and prompts
    the user to select them interactively. It validates that all specified subsystems exist
    and returns their details including UUIDs and NQNs.

    Args:
        nvme_subsystem_names: List of NVMe subsystem names to retrieve. If None, user will be prompted.

    Returns:
        List of dictionaries containing subsystem details (name, uuid, nqn, svm_name).

    Raises:
        typer.Exit: If no subsystems are specified, specified subsystems don't exist,
                   the user cancels the operation, or if a NetApp API error occurs.
    """

    available_nvme_subsystems = []
    try:
        for nvme_subsystem in NvmeSubsystem.get_collection():
            nvme_subsystem.get()
            available_nvme_subsystems.append(
                {
                    "name": nvme_subsystem.name,
                    "uuid": nvme_subsystem.uuid,
                    "nqn": nvme_subsystem.target_nqn,
                    "svm_name": nvme_subsystem.svm.name,
                }
            )
    except NetAppRestError as e:
        error_and_exit(
            "Failed to retrieve available NVMe subsystems.",
            Rule(),
            str(e),
            code=ERR_NETAPP_API,
        )

    # If no NVMe subsystem names are specified, print out available and ask for input
    if not nvme_subsystem_names:
        nvme_subsystem_names = []
        print_table_with_multiple_columns("Available NVMe subsystems", available_nvme_subsystems)
        Console().print("Enter subsystem names one by one. Press Enter on an empty line when finished.")
        while True:
            nvme_subsystem_name = prompt_with_trim("Subsystem name", default="")
            if nvme_subsystem_name == "":
                break
            nvme_subsystem_names.append(nvme_subsystem_name)

        # Must provide at least one NVMe subsystem name
        if not nvme_subsystem_names:
            error_and_exit("You must specify at least one NVMe subsystem name to continue.", code=ERR_INPUT_INVALID)

    # Get all the selected NVMe subsystems
    selected_nvme_subsystems = []
    for nvme_subsystem_name in nvme_subsystem_names:
        # Find the subsystem from available subsystems
        selected_nvme_subsystem = find_first_by_property(
            items=available_nvme_subsystems, key="name", value=nvme_subsystem_name
        )
        if selected_nvme_subsystem:
            selected_nvme_subsystems.append(selected_nvme_subsystem)
        else:
            error_and_exit(
                f"NVMe subsystem {style_var(nvme_subsystem_name, color='yellow')} does not exist.",
                code=ERR_SUBSYSTEM_NOT_FOUND,
            )

    print_table_with_multiple_columns("Selected NVMe subsystems to be used", selected_nvme_subsystems)

    if not auto_confirm("Would you like to proceed with these NVMe subsystems?"):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    return selected_nvme_subsystems


def netapp_add_host_to_subsystems(host_nqn: str, nvme_subsystem_uuids: List[str]) -> None:
    """
    Add a host NQN to multiple NetApp NVMe subsystems.

    This function adds the specified host NQN to each of the provided NVMe subsystems,
    enabling the host to access namespaces within those subsystems. If the host is
    already connected to a subsystem, it reports this without error.

    Args:
        host_nqn: NVMe Host Qualified Name to add to the subsystems.
        nvme_subsystem_uuids: List of NVMe subsystem UUIDs to add the host to.

    Raises:
        typer.Exit: If the host cannot be added to any subsystem or if a NetApp API error occurs.
    """

    # Add host_nqn to the provided subsystems
    for nvme_subsystem_uuid in nvme_subsystem_uuids:
        nvme_subsystem_host = NvmeSubsystemHost.from_dict({"subsystem": {"uuid": nvme_subsystem_uuid}, "nqn": host_nqn})
        try:
            Console().print(
                f"Adding host NQN {style_var(host_nqn)} to NVMe subsystem {style_var(nvme_subsystem_uuid)}."
            )
            nvme_subsystem_host.post()
        except NetAppRestError as e:
            # Duplicate host_nqn is status_code 409, netapp error code: NETAPP_DUPLICATE_NQN_ERR_CODE, this is fine and we can continue
            if e.status_code == 409 and int(e.response_body["error"]["code"]) == NETAPP_DUPLICATE_NQN_ERR_CODE:  # type: ignore
                Console().print(
                    f"Host NQN {style_var(host_nqn)} is already connected to NVMe subsystem {style_var(nvme_subsystem_uuid)}."
                )
            else:
                error_and_exit(
                    f"Failed to add host NQN {style_var(host_nqn, color='yellow')} to NVMe subsystem {style_var(nvme_subsystem_uuid, color='yellow')}.",
                    Rule(),
                    str(e),
                    code=ERR_NETAPP_API,
                )


def netapp_get_nvme_interfaces(subsystem_endpoints: Optional[List[str]]) -> List[Dict[str, str]]:
    """
    Retrieve and validate NetApp NVMe interface endpoints.

    This function gets all available NVMe interfaces from the NetApp cluster and validates
    that the specified endpoints exist. If no endpoints are provided, it displays available
    options and prompts the user to select them.

    Args:
        subsystem_endpoints: List of NVMe subsystem endpoint addresses to validate. If None, user will be prompted.

    Returns:
        List of dictionaries containing selected NVMe interface details.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints are not available,
                   or if a NetApp API error occurs.
    """

    available_nvme_interfaces = netapp_get_available_nvme_interfaces()

    available_subsystem_endpoints = [
        available_nvme_interface["ip"] for available_nvme_interface in available_nvme_interfaces
    ]

    if not subsystem_endpoints:
        print_table_with_multiple_columns("Available NVMe interfaces", available_nvme_interfaces)
        if auto_confirm("Would you like to use all the listed NVMe endpoints?"):
            subsystem_endpoints = available_subsystem_endpoints
        else:
            subsystem_endpoints = []
            Console().print("Enter subsystem endpoints one by one. Press Enter on an empty line when finished.")
            while True:
                subsystem_endpoint = prompt_with_trim(
                    "Subsystem endpoint IP address",
                    default="",
                )
                if subsystem_endpoint == "":
                    break
                subsystem_endpoints.append(subsystem_endpoint)
        validate_ip_list(subsystem_endpoints)

    if len(subsystem_endpoints) == 0:
        error_and_exit(
            "You must specify at least one NVMe subsystem endpoint to continue.",
            code=ERR_INPUT_INVALID,
        )

    selected_nvme_interfaces = []
    for subsystem_endpoint in subsystem_endpoints:
        selected_nvme_interface = find_first_by_property(
            items=available_nvme_interfaces, key="ip", value=subsystem_endpoint
        )
        if selected_nvme_interface:
            selected_nvme_interfaces.append(selected_nvme_interface)
        else:
            error_and_exit(
                f"Endpoint {style_var(subsystem_endpoint, color='yellow')} is not available.",
                code=ERR_ENDPOINT_NOT_FOUND,
            )

    return selected_nvme_interfaces


def netapp_get_available_nvme_interfaces() -> List[Dict[str, str]]:
    """
    Retrieve all available NetApp NVMe interfaces that support NVMe-over-TCP.

    This function queries all NVMe interfaces on the NetApp cluster and filters them
    to return only those that support the NVMe-over-TCP transport protocol, providing
    the interface details needed for subsystem endpoint configuration.

    Returns:
        List of dictionaries containing 'ip', 'interface_name', 'svm_name', and 'node_name'
        keys for each NVMe-over-TCP interface.

    Raises:
        typer.Exit: If NVMe interfaces cannot be retrieved or if a NetApp API error occurs.
    """

    available_nvme_interfaces = []
    try:
        for nvme_interface in NvmeInterface.get_collection():
            nvme_interface.get()
            # Only include if nvme_tcp is an allowed protocol
            if NETAPP_NVME_TCP_PROTOCOL_NAME in nvme_interface.transport_protocols:
                available_nvme_interfaces.append(
                    {
                        "ip": nvme_interface.transport_address,
                        "interface_name": nvme_interface.name,
                        "svm_name": nvme_interface.svm.name,
                        "node_name": nvme_interface.node.name,
                    }
                )
    except NetAppRestError as e:
        error_and_exit(
            "Failed to retrieve available NVMe interfaces.",
            Rule(),
            str(e),
            code=ERR_NETAPP_API,
        )

    return available_nvme_interfaces


def netapp_get_subsystems_with_matching_nvme_interfaces(
    nvme_subsystems: List[Dict[str, str]], nvme_interfaces: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """
    Create target configurations by matching NVMe subsystems with their corresponding interfaces.

    This function performs a filtered Cartesian product of NVMe subsystems and interfaces,
    matching them by Storage Virtual Machine name to create valid target configurations.
    Each resulting target contains an IP address and NQN pair for NVMe connectivity.

    Args:
        nvme_subsystems: List of NVMe subsystem dictionaries containing 'svm_name' and 'nqn' keys.
        nvme_interfaces: List of NVMe interface dictionaries containing 'svm_name' and 'ip' keys.

    Returns:
        List of dictionaries containing 'ip' and 'nqn' keys for each valid subsystem-interface pair.
    """

    subsystems_with_nvme_interfaces = []
    for nvme_subsystem in nvme_subsystems:
        for nvme_interface in nvme_interfaces:
            if nvme_subsystem["svm_name"] == nvme_interface["svm_name"]:
                subsystems_with_nvme_interfaces.append({"ip": nvme_interface["ip"], "nqn": nvme_subsystem["nqn"]})
    return subsystems_with_nvme_interfaces
