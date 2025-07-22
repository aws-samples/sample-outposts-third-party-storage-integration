"""
AWS Secrets Manager operations and helper functions.
"""

from typing import List

import boto3
from botocore.exceptions import ClientError

from launch_wizard.aws.pagination import paginate_aws_response
from launch_wizard.common.error_codes import ERR_AWS_CLIENT
from launch_wizard.utils.ui_utils import error_and_exit


def get_available_secret_names(secrets_manager_client: boto3.client) -> List[str]:
    """
    Retrieve all authentication secret names from AWS Secrets Manager.

    This function queries AWS Secrets Manager to get a list of all available secrets
    that can be used for storage array authentication during instance configuration.

    Args:
        secrets_manager_client: The boto3 Secrets Manager client for AWS API calls.

    Returns:
        A list of secret names as strings.

    Raises:
        typer.Exit: If an AWS error occurs during the API call.
    """

    try:
        available_secrets = paginate_aws_response(secrets_manager_client.list_secrets, "SecretList")

        available_secret_names = [secret["Name"] for secret in available_secrets]

        return available_secret_names
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)
