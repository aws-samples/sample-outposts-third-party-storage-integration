from typing import List, Optional

from hpe3parclient import exceptions
from hpe3parclient.client import HPE3ParClient
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.enums import StorageProtocol
from launch_wizard.common.error_codes import ERR_HPE_API, ERR_INPUT_INVALID, ERR_USER_ABORT, ERR_VOLUME_NOT_FOUND
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def hpe_get_volume_names(hpe_client: HPE3ParClient, volume_names: Optional[List[str]]) -> List[str]:
    """
    Retrieve and validate HPE volume names.

    This function gets all available volumes from the HPE system and validates that
    the specified volume names exist. If no volume names are provided, it displays available
    volumes and prompts the user to select them interactively.

    Args:
        hpe_client: Active connection to the HPE system.
        volume_names: List of volume names to validate. If None, user will be prompted.

    Returns:
        List of validated volume names.

    Raises:
        typer.Exit: If volumes cannot be retrieved, specified volumes don't exist, no volumes are selected,
                    or if the user cancels the operation.
    """

    Console().print("Retrieving and validating volume information...")
    available_volumes = []
    try:
        Console().print("Fetching available volumes...")
        for volume in hpe_client.getVolumes().get("members", []):
            # It appears that 1 is for system volumes, 6 is for user volumes, and 7 is for physical drives
            # However, this could not be found in any documentation
            if volume.get("provisioningType") == 6:
                available_volumes.append({"name": volume.get("name"), "uuid": volume.get("uuid")})
        Console().print(f"Found {style_var(len(available_volumes))} available volumes.")
    except Exception as e:
        error_and_exit(
            "Failed to retrieve available volumes.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )

    if not volume_names:
        volume_names = []
        print_table_with_multiple_columns("Available volumes", available_volumes, sort_by="name")
        Console().print("Enter the volume names one by one. Press Enter on an empty line when finished.")
        while True:
            volume_name = prompt_with_trim(
                "Volume name",
                default="",
                show_default=False,
            )
            if volume_name == "":
                break
            volume_names.append(volume_name)

        # Must provide at least one volume name
        if not volume_names:
            error_and_exit("You must specify at least one volume name to continue.", code=ERR_INPUT_INVALID)

    Console().print(f"Validating {style_var(len(volume_names))} specified volumes...")
    # Get all the selected volumes
    selected_volumes = []
    for volume_name in volume_names:
        Console().print(f"  Checking the volume {style_var(volume_name)}...")
        # Find the volume from available volumes
        volume = find_first_by_property(items=available_volumes, key="name", value=volume_name)
        if volume:
            selected_volumes.append(volume)
            Console().print(
                f"    {style_var('✓', color='green')} Found the volume with UUID {style_var(volume['uuid'])}."
            )
        else:
            error_and_exit(
                f"The volume {style_var(volume_name, color='yellow')} does not exist.",
                code=ERR_VOLUME_NOT_FOUND,
            )

    print_table_with_multiple_columns("Selected volumes to be used", selected_volumes, sort_by="name")

    if not auto_confirm("Would you like to proceed with these volumes?", default=True):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    selected_volume_names = [volume["name"] for volume in selected_volumes]
    Console().print(
        f"{style_var('✓', color='green')} Successfully validated {style_var(len(selected_volume_names))} volumes."
    )

    return selected_volume_names


def hpe_get_host_set_name(hpe_client: HPE3ParClient, host_set_name: Optional[str]) -> Optional[str]:
    """
    Retrieve and validate an HPE host set name.

    This function validates the provided host set name or prompts the user to select one
    from available host sets. It also offers the option to proceed without using a host set.

    Args:
        hpe_client: Active connection to the HPE system.
        host_set_name: Name of the host set to use. If None, user will be prompted.

    Returns:
        The validated host set name, or None if proceeding without a host set.

    Raises:
        typer.Exit: If host sets cannot be retrieved, the host set name is empty,
                    or if an HPE API error occurs.
    """

    if not host_set_name:
        if not auto_confirm("No host set name was specified. Would you like to use a host set?", default=False):
            Console().print(f"{style_var('✓', color='green')} Proceeding without a host set.")
            return None

        Console().print("Retrieving available host sets...")
        available_host_sets = []
        try:
            for host_set in hpe_client.getHostSets().get("members", []):
                available_host_sets.append({"name": host_set.get("name"), "members": host_set.get("setmembers")})
            Console().print(f"Found {style_var(len(available_host_sets))} available host sets.")
        except Exception as e:
            error_and_exit(
                "Failed to retrieve available host sets.",
                Rule(),
                str(e),
                code=ERR_HPE_API,
            )

        print_table_with_multiple_columns("Available host sets", available_host_sets, sort_by="name")

        host_set_name = prompt_with_trim("Please enter an existing host set name or specify a new name", data_type=str)

        if host_set_name:
            Console().print(f"{style_var('✓', color='green')} Using the host set name {style_var(host_set_name)}.")
        else:
            error_and_exit("The host set name cannot be empty.", code=ERR_INPUT_INVALID)

    return host_set_name


def hpe_get_host_name(hpe_client: HPE3ParClient, host_name: Optional[str], protocol: StorageProtocol) -> str:
    """
    Retrieve and validate an HPE host name.

    This function validates the provided host name or prompts the user to select one
    from available hosts or specify a new host name to be created.

    Args:
        hpe_client: Active connection to the HPE system.
        host_name: Name of the host to use. If None, user will be prompted.
        protocol: Storage protocol being used (iSCSI or NVMe) for protocol-specific guidance.

    Returns:
        The validated host name as a string.

    Raises:
        typer.Exit: If hosts cannot be retrieved, the host name is empty,
                    or if an HPE API error occurs.
    """

    if not host_name:
        Console().print("Retrieving available hosts...")
        available_hosts = []
        try:
            for host in hpe_client.getHosts().get("members", []):
                available_hosts.append(
                    {
                        "name": host.get("name"),
                        "iscsi_paths": [path.get("name") for path in host.get("iSCSIPaths", [])],
                        "nvme_paths": [path.get("NQN") for path in host.get("NVMETCPPaths", [])],
                        "fc_paths": [path.get("wwn") for path in host.get("FCPaths", [])],
                    }
                )
            Console().print(f"Found {style_var(len(available_hosts))} available hosts.")
        except Exception as e:
            error_and_exit(
                "Failed to retrieve available hosts.",
                Rule(),
                str(e),
                code=ERR_HPE_API,
            )

        print_table_with_multiple_columns("Available hosts", available_hosts, sort_by="name")

        if protocol == StorageProtocol.NVME:
            Console().print(
                f"{style_var('Warning', color='yellow')}: Only one NVMe host NQN can be associated with a host. If you will use a new host NQN for your instance, please specify a new host name."
            )

        host_name = prompt_with_trim("Please enter an existing host name or specify a new name", data_type=str)

        if host_name:
            Console().print(f"{style_var('✓', color='green')} Using the host name {style_var(host_name)}.")
        else:
            error_and_exit("The host name cannot be empty.", code=ERR_INPUT_INVALID)

    return host_name


def hpe_create_host_set(hpe_client: HPE3ParClient, host_set_name: str, host_name: str) -> None:
    """
    Create a new HPE host set or add a host to an existing one.

    This function creates a new host set with the specified name and adds the given host to it.
    If a host set with the same name already exists, it adds the host to the existing group.

    Args:
        hpe_client: Active connection to the HPE system.
        host_set_name: Name of the host set to create or modify.
        host_name: Name of the host to add to the host set.

    Raises:
        typer.Exit: If the host set creation fails or if an HPE API error occurs.
    """

    Console().print(f"Creating the host set {style_var(host_set_name)} with the host {style_var(host_name)}...")

    try:
        Console().print("Checking for an existing host set with the same name...")
        try:
            hpe_client.getHostSet(name=host_set_name)
            Console().print(f"The host set {style_var(host_set_name)} already exists.")
            Console().print("Adding the host to the existing host set...")
            hpe_modify_host_set(hpe_client, host_set_name, host_name)
        except exceptions.HTTPNotFound:
            Console().print(f"Creating a new host set {style_var(host_set_name)}...")
            # Host set does not exist
            # Create a new one
            hpe_client.createHostSet(name=host_set_name, setmembers=[host_name])
            Console().print(
                f"{style_var('✓', color='green')} Successfully created the host set {style_var(host_set_name)}."
            )
    except Exception as e:
        error_and_exit(
            f"Failed to create the host set {style_var(host_set_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )


def hpe_modify_host_set(hpe_client: HPE3ParClient, host_set_name: str, host_name: str) -> None:
    """
    Add a host to an existing HPE host set.

    This function adds the specified host to an existing host set. If the host is already
    a member of the host set, it reports this without error.

    Args:
        hpe_client: Active connection to the HPE system.
        host_set_name: Name of the existing host set to modify.
        host_name: Name of the host to add to the host set.

    Raises:
        typer.Exit: If the host set modification fails or if an HPE API error occurs.
    """

    Console().print(f"Modifying the host set {style_var(host_set_name)} to add the host {style_var(host_name)}...")

    try:
        Console().print("Retrieving host set details...")
        host_set = hpe_client.getHostSet(name=host_set_name)

        Console().print("Checking the existing hosts...")
        existing_host_names = host_set.get("setmembers", [])
        if host_name in existing_host_names:
            Console().print(
                f"The host {style_var(host_name)} is already a member of the host set {style_var(host_set_name)}."
            )
            Console().print(f"{style_var('✓', color='green')} No changes are needed.")
            return

        Console().print(f"Adding the new host {style_var(host_name)} to the host set {style_var(host_set_name)}...")
        hpe_client.modifyHostSet(name=host_set_name, action=HPE3ParClient.HOST_EDIT_ADD, setmembers=[host_name])
        Console().print(
            f"{style_var('✓', color='green')} Successfully added the host {style_var(host_name)} to the host set {style_var(host_set_name)}."
        )
    except Exception as e:
        error_and_exit(
            f"Failed to add the host {style_var(host_name, color='yellow')} to the host set {style_var(host_set_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )


def hpe_export_volumes_to_host(hpe_client: HPE3ParClient, volume_names: List[str], host_name: str) -> None:
    """
    Map HPE volumes to a specific host.

    This function maps each specified volume to the given host. If a volume is already
    mapped to the host, it reports this without error and continues with the next volume.

    Args:
        hpe_client: Active connection to the HPE system.
        volume_names: List of volume names to map to the host.
        host_name: Name of the host to map volumes to.

    Raises:
        typer.Exit: If volume mapping fails or if an HPE API error occurs.
    """

    Console().print(f"Mapping {style_var(len(volume_names))} volumes to the host {style_var(host_name)}...")

    Console().print("Retrieving existing VLUNs...")
    try:
        existing_vluns = hpe_client.getVLUNs().get("members", [])
    except Exception as e:
        error_and_exit(
            "Failed to retrieve existing VLUNs.",
            Rule(),
            str(e),
            code=ERR_HPE_API,
        )

    for volume_name in volume_names:
        Console().print(f"  Mapping the volume {style_var(volume_name)}...")
        # Check if the volume is already exported to the host
        if any(
            vlun
            for vlun in existing_vluns
            if vlun.get("volumeName") == volume_name and vlun.get("hostname") == host_name
        ):
            Console().print(
                f"    The volume {style_var(volume_name)} is already mapped to the host {style_var(host_name)}."
            )
            continue

        try:
            hpe_client.createVLUN(volumeName=volume_name, hostname=host_name, auto=True)
            Console().print(
                f"    {style_var('✓', color='green')} Successfully mapped the volume {style_var(volume_name)} to the host {style_var(host_name)}."
            )
        except Exception as e:
            error_and_exit(
                f"Failed to map the volume {style_var(volume_name, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
                Rule(),
                str(e),
                code=ERR_HPE_API,
            )

    Console().print(
        f"{style_var('✓', color='green')} Successfully mapped {style_var(len(volume_names))} volumes to the host {style_var(host_name)}."
    )
