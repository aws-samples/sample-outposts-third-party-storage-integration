"""
AWS Outposts operations and helper functions.
"""

from typing import List, Optional, cast

import boto3
from botocore.exceptions import ClientError
from rich.console import Console

from launch_wizard.aws.pagination import paginate_aws_response
from launch_wizard.common.enums import OutpostHardwareType
from launch_wizard.common.error_codes import (
    ERR_AWS_CLIENT,
    ERR_AWS_INSTANCE_TYPE_UNSUPPORTED,
    ERR_AWS_UNSUPPORTED_HARDWARE_TYPE,
)
from launch_wizard.utils.display_utils import print_table_with_single_column, style_var
from launch_wizard.utils.ui_utils import error_and_exit, prompt_with_trim


def validate_instance_type(
    outposts_client: boto3.client,
    instance_type: Optional[str],
    outpost_id: str,
) -> str:
    """
    Validate that the specified instance type is available on the target Outpost.

    This function retrieves all available instance types for the specified Outpost and validates
    that the provided instance type is supported. If no instance type is provided, it displays
    available options and prompts the user to select one.

    Args:
        outposts_client: The boto3 Outposts client for AWS API calls.
        instance_type: The instance type to validate. If None, the user will be prompted to select one.
        outpost_id: The ID or ARN of the Outpost to check instance type availability.

    Returns:
        The validated instance type as a string.

    Raises:
        typer.Exit: If the instance type is not available on the Outpost or if an AWS error occurs.
    """

    available_instance_types = get_available_instance_types(outposts_client, outpost_id)

    if not instance_type:
        print_table_with_single_column(
            "Available instance types for this Outpost", available_instance_types, column_name="Instance Type"
        )

        instance_type = prompt_with_trim("Please enter an instance type")
        instance_type = cast(str, instance_type)

    if instance_type not in available_instance_types:
        error_and_exit(
            f"Instance type {style_var(instance_type, color='yellow')} is not available on this Outpost.",
            code=ERR_AWS_INSTANCE_TYPE_UNSUPPORTED,
        )

    return instance_type


def get_outpost_hardware_type(outposts_client: boto3.client, outpost_arn: str) -> OutpostHardwareType:
    """
    Determine the hardware type of the specified AWS Outpost.

    This function queries the Outpost details to determine whether it's a RACK or SERVER
    hardware type. This information is important for network configuration, as SERVER
    hardware requires Local Network Interface (LNI) configuration for proper connectivity.

    Args:
        outposts_client: The boto3 Outposts client for AWS API calls.
        outpost_arn: The ARN of the Outpost to query.

    Returns:
        The hardware type of the Outpost (RACK or SERVER).

    Raises:
        typer.Exit: If the Outpost is not found, has an unsupported hardware type, or if an AWS error occurs.
    """

    # Check if the device is a rack or a server.
    # Validate that the subnet has properly setup LNI defaults.
    # On Outpost Servers, without an LNI an instance won't be able to connect to the
    # the on-premise network, which is not the VPC subnet that the instance will be
    # launched into.
    try:
        get_outpost_response = outposts_client.get_outpost(OutpostId=outpost_arn)
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)

    outpost = get_outpost_response["Outpost"]

    try:
        outpost_hardware_type = OutpostHardwareType(outpost["SupportedHardwareType"])
        Console().print(f"This Outpost is a {style_var(outpost_hardware_type.value)}.")
    except ValueError:
        error_and_exit(
            f"The hardware type {style_var(outpost['SupportedHardwareType'], color='yellow')} is not supported.",
            code=ERR_AWS_UNSUPPORTED_HARDWARE_TYPE,
        )

    return outpost_hardware_type


def get_available_instance_types(outposts_client: boto3.client, outpost_id: str) -> List[str]:
    """
    Retrieve all instance types available on the specified AWS Outpost.

    This function queries the Outpost to get a list of all instance types that are
    configured and available for launching instances.

    Args:
        outposts_client: The boto3 Outposts client for AWS API calls.
        outpost_id: The ID or ARN of the Outpost to query.

    Returns:
        A list of available instance type names as strings.

    Raises:
        typer.Exit: If an AWS error occurs during the API call.
    """

    # Use the paginate function to get all instance types
    instance_type_response_items = paginate_aws_response(
        outposts_client.get_outpost_instance_types, "InstanceTypes", OutpostId=outpost_id
    )

    # Extract the InstanceTypes property from each response item
    available_instance_types = [
        instance_type_response_item["InstanceType"] for instance_type_response_item in instance_type_response_items
    ]

    return available_instance_types
