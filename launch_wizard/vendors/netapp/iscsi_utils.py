from typing import Dict, List, Optional, Tuple, cast

from netapp_ontap.error import NetAppRestError
from netapp_ontap.resource import Resource
from netapp_ontap.resources import Igroup, IgroupInitiator, IpInterface, IscsiService, Lun, LunMap, Svm
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.constants import (
    NETAPP_DUPLICATE_IQN_ERR_CODE,
    NETAPP_DUPLICATE_LUN_MAP_ERR_CODE,
    NETAPP_ISCSI_DATA_SERVICE,
    NETAPP_ISCSI_PROTOCOL_NAME,
    NETAPP_MIXED_PROTOCOL_NAME,
)
from launch_wizard.common.enums import OperationSystemType
from launch_wizard.common.error_codes import (
    ERR_ENDPOINT_NOT_FOUND,
    ERR_INPUT_INVALID,
    ERR_LUN_NOT_FOUND,
    ERR_NETAPP_API,
    ERR_NETAPP_ISCSI_NOT_ENABLED,
    ERR_USER_ABORT,
)
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import (
    print_table_with_multiple_columns,
    print_table_with_single_column,
    style_var,
)
from launch_wizard.utils.network_utils import validate_ip_list
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def netapp_get_iscsi_service(svm_name: str) -> Optional[Resource]:
    """
    Check whether a NetApp Storage Virtual Machine has the iSCSI service enabled.

    This function queries the specified SVM to determine if the iSCSI service is configured
    and enabled, which is required for iSCSI storage connectivity.

    Args:
        svm_name: Name of the Storage Virtual Machine to check.

    Returns:
        The iSCSI service resource if enabled, None if disabled or not configured.

    Raises:
        typer.Exit: If the iSCSI service information cannot be retrieved or if a NetApp API error occurs.
    """

    try:
        iscsi_service = IscsiService.find(svm=svm_name)
        # Should we check for svm.state == running?
        if iscsi_service and iscsi_service.enabled:
            iscsi_service.get()
            return iscsi_service

        # Iscsi isn't enabled on SVM
        return None
    except NetAppRestError as e:
        error_and_exit(
            f"Failed to retrieve iSCSI service information for SVM {style_var(svm_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_NETAPP_API,
        )


def netapp_get_svm_name_and_target_iqn(svm_name: Optional[str]) -> Tuple[str, str]:
    """
    Retrieve and validate a NetApp Storage Virtual Machine name and its target IQN.

    This function validates that the specified SVM exists and has iSCSI service enabled.
    If no SVM name is provided, it displays available SVMs with iSCSI enabled and prompts
    the user to select one.

    Args:
        svm_name: Name of the Storage Virtual Machine to validate. If None, user will be prompted.

    Returns:
        A tuple containing the validated SVM name and its corresponding target IQN.

    Raises:
        typer.Exit: If no SVMs with iSCSI are available, the specified SVM doesn't have iSCSI enabled,
                   or if a NetApp API error occurs.
    """

    available_svms = []
    try:
        for svm in Svm.get_collection():
            svm.get()
            iscsi_service = netapp_get_iscsi_service(svm.name)
            if iscsi_service:
                available_svms.append({"name": svm.name, "target_iqn": iscsi_service.target.name})
    except NetAppRestError as e:
        error_and_exit(
            "Failed to retrieve available Storage Virtual Machines.",
            Rule(),
            str(e),
            code=ERR_NETAPP_API,
        )

    if not svm_name:
        print_table_with_multiple_columns("Available Storage Virtual Machines with iSCSI enabled", available_svms)
        svm_name = prompt_with_trim("Please enter a Storage Virtual Machine (SVM) name")

    selected_svm = find_first_by_property(items=available_svms, key="name", value=svm_name)

    if not selected_svm:
        error_and_exit(
            f"Storage Virtual Machine {style_var(svm_name, color='yellow')} doesn't have iSCSI enabled.",
            code=ERR_NETAPP_ISCSI_NOT_ENABLED,
        )

    Console().print(
        f"Using Storage Virtual Machine {style_var(selected_svm['name'])} with Target IQN {style_var(selected_svm['target_iqn'])}"
    )

    return selected_svm["name"], selected_svm["target_iqn"]


