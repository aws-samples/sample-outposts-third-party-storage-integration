"""
AWS resource discovery operations and helper functions.
"""

from typing import List

import boto3

from launch_wizard.aws.pagination import paginate_aws_response


def get_available_instance_profile_names(iam_client: boto3.client) -> List[str]:
    """
    Retrieve all IAM instance profile names available in the AWS account.

    This function queries all IAM instance profiles in the account and returns their names
    for use in granting AWS service permissions to EC2 instances.

    Args:
        iam_client: The boto3 IAM client for AWS API calls.

    Returns:
        A list of instance profile names as strings.

    Raises:
        typer.Exit: If an AWS error occurs during the API call.
    """

    # IAM uses different pagination parameters - "Marker" instead of "NextToken"
    available_instance_profiles = paginate_aws_response(
        iam_client.list_instance_profiles, "InstanceProfiles", next_token_key="Marker"
    )

    available_instance_profile_names = [
        instance_profile["InstanceProfileName"] for instance_profile in available_instance_profiles
    ]

    return available_instance_profile_names
