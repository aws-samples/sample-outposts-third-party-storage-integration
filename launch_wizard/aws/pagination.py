"""
AWS pagination utilities.
"""

from typing import Any, Callable, Dict, List

from botocore.exceptions import ClientError

from launch_wizard.common.error_codes import ERR_AWS_CLIENT
from launch_wizard.utils.ui_utils import error_and_exit


def paginate_aws_response(
    client_method: Callable, response_key: str, next_token_key: str = "NextToken", **kwargs: Any
) -> List[Dict[str, Any]]:
    """
    Handle paginated AWS API responses by collecting all items across multiple pages.

    This function automatically handles pagination for AWS API calls that return paginated results,
    collecting all items from all pages into a single list.

    Args:
        client_method: The boto3 client method to call (e.g., ec2_client.describe_subnets).
        response_key: The key in the response that contains the list of items.
        next_token_key: The key used for pagination token. Defaults to "NextToken".
        **kwargs: Additional parameters to pass to the client method.

    Returns:
        List of all items collected from all pages of the API response.

    Raises:
        typer.Exit: If an AWS client error occurs during the API calls.
    """

    all_items = []
    next_token = None

    try:
        while True:
            # Prepare parameters for the API call
            params = kwargs.copy()
            if next_token:
                params[next_token_key] = next_token

            # Make the API call
            response = client_method(**params)

            # Add items from this page to our list
            all_items.extend(response.get(response_key, []))

            # Check if there are more results
            next_token = response.get(next_token_key)
            if not next_token:
                break
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)

    return all_items