def netapp_create_igroup(svm_name: str, igroup_name: Optional[str], os_type: OperationSystemType) -> str:
    """
    Create a new NetApp initiator group or validate an existing one.

    This function creates a new iSCSI initiator group with the specified name and operating system type,
    or validates that an existing group is suitable for use. If no group name is provided, it displays
    available groups and prompts the user to select or create one.

    Args:
        svm_name: Name of the Storage Virtual Machine where the initiator group will be created.
        igroup_name: Name of the initiator group to create or validate. If None, user will be prompted.
        os_type: Operating system type for the initiator group (Linux or Windows).

    Returns:
        The name of the created or validated initiator group.

    Raises:
        typer.Exit: If initiator group creation fails, the user cancels the operation,
                   or if a NetApp API error occurs.
    """

    available_igroups = []
    try:
        for igroup in Igroup.get_collection(svm=svm_name):
            igroup.get()
            if str(igroup.protocol) in [NETAPP_ISCSI_PROTOCOL_NAME, NETAPP_MIXED_PROTOCOL_NAME]:
                initiator_names = ""
                if hasattr(igroup, "initiators") and igroup.initiators:
                    initiator_names = "\n".join([initiator.name for initiator in igroup.initiators])
                available_igroups.append(
                    {
                        "name": igroup.name,
                        "os_type": igroup.os_type,
                        "protocol": igroup.protocol,
                        "initiators": initiator_names,
                    }
                )
    except NetAppRestError as e:
        error_and_exit(
            "Failed to retrieve available initiator groups.",
            Rule(),
            str(e),
            code=ERR_NETAPP_API,
        )

    if not igroup_name:
        print_table_with_multiple_columns(
            "Available initiator groups with iSCSI protocol on Storage Virtual Machine", available_igroups
        )
        igroup_name = prompt_with_trim("Please enter an existing initiator group name or specify a new name")
        igroup_name = cast(str, igroup_name)

    selected_igroup = find_first_by_property(items=available_igroups, key="name", value=igroup_name)

    if selected_igroup:
        Console().print(f"Initiator group {style_var(igroup_name)} already exists.")
        return igroup_name

    Console().print(f"Initiator group {style_var(igroup_name)} doesn't exist.")
    if not auto_confirm(f"Would you like to create initiator group {style_var(igroup_name)}?"):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    try:
        igroup = Igroup(
            name=igroup_name,
            svm={"name": svm_name},
            os_type=os_type.value,
            protocol=NETAPP_ISCSI_PROTOCOL_NAME,
            initiators=[],
        )
        igroup.post()
        Console().print(f"Initiator group {style_var(igroup_name)} was created successfully.")
    except NetAppRestError:
        error_and_exit(
            f"Storage Virtual Machine {style_var(svm_name, color='yellow')} doesn't have iSCSI enabled.",
            code=ERR_NETAPP_ISCSI_NOT_ENABLED,
        )

    return igroup_name


def netapp_add_initiator_iqn_to_igroup(svm_name: str, igroup_name: str, initiator_iqn: str) -> None:
    """
    Add an iSCSI initiator IQN to a NetApp initiator group.

    This function adds the specified iSCSI initiator IQN to the given initiator group.
    If the initiator is already present in the group, it reports this without error.
    After adding, it displays the updated list of initiators in the group.

    Args:
        svm_name: Name of the Storage Virtual Machine containing the initiator group.
        igroup_name: Name of the initiator group to modify.
        initiator_iqn: iSCSI Initiator Qualified Name to add to the group.

    Raises:
        typer.Exit: If the initiator cannot be added to the group or if a NetApp API error occurs.
    """

    try:
        # Find the igroup
        igroup = Igroup.find(name=igroup_name, svm=svm_name)

        # Add the initiator to the igroup
        initiator = IgroupInitiator(igroup.uuid)
        initiator.name = initiator_iqn  # type: ignore
        initiator.post()

        Console().print(
            f"Initiator IQN {style_var(initiator_iqn)} was successfully added to initiator group {style_var(igroup_name)}."
        )

        # Refresh the igroup to get the updated list of initiators
        igroup.get()
        print_table_with_single_column(
            f"Initiators in initiator group {style_var(igroup_name)}",
            [initiator.name for initiator in igroup.initiators],
            column_name="IQN",
        )
    except NetAppRestError as e:
        # Duplicate initiator_iqn is status_code 409, netapp error code: NETAPP_DUPLICATE_IQN_ERR_CODE, this is fine and we can continue
        if e.status_code == 409 and int(e.response_body["error"]["code"]) == NETAPP_DUPLICATE_IQN_ERR_CODE:  # type: ignore
            Console().print(
                f"Initiator IQN {style_var(initiator_iqn)} already exists in initiator group {style_var(igroup_name)}."
            )
        else:
            error_and_exit(
                f"Failed to add initiator IQN {style_var(initiator_iqn, color='yellow')} to initiator group {style_var(igroup_name, color='yellow')}.",
                Rule(),
                str(e),
                code=ERR_NETAPP_API,
            )


