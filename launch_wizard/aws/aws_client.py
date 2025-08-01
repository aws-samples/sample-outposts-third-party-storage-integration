"""
AWS client wrapper for Launch Wizard operations.
"""

import boto3
from botocore.exceptions import NoCredentialsError
from rich.rule import Rule

from launch_wizard.common.error_codes import ERR_AWS_CLIENT
from launch_wizard.utils.ui_utils import error_and_exit


class AWSClient:
    """
    AWS client wrapper for Launch Wizard operations.
    """

    def __init__(self, region: str) -> None:
        """
        Initialize AWS client wrapper.
        """

        self.region = region

        # Initialize storage for lazy loading (including session)
        self._session = None
        self._ec2 = None
        self._iam = None
        self._outposts = None
        self._secrets_manager = None

    # Lazy session property
    @property
    def session(self) -> boto3.Session:
        """
        Lazy initialization of boto3 session.
        """

        if self._session is None:
            try:
                self._session = boto3.Session()
            except NoCredentialsError as e:
                error_and_exit(
                    'AWS credentials not found. Please configure AWS CLI using "aws configure" or set environment variables. Required: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and optionally AWS_SESSION_TOKEN.',
                    Rule(),
                    str(e),
                    code=ERR_AWS_CLIENT,
                )
            except Exception as e:
                error_and_exit("Failed to initialize AWS session.", Rule(), str(e), code=ERR_AWS_CLIENT)
        return self._session

    # Direct client access for backward compatibility with lazy initialization
    @property
    def ec2(self) -> boto3.client:
        """
        Lazy initialization of EC2 client.
        """

        if self._ec2 is None:
            try:
                self._ec2 = self.session.client("ec2", region_name=self.region)
            except Exception as e:
                error_and_exit("Failed to initialize EC2 client.", Rule(), str(e), code=ERR_AWS_CLIENT)
        return self._ec2

    @property
    def iam(self) -> boto3.client:
        """
        Lazy initialization of IAM client.
        """

        if self._iam is None:
            try:
                self._iam = self.session.client("iam", region_name=self.region)
            except Exception as e:
                error_and_exit("Failed to initialize IAM client.", Rule(), str(e), code=ERR_AWS_CLIENT)
        return self._iam

    @property
    def outposts(self) -> boto3.client:
        """
        Lazy initialization of Outposts client.
        """

        if self._outposts is None:
            try:
                self._outposts = self.session.client("outposts", region_name=self.region)
            except Exception as e:
                error_and_exit("Failed to initialize Outposts client.", Rule(), str(e), code=ERR_AWS_CLIENT)
        return self._outposts

    @property
    def secrets_manager(self) -> boto3.client:
        """
        Lazy initialization of Secrets Manager client.
        """

        if self._secrets_manager is None:
            try:
                self._secrets_manager = self.session.client("secretsmanager", region_name=self.region)
            except Exception as e:
                error_and_exit("Failed to initialize Secrets Manager client.", Rule(), str(e), code=ERR_AWS_CLIENT)
        return self._secrets_manager
