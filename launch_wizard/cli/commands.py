"""
Main command logic for the CLI application.
"""

from typing import Optional

import typer
from rich.console import Console
from typing_extensions import Annotated

from launch_wizard.aws.aws_client import AWSClient
from launch_wizard.aws.ec2 import (
    validate_ami,
    validate_instance_name,
    validate_instance_profile,
    validate_key_pair,
    validate_network,
    validate_root_volume_options,
    validate_security_group,
    validate_subnet,
)
from launch_wizard.aws.outposts import get_outpost_hardware_type, validate_instance_type
from launch_wizard.common.config import global_config
from launch_wizard.common.constants import AWS_DEFAULT_REGION
from launch_wizard.common.enums import EBSVolumeType, FeatureName, OperationSystemType
from launch_wizard.utils.display_utils import style_var
from launch_wizard.utils.ui_utils import prompt_with_trim


def main_command(
    ctx: typer.Context,
    feature_name: Annotated[FeatureName, typer.Option(prompt=True, case_sensitive=False)],
    guest_os_type: Annotated[OperationSystemType, typer.Option(prompt=True, case_sensitive=False)],
    region_name: Annotated[
        str,
        typer.Option(
            prompt="AWS Region",
            envvar="AWS_DEFAULT_REGION",
            help="AWS Region where the target Outpost is homed",
        ),
    ] = AWS_DEFAULT_REGION,
    ami_id: Annotated[Optional[str], typer.Option(help="ID of the AMI to launch")] = None,
    subnet_id: Annotated[
        Optional[str],
        typer.Option(help="Outpost subnet where the instance will be launched"),
    ] = None,
    instance_type: Annotated[
        Optional[str],
        typer.Option(
            help="Instance type to launch. The Outpost must be configured for this instance type",
        ),
    ] = None,
    key_name: Annotated[Optional[str], typer.Option(help="Key pair name for SSH access")] = None,
    security_group_id: Annotated[
        Optional[str], typer.Option(help="Security group ID to associate with the instance")
    ] = None,
    instance_profile_name: Annotated[
        Optional[str], typer.Option(help="IAM instance profile name to attach to the instance")
    ] = None,
    instance_name: Annotated[Optional[str], typer.Option(help="Name to assign to the EC2 instance")] = None,
    root_volume_size: Annotated[Optional[int], typer.Option(help="Size of the root volume in GiB")] = None,
    root_volume_type: Annotated[Optional[EBSVolumeType], typer.Option(help="Type of the root volume to attach")] = None,
    save_user_data_path: Annotated[
        Optional[str], typer.Option(help="Path to save the generated user data script to a local file")
    ] = None,
    save_user_data_only: Annotated[
        bool,
        typer.Option(help="Generate and save user data only, without launching an EC2 instance"),
    ] = False,
    assume_yes: Annotated[
        bool, typer.Option("--assume-yes", "-y", help="Automatically answer yes to all prompts")
    ] = False,
) -> None:
    """
    Launch EC2 instances with external storage arrays on AWS Outposts.

    This utility provides a simplified EC2 instance launching experience with external storage arrays.
    It has been validated with specific AMIs, though you can use it with other AMIs (results may vary
    depending on the AMI configuration).

    Args:
        ctx: Typer context object for passing data between commands.
        feature_name: The storage feature to configure (data_volumes, localboot, or sanboot).
        guest_os_type: The operating system type (linux or windows).
        region_name: AWS Region where the target Outpost is located.
        ami_id: ID of the AMI to launch (optional, will prompt if not provided).
        subnet_id: Outpost subnet where the instance will be launched (optional, will prompt if not provided).
        instance_type: Instance type to launch (optional, will prompt if not provided).
        key_name: Key pair name for SSH access (optional).
        security_group_id: Security group ID to associate with the instance (optional).
        instance_profile_name: IAM instance profile name to attach to the instance (optional).
        instance_name: Name to assign to the EC2 instance (optional, will prompt if not provided).
        root_volume_size: Size of the root volume in GiB (optional).
        root_volume_type: Type of the root volume to attach (optional).
        save_user_data_path: Path to save the generated user data script to a local file (optional).
        save_user_data_only: Generate and save user data only, without launching an EC2 instance (optional).
        assume_yes: Automatically answer yes to all prompts (optional).
    """

    global_config.assume_yes = assume_yes

    # Validate mutual exclusivity of options
    if save_user_data_only and not save_user_data_path:
        Console().print(f"{style_var('--save-user-data-only')} requires the user data file path to be specified.")
        save_user_data_path = prompt_with_trim("Enter the file path to save user data")

    # Create AWS client wrapper
    aws_client = AWSClient(region_name)

    # Skip AWS validation if only generating user data
    if save_user_data_only:
        # For user data only mode, we only need minimal context
        # Set default values for required context variables
        ami_id = None
        subnet_id = None
        outpost_hardware_type = None
        instance_type = None
        key_name = None
        security_group_id = None
        instance_profile_name = None
        instance_name = None
        root_volume_device_name = None
        root_volume_size = None
        root_volume_type = None
    else:
        # Validate AWS resources and configuration
        ami_id = validate_ami(aws_client.ec2, ami_id)
        subnet_id, outpost_arn = validate_subnet(aws_client.ec2, subnet_id)
        outpost_hardware_type = get_outpost_hardware_type(aws_client.outposts, outpost_arn)
        validate_network(aws_client.ec2, subnet_id, outpost_hardware_type)
        instance_type = validate_instance_type(aws_client.outposts, instance_type, outpost_arn)
        key_name = validate_key_pair(aws_client.ec2, key_name)
        security_group_id = validate_security_group(aws_client.ec2, security_group_id)
        instance_profile_name = validate_instance_profile(aws_client.iam, instance_profile_name)
        instance_name = validate_instance_name(instance_name)

        # Validate and prompt for root volume options if needed
        root_volume_size, root_volume_type, root_volume_device_name = validate_root_volume_options(
            aws_client.ec2, ami_id, root_volume_size, root_volume_type
        )

    # Store validated configuration in context for vendor sub-commands
    ctx.obj = ctx.obj or {}
    ctx.obj.update(
        {
            "feature_name": feature_name,
            "guest_os_type": guest_os_type,
            "aws_client": aws_client,
            "outpost_hardware_type": outpost_hardware_type,
            "ami_id": ami_id,
            "instance_type": instance_type,
            "subnet_id": subnet_id,
            "key_name": key_name,
            "security_group_id": security_group_id,
            "instance_profile_name": instance_profile_name,
            "instance_name": instance_name,
            "root_volume_device_name": root_volume_device_name,
            "root_volume_size": root_volume_size,
            "root_volume_type": root_volume_type,
            "save_user_data_path": save_user_data_path,
            "save_user_data_only": save_user_data_only,
        }
    )