def netapp_map_luns_to_igroup(svm_name: str, igroup_name: str, lun_paths: Optional[List[str]]) -> None:
    """
    Map NetApp LUNs to the specified initiator group.

    This function maps the specified LUNs to the given initiator group, making them accessible
    to the initiators in that group. If no LUN paths are provided, it displays all available
    LUNs and prompts the user to select them interactively.

    Args:
        svm_name: Name of the Storage Virtual Machine containing the LUNs and initiator group.
        igroup_name: Name of the initiator group to map LUNs to.
        lun_paths: List of LUN paths to map. If None, user will be prompted to select from available LUNs.

    Raises:
        typer.Exit: If no LUNs are available, specified LUNs don't exist, no LUN paths are provided,
                   or if a NetApp API error occurs.
    """

    available_luns = []
    try:
        for lun in Lun.get_collection(svm=svm_name):
            lun.get()
            if lun.enabled:
                available_luns.append(
                    {
                        "path": lun.name,
                        "size": f"{lun.space.size / (1024 * 1024 * 1024):.2f} GiB",
                        "os_type": lun.os_type,
                        "node": lun.location.node.name,
                        "volume": lun.location.volume.name,
                    }
                )
    except NetAppRestError as e:
        error_and_exit("Failed to retrieve available LUNs.", Rule(), str(e), code=ERR_NETAPP_API)

    if not available_luns:
        error_and_exit("There are no LUNs available on the Storage Virtual Machine.", code=ERR_LUN_NOT_FOUND)

    if not lun_paths:
        print_table_with_multiple_columns("Available LUNs on Storage Virtual Machine", available_luns)

        lun_paths = []
        Console().print("Enter LUN paths one by one. Press Enter on an empty line when finished.")
        while True:
            lun_path = prompt_with_trim("LUN path to map to initiator group", default="")
            if lun_path == "":
                break
            lun_paths.append(lun_path)

    # Must provide at least one LUN path
    if not lun_paths:
        error_and_exit("You must specify at least one LUN path to continue.", code=ERR_INPUT_INVALID)

    for lun_path in lun_paths:
        selected_lun = find_first_by_property(items=available_luns, key="path", value=lun_path)
        if selected_lun:
            Console().print(f"Mapping LUN {style_var(lun_path)} to initiator group {style_var(igroup_name)}.")
            netapp_map_lun_to_igroup(svm_name, igroup_name, lun_path)
        else:
            error_and_exit(
                f"LUN {style_var(lun_path, color='yellow')} does not exist.",
                code=ERR_LUN_NOT_FOUND,
            )

    netapp_print_lun_maps_for_igroup(svm_name, igroup_name)


def netapp_map_lun_to_igroup(svm_name: str, igroup_name: str, lun_path: str) -> None:
    """
    Map a single NetApp LUN to an initiator group.

    This function creates a mapping between a specific LUN and an initiator group on the
    specified Storage Virtual Machine. If the LUN is already mapped to the group, it
    reports this without error.

    Args:
        svm_name: Name of the Storage Virtual Machine containing the LUN and initiator group.
        igroup_name: Name of the initiator group to map the LUN to.
        lun_path: Path of the LUN to map to the initiator group.

    Raises:
        typer.Exit: If the LUN mapping fails or if a NetApp API error occurs.
    """

    try:
        lun_map = LunMap(svm={"name": svm_name}, igroup={"name": igroup_name}, lun={"name": lun_path})
        lun_map.post()
    except NetAppRestError as e:
        if e.status_code == 409 and int(e.response_body["error"]["code"]) == NETAPP_DUPLICATE_LUN_MAP_ERR_CODE:  # type: ignore
            Console().print(f"LUN {style_var(lun_path)} is already mapped to initiator group {style_var(igroup_name)}.")
        else:
            error_and_exit(
                f"Failed to map LUN {style_var(lun_path, color='yellow')} to initiator group {style_var(igroup_name, color='yellow')}.",
                Rule(),
                str(e),
                code=ERR_NETAPP_API,
            )


