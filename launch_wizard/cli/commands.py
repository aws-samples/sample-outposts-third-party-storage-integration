"""
Main command logic for the CLI application.
"""

from typing import Optional

import boto3
import typer
from botocore.exceptions import ClientError
from typing_extensions import Annotated

from launch_wizard.aws.ec2 import (
    validate_ami,
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
from launch_wizard.common.error_codes import ERR_AWS_CLIENT
from launch_wizard.utils.ui_utils import error_and_exit


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
    root_volume_size: Annotated[Optional[int], typer.Option(help="Size of the root volume in GiB")] = None,
    root_volume_type: Annotated[Optional[EBSVolumeType], typer.Option(help="Type of the root volume to attach")] = None,
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
        root_volume_size: Size of the root volume in GiB (optional).
        root_volume_type: Type of the root volume to attach (optional).
        assume_yes: Automatically answer yes to all prompts (optional).
    """

    global_config.assume_yes = assume_yes

    # Create AWS service clients
    try:
        ec2_client = boto3.client("ec2", region_name=region_name)
        iam_client = boto3.client("iam", region_name=region_name)
        outposts_client = boto3.client("outposts", region_name=region_name)
        secrets_manager_client = boto3.client("secretsmanager", region_name=region_name)
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)

    # Validate AWS resources and configuration
    ami_id = validate_ami(ec2_client, ami_id)
    subnet_id, outpost_arn = validate_subnet(ec2_client, subnet_id)
    outpost_hardware_type = get_outpost_hardware_type(outposts_client, outpost_arn)
    validate_network(ec2_client, subnet_id, outpost_hardware_type)
    instance_type = validate_instance_type(outposts_client, instance_type, outpost_arn)
    key_name = validate_key_pair(ec2_client, key_name)
    security_group_id = validate_security_group(ec2_client, security_group_id)
    instance_profile_name = validate_instance_profile(iam_client, instance_profile_name)

    # Validate and prompt for root volume options if needed
    root_volume_size, root_volume_type, root_volume_device_name = validate_root_volume_options(
        ec2_client, ami_id, root_volume_size, root_volume_type
    )

    # Store validated configuration in context for vendor sub-commands
    ctx.obj = ctx.obj or {}
    ctx.obj.update(
        {
            "feature_name": feature_name,
            "guest_os_type": guest_os_type,
            "outpost_hardware_type": outpost_hardware_type,
            "ec2_client": ec2_client,
            "secrets_manager_client": secrets_manager_client,
            "ami_id": ami_id,
            "instance_type": instance_type,
            "subnet_id": subnet_id,
            "key_name": key_name,
            "security_group_id": security_group_id,
            "instance_profile_name": instance_profile_name,
            "root_volume_device_name": root_volume_device_name,
            "root_volume_size": root_volume_size,
            "root_volume_type": root_volume_type,
        }
    )
