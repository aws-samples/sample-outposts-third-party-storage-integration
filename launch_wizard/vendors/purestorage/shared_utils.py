from typing import List, Optional

from pypureclient import flasharray
from pypureclient.exceptions import PureError
from pypureclient.responses import ErrorResponse
from rich.console import Console
from rich.pretty import Pretty
from rich.rule import Rule

from launch_wizard.common.error_codes import ERR_INPUT_INVALID, ERR_PURE_API, ERR_USER_ABORT, ERR_VOLUME_NOT_FOUND
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import print_table_with_multiple_columns, style_var
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim


def pure_get_volume_uuids(pure_client: flasharray.Client, volume_names: Optional[List[str]]) -> List[str]:
    """
    Retrieve Pure Storage FlashArray volume UUIDs by name.

    This function retrieves volume UUIDs for the specified volume names from the Pure Storage
    FlashArray. If no volume names are provided, it displays all available volumes and prompts
    the user to select them interactively. Only non-destroyed volumes are considered.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        volume_names: List of volume names to retrieve UUIDs for. If None, user will be prompted.

    Returns:
        List of volume UUIDs corresponding to the specified or selected volume names.

    Raises:
        typer.Exit: If no volumes are specified, specified volumes don't exist,
                   or if a Pure Storage API error occurs.
    """

    available_volumes = []
    try:
        for volume_item in pure_client.get_volumes().items:
            if not volume_item.destroyed:
                available_volumes.append({"name": volume_item.name, "uuid": volume_item.id})
    except PureError as e:
        error_and_exit(
            "Failed to retrieve available volumes.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )

    if not volume_names:
        volume_names = []
        print_table_with_multiple_columns("Available volumes", available_volumes)
        Console().print("Enter volume names one by one. Press Enter on an empty line when finished.")
        while True:
            volume_name = prompt_with_trim("Volume name", default="")
            if volume_name == "":
                break
            volume_names.append(volume_name)

        # Must provide at least one volume name
        if not volume_names:
            error_and_exit("You must specify at least one volume name to continue.", code=ERR_INPUT_INVALID)

    # Get all the selected volumes
    selected_volumes = []
    for volume_name in volume_names:
        # Find the volume from available volumes
        volume = find_first_by_property(items=available_volumes, key="name", value=volume_name)
        if volume:
            selected_volumes.append(volume)
        else:
            error_and_exit(
                f"Volume {style_var(volume_name, color='yellow')} does not exist.",
                code=ERR_VOLUME_NOT_FOUND,
            )

    print_table_with_multiple_columns("Selected volumes to be used", selected_volumes)

    if not auto_confirm("Would you like to proceed with these volumes?"):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    selected_volume_uuids = [volume["uuid"] for volume in selected_volumes]

    return selected_volume_uuids


def pure_get_host_group_name(pure_client: flasharray.Client, host_group_name: Optional[str]) -> Optional[str]:
    """
    Retrieve or prompt for a Pure Storage FlashArray host group name.

    This function validates the provided host group name or prompts the user to select
    from available host groups or create a new one. If no host group name is provided,
    it offers the option to proceed without using a host group.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        host_group_name: Name of the host group to validate. If None, user will be prompted.

    Returns:
        The validated host group name, or None if proceeding without a host group.

    Raises:
        typer.Exit: If host group information cannot be retrieved or if a Pure Storage API error occurs.
    """

    if not host_group_name:
        if auto_confirm("No host group name specified. Would you like to proceed without using a host group?"):
            return None

        available_host_groups = []
        try:
            for host_group_item in pure_client.get_host_groups().items:
                available_host_groups.append(
                    {
                        "name": host_group_item.name,
                        "connection_count": host_group_item.connection_count,
                        "host_count": host_group_item.host_count,
                        "is_local": host_group_item.is_local,
                    }
                )
        except PureError as e:
            error_and_exit(
                "Failed to retrieve available host groups.",
                Rule(),
                str(e),
                code=ERR_PURE_API,
            )

        print_table_with_multiple_columns("Available host groups", available_host_groups)

        host_group_name = prompt_with_trim("Please enter an existing host group name or specify a new name")

        if host_group_name:
            Console().print(f"Using host group name: {style_var(host_group_name)}.")
        else:
            error_and_exit("Host group name cannot be empty.", code=ERR_INPUT_INVALID)

    return host_group_name


def pure_get_host_name(pure_client: flasharray.Client, host_name: Optional[str]) -> str:
    """
    Retrieve or prompt for a Pure Storage FlashArray host name.

    This function validates the provided host name or prompts the user to select
    from available hosts or create a new one. It displays existing hosts with
    their connection details and associated IQNs/NQNs.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        host_name: Name of the host to validate. If None, user will be prompted.

    Returns:
        The validated host name.

    Raises:
        typer.Exit: If no host name is provided, host information cannot be retrieved,
                   or if a Pure Storage API error occurs.
    """

    if not host_name:
        available_hosts = []
        try:
            for host_item in pure_client.get_hosts().items:
                available_hosts.append(
                    {
                        "name": host_item.name,
                        "connection_count": host_item.connection_count,
                        "is_local": host_item.is_local,
                        "iqns": host_item.iqns,
                        "nqns": host_item.nqns,
                    }
                )
        except PureError as e:
            error_and_exit(
                "Failed to retrieve available hosts.",
                Rule(),
                str(e),
                code=ERR_PURE_API,
            )

        print_table_with_multiple_columns("Available hosts", available_hosts)

        host_name = prompt_with_trim("Please enter an existing host name or specify a new name")

        if host_name:
            Console().print(f"Using host name: {style_var(host_name)}.")
        else:
            error_and_exit("Host name cannot be empty.", code=ERR_INPUT_INVALID)

    return host_name


def pure_create_host_group(pure_client: flasharray.Client, host_group_name: str, host_name: str) -> None:
    """
    Create a Pure Storage FlashArray host group and add a host to it.

    This function creates a new host group with the specified name and adds the given
    host to it. If the host group already exists, it adds the host to the existing group.
    If the host is already in the group, it reports this without error.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        host_group_name: Name of the host group to create or modify.
        host_name: Name of the host to add to the host group.

    Raises:
        typer.Exit: If the host group cannot be created or modified, or if a Pure Storage API error occurs.
    """

    # Create the host group
    try:
        response = pure_client.post_host_groups(names=[host_group_name])
        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "Host group already exists.":
                Console().print(f"Host group {style_var(host_group_name)} already exists.")
            else:
                error_and_exit(
                    f"Failed to create host group {style_var(host_group_name, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to create host group {style_var(host_group_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )

    # Add the host to the host group
    try:
        response = pure_client.post_host_groups_hosts(member_names=[host_name], group_names=[host_group_name])
        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "Host is connected to a volume which is also connected to the host group.":
                Console().print(
                    f"Host {style_var(host_name)} is already connected to a volume which is also connected to host group {style_var(host_group_name)}."
                )
            else:
                error_and_exit(
                    f"Failed to add host {style_var(host_name, color='yellow')} to host group {style_var(host_group_name, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to add host {style_var(host_name, color='yellow')} to host group {style_var(host_group_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )


def pure_connect_volumes_to_host(
    pure_client: flasharray.Client,
    volume_uuids: List[str],
    host_name: str,
) -> None:
    """
    Connect Pure Storage FlashArray volumes to a specific host.

    This function creates connections between the specified volumes and host,
    making the volumes accessible to the host. If connections already exist,
    it reports this without error.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        volume_uuids: List of volume UUIDs to connect to the host.
        host_name: Name of the host to connect volumes to.

    Raises:
        typer.Exit: If the volume connections cannot be created or if a Pure Storage API error occurs.
    """

    # Connect the volumes to the host
    try:
        response = pure_client.post_connections(host_names=[host_name], volume_ids=[",".join(volume_uuids)])

        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "Connection already exists.":
                Console().print(
                    f"Volumes {style_var(str(volume_uuids))} are already connected to host {style_var(host_name)}."
                )
            else:
                error_and_exit(
                    f"Failed to connect volumes {style_var(', '.join(volume_uuids), color='yellow')} to host {style_var(host_name, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to connect volumes {style_var(', '.join(volume_uuids), color='yellow')} to host {style_var(host_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )


def pure_connect_volumes_to_host_group(
    pure_client: flasharray.Client,
    volume_uuids: List[str],
    host_group_name: str,
) -> None:
    """
    Connect Pure Storage FlashArray volumes to a specific host group.

    This function creates connections between the specified volumes and host group,
    making the volumes accessible to all hosts in the group. If connections already
    exist, it reports this without error.

    Args:
        pure_client: Pure Storage FlashArray client instance.
        volume_uuids: List of volume UUIDs to connect to the host group.
        host_group_name: Name of the host group to connect volumes to.

    Raises:
        typer.Exit: If the volume connections cannot be created or if a Pure Storage API error occurs.
    """

    # Connect the volumes to the host group
    try:
        response = pure_client.post_connections(
            host_group_names=[host_group_name],
            volume_ids=[",".join(volume_uuids)],
        )

        if isinstance(response, ErrorResponse):
            if response.errors[0].message == "Connection already exists.":
                Console().print(
                    f"Volumes {style_var(', '.join(volume_uuids))} are already connected to host group {style_var(host_group_name)}."
                )
            else:
                error_and_exit(
                    f"Failed to connect volumes {style_var(', '.join(volume_uuids), color='yellow')} to host group {style_var(host_group_name, color='yellow')}.",
                    Rule(),
                    Pretty(response),
                    code=ERR_PURE_API,
                )
    except PureError as e:
        error_and_exit(
            f"Failed to connect volumes {style_var(', '.join(volume_uuids), color='yellow')} to host group {style_var(host_group_name, color='yellow')}.",
            Rule(),
            str(e),
            code=ERR_PURE_API,
        )