def netapp_print_lun_maps_for_igroup(svm_name: str, igroup_name: str) -> None:
    """
    Display a table of LUNs mapped to the specified NetApp initiator group.

    This function retrieves and displays all LUN mappings for the given initiator group,
    providing a clear view of which LUNs are accessible to the initiators in the group.

    Args:
        svm_name: Name of the Storage Virtual Machine containing the initiator group.
        igroup_name: Name of the initiator group to display LUN mappings for.

    Raises:
        typer.Exit: If LUN mappings cannot be retrieved or if a NetApp API error occurs.
    """

    try:
        # Find the igroup
        igroup = Igroup.find(name=igroup_name, svm=svm_name)
        igroup.get(fields="lun_maps")
        lun_names = [lun_map.lun.name for lun_map in igroup.lun_maps]
        print_table_with_single_column(
            f"LUN maps for initiator group {style_var(igroup_name)}", lun_names, column_name="LUN Name"
        )
    except NetAppRestError as e:
        error_and_exit(
            f"Failed to retrieve LUN maps for initiator group {style_var(igroup_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_NETAPP_API,
        )


def netapp_get_target_endpoints(svm_name: str, target_endpoints: Optional[List[str]]) -> List[str]:
    """
    Retrieve and validate NetApp iSCSI target endpoints for the specified SVM.

    This function gets all available iSCSI interfaces from the Storage Virtual Machine and
    validates that the specified target endpoints exist. If no endpoints are provided, it
    displays available options and prompts the user to select them.

    Args:
        svm_name: Name of the Storage Virtual Machine to query for iSCSI interfaces.
        target_endpoints: List of target endpoint addresses to validate. If None, user will be prompted.

    Returns:
        List of validated target endpoint addresses.

    Raises:
        typer.Exit: If no endpoints are specified, specified endpoints are not available,
                   or if a NetApp API error occurs.
    """

    available_iscsi_interfaces = netapp_get_available_iscsi_interfaces(svm_name)

    available_target_endpoints = [
        available_iscsi_interface["ip"] for available_iscsi_interface in available_iscsi_interfaces
    ]

    if not target_endpoints:
        print_table_with_multiple_columns("Available iSCSI interfaces", available_iscsi_interfaces)
        if auto_confirm("Would you like to use all the listed iSCSI endpoints?"):
            target_endpoints = available_target_endpoints
        else:
            target_endpoints = []
            Console().print("Enter target endpoints one by one. Press Enter on an empty line when finished.")
            while True:
                target_endpoint = prompt_with_trim(
                    "Target endpoint IP address",
                    default="",
                )
                if target_endpoint == "":
                    break
                target_endpoints.append(target_endpoint)
        validate_ip_list(target_endpoints)

    if len(target_endpoints) == 0:
        error_and_exit(
            "You must specify at least one iSCSI target endpoint to continue.",
            code=ERR_INPUT_INVALID,
        )

    for target_endpoint in target_endpoints:
        if target_endpoint not in available_target_endpoints:
            error_and_exit(
                f"Endpoint {style_var(target_endpoint, color='yellow')} is not available.",
                code=ERR_ENDPOINT_NOT_FOUND,
            )

    return target_endpoints


def netapp_get_available_iscsi_interfaces(svm_name: str) -> List[Dict[str, str]]:
    """
    Retrieve all available NetApp iSCSI interfaces for the specified Storage Virtual Machine.

    This function queries all IP interfaces on the SVM and filters them to return only those
    configured for iSCSI data service, providing the interface details needed for target
    endpoint configuration.

    Args:
        svm_name: Name of the Storage Virtual Machine to query for iSCSI interfaces.

    Returns:
        List of dictionaries containing 'ip' and 'interface_name' keys for each iSCSI interface.

    Raises:
        typer.Exit: If iSCSI interfaces cannot be retrieved or if a NetApp API error occurs.
    """

    available_iscsi_interfaces = []
    try:
        for ip_interface in IpInterface.get_collection(svm=svm_name):
            ip_interface.get()
            if NETAPP_ISCSI_DATA_SERVICE in ip_interface.services:
                available_iscsi_interfaces.append({"ip": ip_interface.ip.address, "interface_name": ip_interface.name})
    except NetAppRestError as e:
        error_and_exit(
            "Failed to retrieve available iSCSI interfaces.",
            Rule(),
            str(e),
            code=ERR_NETAPP_API,
        )

    return available_iscsi_interfaces
