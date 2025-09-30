"""
Data volumes workflow implementation for HPE storage devices.

This module contains the vendor-specific implementation of the data volumes workflow
for HPE storage devices.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.rule import Rule

from launch_wizard.common.enums import StorageProtocol
from launch_wizard.utils.display_utils import style_var
from launch_wizard.utils.workflow_orchestrator import prepare_secondary_workflow_context, prompt_for_storage_protocol


def execute_data_volumes_workflow(
    ctx: typer.Context,
    default_protocol: StorageProtocol,
    hpe_management_ip: str,
    hpe_username: str,
    hpe_password: str,
) -> Optional[str]:
    """
    Execute a data volumes workflow for HPE and return the generated user data.

    This function leverages the existing HPE workflow by calling it with a secondary context configured for data volumes.

    Args:
        ctx: The original workflow context.
        default_protocol: The default storage protocol to use.
        hpe_management_ip: HPE management IP address.
        hpe_username: HPE username.
        hpe_password: HPE password.

    Returns:
        The generated data volumes user data script, or None if workflow fails.
    """

    # Prompt user to choose storage protocol
    protocol = prompt_for_storage_protocol(default_protocol)

    Console().print(Rule())
    Console().print(style_var("Starting the data volumes configuration workflow..."))

    try:
        # Import the HPE iSCSI and NVMe workflow functions
        from launch_wizard.vendors.hpe.iscsi import iscsi
        from launch_wizard.vendors.hpe.nvme import nvme

        # Prepare context for data volumes workflow with return_user_data flag
        secondary_context = prepare_secondary_workflow_context(ctx)

        # Create a new context object for the data volumes workflow
        data_volumes_ctx = typer.Context(ctx.command, obj=secondary_context)

        # Call the existing HPE iSCSI or NVMe workflow with data volumes context
        # This will automatically handle all the HPE-specific logic without duplication
        if protocol == StorageProtocol.ISCSI:
            user_data = iscsi(
                ctx=data_volumes_ctx,
                hpe_management_ip=hpe_management_ip,
                hpe_username=hpe_username,
                hpe_password=hpe_password,
            )
        elif protocol == StorageProtocol.NVME:
            user_data = nvme(
                ctx=data_volumes_ctx,
                hpe_management_ip=hpe_management_ip,
                hpe_username=hpe_username,
                hpe_password=hpe_password,
            )
        else:
            Console().print(style_var(f"The protocol {protocol} is not supported.", color="red"))
            return None

        Console().print(f"{style_var('✓', color='green')} The data volumes configuration is completed successfully.")
        Console().print(Rule())
        return user_data
    except Exception as e:
        Console().print(f"{style_var('✗', color='red')} The data volumes configuration failed.")
        Console().print(style_var(str(e), color="red"))
        Console().print(Rule())
        return None
