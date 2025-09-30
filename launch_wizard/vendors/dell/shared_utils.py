from typing import List, Optional

from PyPowerStore.powerstore_conn import PowerStoreConn
from PyPowerStore.utils.exception import PowerStoreException
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.error_codes import ERR_DELL_API, ERR_INPUT_INVALID, ERR_USER_ABORT, ERR_VOLUME_NOT_FOUND
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def dell_get_volume_ids(powerstore_connection: PowerStoreConn, volume_names: Optional[List[str]]) -> List[str]:
    """
    Retrieve and validate Dell PowerStore volume IDs based on volume names.

    This function gets all available volumes from the PowerStore system and validates that
    the specified volume names exist. If no volume names are provided, it displays available
    volumes and prompts the user to select them interactively.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        volume_names: List of volume names to retrieve IDs for. If None, user will be prompted.

    Returns:
        List of volume IDs corresponding to the specified volume names.

    Raises:
        typer.Exit: If volumes cannot be retrieved, specified volumes don't exist, no volumes are selected,
                    or if the user cancels the operation.
    """

    Console().print("Retrieving and validating volume information...")
    available_volumes = []
    try:
        Console().print("Fetching available volumes...")
        for volume in powerstore_connection.provisioning.get_volumes():
            available_volumes.append({"name": volume["name"], "id": volume["id"]})
        Console().print(f"Found {style_var(len(available_volumes))} available volumes.")
    except PowerStoreException as e:
        error_and_exit(
            "Failed to retrieve available volumes.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
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
            Console().print(f"    {style_var('✓', color='green')} Found the volume with ID {style_var(volume['id'])}.")
        else:
            error_and_exit(
                f"The volume {style_var(volume_name, color='yellow')} does not exist.",
                code=ERR_VOLUME_NOT_FOUND,
            )

    print_table_with_multiple_columns("Selected volumes to be used", selected_volumes, sort_by="name")

    if not auto_confirm("Would you like to proceed with these volumes?", default=True):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    selected_volume_ids = [volume["id"] for volume in selected_volumes]
    Console().print(
        f"{style_var('✓', color='green')} Successfully validated {style_var(len(selected_volume_ids))} volumes."
    )

    return selected_volume_ids


def dell_get_host_group_name(powerstore_connection: PowerStoreConn, host_group_name: Optional[str]) -> Optional[str]:
    """
    Retrieve and validate a Dell PowerStore host group name.

    This function validates the provided host group name or prompts the user to select one
    from available host groups. It also offers the option to proceed without using a host group.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_group_name: Name of the host group to use. If None, user will be prompted.

    Returns:
        The validated host group name, or None if proceeding without a host group.

    Raises:
        typer.Exit: If host groups cannot be retrieved, the host group name is empty,
                    or if a PowerStore API error occurs.
    """

    if not host_group_name:
        if not auto_confirm("No host group name was specified. Would you like to use a host group?", default=False):
            Console().print(f"{style_var('✓', color='green')} Proceeding without a host group.")
            return None

        Console().print("Retrieving available host groups...")
        available_host_groups = []
        try:
            for host_group in powerstore_connection.provisioning.get_host_group_list():
                available_host_groups.append({"name": host_group["name"], "id": host_group["id"]})
            Console().print(f"Found {style_var(len(available_host_groups))} available host groups.")
        except PowerStoreException as e:
            error_and_exit(
                "Failed to retrieve available host groups.",
                Rule(),
                str(e),
                code=ERR_DELL_API,
            )

        print_table_with_multiple_columns("Available host groups", available_host_groups, sort_by="name")

        host_group_name = prompt_with_trim(
            "Please enter an existing host group name or specify a new name", data_type=str
        )

        if host_group_name:
            Console().print(f"{style_var('✓', color='green')} Using the host group name {style_var(host_group_name)}.")
        else:
            error_and_exit("The host group name cannot be empty.", code=ERR_INPUT_INVALID)

    return host_group_name


def dell_get_host_name(powerstore_connection: PowerStoreConn, host_name: Optional[str]) -> str:
    """
    Retrieve and validate a Dell PowerStore host name.

    This function validates the provided host name or prompts the user to select one
    from available hosts or specify a new host name to be created.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_name: Name of the host to use. If None, user will be prompted.

    Returns:
        The validated host name as a string.

    Raises:
        typer.Exit: If hosts cannot be retrieved, the host name is empty,
                    or if a PowerStore API error occurs.
    """

    if not host_name:
        Console().print("Retrieving available hosts...")
        available_hosts = []
        try:
            for host in powerstore_connection.provisioning.get_hosts():
                available_hosts.append({"name": host["name"], "id": host["id"]})
            Console().print(f"Found {style_var(len(available_hosts))} available hosts.")
        except PowerStoreException as e:
            error_and_exit(
                "Failed to retrieve available hosts.",
                Rule(),
                str(e),
                code=ERR_DELL_API,
            )

        print_table_with_multiple_columns("Available hosts", available_hosts, sort_by="name")
        host_name = prompt_with_trim("Please enter an existing host name or specify a new name", data_type=str)

        if host_name:
            Console().print(f"{style_var('✓', color='green')} Using the host name {style_var(host_name)}.")
        else:
            error_and_exit("The host name cannot be empty.", code=ERR_INPUT_INVALID)

    return host_name


def dell_create_host_group(powerstore_connection: PowerStoreConn, host_group_name: str, host_id: str) -> str:
    """
    Create a new Dell PowerStore host group or add a host to an existing one.

    This function creates a new host group with the specified name and adds the given host to it.
    If a host group with the same name already exists, it adds the host to the existing group.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_group_name: Name of the host group to create or modify.
        host_id: ID of the host to add to the host group.

    Returns:
        The ID of the created or modified host group.

    Raises:
        typer.Exit: If the host group creation fails or if a PowerStore API error occurs.
    """

    Console().print(f"Creating the host group {style_var(host_group_name)} with the host ID {style_var(host_id)}...")

    try:
        Console().print("Checking for an existing host group with the same name...")
        host_groups_with_matching_name = powerstore_connection.provisioning.get_host_group_by_name(
            host_group_name=host_group_name
        )
        if host_groups_with_matching_name:
            Console().print(f"The host group {style_var(host_group_name)} already exists.")
            Console().print("Adding the host to the existing host group.")
            return dell_modify_host_group(powerstore_connection, host_group_name, host_id)
        else:
            Console().print(f"Creating a new host group {style_var(host_group_name)}...")
            host_group = powerstore_connection.provisioning.create_host_group(name=host_group_name, host_ids=[host_id])
            Console().print(
                f"{style_var('✓', color='green')} Successfully created the host group {style_var(host_group_name)} with ID {style_var(host_group['id'])}."
            )
            return host_group["id"]
    except PowerStoreException as e:
        error_and_exit(
            f"Failed to create the host group {style_var(host_group_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )


def dell_modify_host_group(powerstore_connection: PowerStoreConn, host_group_name: str, host_id: str) -> str:
    """
    Add a host to an existing Dell PowerStore host group.

    This function adds the specified host to an existing host group. If the host is already
    a member of the host group, it reports this and returns the host group ID without error.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        host_group_name: Name of the existing host group to modify.
        host_id: ID of the host to add to the host group.

    Returns:
        The ID of the modified host group.

    Raises:
        typer.Exit: If the host group modification fails or if a PowerStore API error occurs.
    """

    Console().print(f"Modifying the host group {style_var(host_group_name)} to add the host {style_var(host_id)}...")

    try:
        Console().print("Retrieving host group details...")
        host_group = powerstore_connection.provisioning.get_host_group_by_name(host_group_name=host_group_name)[0]
        host_group_id = host_group["id"]

        Console().print("Checking the existing hosts...")
        host_group_details = powerstore_connection.provisioning.get_host_group_details(host_group_id=host_group_id)
        if host_group_details["hosts"]:
            for host in host_group_details["hosts"]:
                if host["id"] == host_id:
                    Console().print(
                        f"The host {style_var(host_id)} is already a member of the host group {style_var(host_group_name)}."
                    )
                    Console().print(f"{style_var('✓', color='green')} No changes are needed.")
                    return host_group_id

        Console().print(f"Adding the new host {style_var(host_id)} to the host group {style_var(host_group_name)}...")
        powerstore_connection.provisioning.modify_host_group(host_group_id, add_host_ids=[host_id])
        Console().print(
            f"{style_var('✓', color='green')} Successfully added the host {style_var(host_id)} to the host group {style_var(host_group_name)}."
        )
        return host_group_id
    except PowerStoreException as e:
        error_and_exit(
            f"Failed to add the host {style_var(host_id, color='yellow')} to the host group {style_var(host_group_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_DELL_API,
        )


def dell_map_volumes_to_host(
    powerstore_connection: PowerStoreConn, volume_ids: List[str], host_name: str, host_id: str
) -> None:
    """
    Map Dell PowerStore volumes to a specific host.

    This function maps each specified volume to the given host. If a volume is already
    mapped to the host, it reports this without error and continues with the next volume.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        volume_ids: List of volume IDs to map to the host.
        host_name: Name of the host for display purposes.
        host_id: ID of the host to map volumes to.

    Raises:
        typer.Exit: If volume mapping fails or if a PowerStore API error occurs.
    """

    Console().print(f"Mapping {style_var(len(volume_ids))} volumes to the host {style_var(host_name)}...")

    for volume_id in volume_ids:
        Console().print(f"  Mapping the volume {style_var(volume_id)}...")
        try:
            powerstore_connection.provisioning.map_volume_to_host(volume_id=volume_id, host_id=host_id)
            Console().print(
                f"    {style_var('✓', color='green')} Successfully mapped the volume {style_var(volume_id)} to the host {style_var(host_name)}."
            )
        except PowerStoreException as e:
            if "already mapped" in str(e):
                Console().print(
                    f"    The volume {style_var(volume_id)} is already mapped to the host {style_var(host_name)}."
                )
            else:
                error_and_exit(
                    f"Failed to map the volume {style_var(volume_id, color='yellow')} to the host {style_var(host_name, color='yellow')}.",
                    Rule(),
                    str(e),
                    code=ERR_DELL_API,
                )

    Console().print(
        f"{style_var('✓', color='green')} Successfully mapped {style_var(len(volume_ids))} volumes to the host {style_var(host_name)}."
    )


def dell_map_volumes_to_host_group(
    powerstore_connection: PowerStoreConn, volume_ids: List[str], host_group_name: str, host_group_id: str
) -> None:
    """
    Map Dell PowerStore volumes to a specific host group.

    This function maps each specified volume to the given host group. If a volume is already
    mapped to the host group, it reports this without error and continues with the next volume.

    Args:
        powerstore_connection: Active connection to the Dell PowerStore system.
        volume_ids: List of volume IDs to map to the host group.
        host_group_name: Name of the host group for display purposes.
        host_group_id: ID of the host group to map volumes to.

    Raises:
        typer.Exit: If volume mapping fails or if a PowerStore API error occurs.
    """

    Console().print(f"Mapping {style_var(len(volume_ids))} volumes to the host group {style_var(host_group_name)}...")

    for volume_id in volume_ids:
        Console().print(f"  Mapping the volume {style_var(volume_id)}...")
        try:
            powerstore_connection.provisioning.map_volume_to_host_group(
                volume_id=volume_id, host_group_id=host_group_id
            )
            Console().print(
                f"    {style_var('✓', color='green')} Successfully mapped the volume {style_var(volume_id)} to the host group {style_var(host_group_name)}."
            )
        except PowerStoreException as e:
            if "already mapped" in str(e):
                Console().print(
                    f"    The volume {style_var(volume_id)} is already mapped to the host group {style_var(host_group_name)}."
                )
            else:
                error_and_exit(
                    f"Failed to map the volume {style_var(volume_id, color='yellow')} to the host group {style_var(host_group_name, color='yellow')}.",
                    Rule(),
                    str(e),
                    code=ERR_DELL_API,
                )

    Console().print(
        f"{style_var('✓', color='green')} Successfully mapped {style_var(len(volume_ids))} volumes to the host group {style_var(host_group_name)}."
    )
