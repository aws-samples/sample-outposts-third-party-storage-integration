"""AWS client wrapper for VMIE operations."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from rich.rule import Rule

from vmie.aws.aws_waiter import AWSWaiter
from vmie.common import (
    DEFAULT_INSTANCE_PROFILE,
    EC2_TRUST_POLICY,
    ERR_AWS_AMI_CREATE_FAILED,
    ERR_AWS_AMI_FETCH_FAILED,
    ERR_AWS_AMI_NOT_FOUND,
    ERR_AWS_AMI_PLATFORM_CHECK_FAILED,
    ERR_AWS_CLIENT_INIT_FAILED,
    ERR_AWS_CREDENTIALS_NOT_FOUND,
    ERR_AWS_EXPORT_TASK_FAILED,
    ERR_AWS_IMPORT_TASK_FAILED,
    ERR_AWS_INSTANCE_LAUNCH_FAILED,
    ERR_AWS_INSTANCE_NO_BLOCK_DEVICES,
    ERR_AWS_INSTANCE_NOT_FOUND,
    ERR_AWS_INSTANCE_PROFILE_CREATE_FAILED,
    ERR_AWS_S3_BUCKET_CREATE_FAILED,
    ERR_AWS_S3_UPLOAD_FAILED,
    ERR_AWS_SSM_COMMAND_FAILED,
    ERR_AWS_SSM_SCRIPT_LOAD_FAILED,
    ERR_AWS_SSM_SCRIPT_NOT_FOUND,
    ERR_AWS_VMIMPORT_ROLE_SETUP_FAILED,
    EXPORT_TIMEOUT_MINUTES,
    IMPORT_TIMEOUT_MINUTES,
    VMIMPORT_EC2_INLINE_POLICY,
    VMIMPORT_ROLE_NAME,
    VMIMPORT_TRUST_POLICY,
    LogLevel,
    get_vmimport_bucket_inline_policy,
)
from vmie.utils import error_and_exit, log_message


class AWSClient:
    """AWS client wrapper for VMIE operations."""

    def __init__(self, region: str):
        """Initialize AWS client."""
        self.region = region

        try:
            self.session = boto3.Session()
            self.ec2 = self.session.client("ec2", region_name=region)
            self.s3 = self.session.client("s3", region_name=region)
            self.iam = self.session.client("iam")
            self.ssm = self.session.client("ssm", region_name=region)

            # Initialize waiter with clients
            self.waiter = AWSWaiter(self.ec2, self.ssm, self.iam)
        except NoCredentialsError as e:
            error_and_exit(
                "AWS credentials not found",
                "Please configure AWS CLI using 'aws configure' or set environment variables",
                "Required: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and optionally AWS_SESSION_TOKEN",
                Rule(),
                str(e),
                code=ERR_AWS_CREDENTIALS_NOT_FOUND,
            )
        except Exception as e:
            error_and_exit(
                "Failed to initialize AWS clients",
                Rule(),
                str(e),
                code=ERR_AWS_CLIENT_INIT_FAILED,
            )

    def get_ami(self, ami_id: str) -> Dict[str, Any]:
        """Fetches the AMI details."""
        try:
            response = self.ec2.describe_images(ImageIds=[ami_id])
            if not response["Images"]:
                error_and_exit(
                    f"AMI not found: {ami_id}",
                    "Please verify the AMI ID and region are correct",
                    code=ERR_AWS_AMI_NOT_FOUND,
                )

            ami = response["Images"][0]
            return ami
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidAMIID.NotFound":
                error_and_exit(
                    f"AMI not found: {ami_id}",
                    "Please verify the AMI ID and region are correct",
                    Rule(),
                    str(e),
                    code=ERR_AWS_AMI_NOT_FOUND,
                )
            error_and_exit(
                "Failed to fetch AMI details",
                Rule(),
                str(e),
                code=ERR_AWS_AMI_FETCH_FAILED,
            )

    def is_windows_ami(self, ami_id: str) -> bool:
        """Check if an AMI is a Windows AMI."""
        try:
            response = self.ec2.describe_images(ImageIds=[ami_id])
            if not response["Images"]:
                error_and_exit(
                    f"AMI not found: {ami_id}",
                    "Please verify the AMI ID and region are correct",
                    code=ERR_AWS_AMI_NOT_FOUND,
                )

            image = response["Images"][0]
            platform = image.get("Platform", "")
            return platform == "windows"

        except Exception as e:
            error_and_exit(
                "Failed to check AMI platform",
                Rule(),
                str(e),
                code=ERR_AWS_AMI_PLATFORM_CHECK_FAILED,
            )

    def create_s3_bucket(self, bucket_name: str) -> bool:
        """Create S3 bucket if it doesn't exist."""
        try:
            # Check if bucket exists
            try:
                self.s3.head_bucket(Bucket=bucket_name)
                log_message(LogLevel.INFO, f"S3 bucket already exists: {bucket_name}")
                return True
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    raise

            # Create bucket
            if self.region == "us-east-1":
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": self.region})

            log_message(LogLevel.SUCCESS, f"S3 bucket created successfully: {bucket_name}")
            return True
        except ClientError as e:
            error_and_exit(
                f"Failed to create S3 bucket: {bucket_name}",
                Rule(),
                str(e),
                code=ERR_AWS_S3_BUCKET_CREATE_FAILED,
            )

    def upload_to_s3(self, local_file: str, bucket: str, key: str) -> str:
        """Upload file to S3 and return S3 URL."""
        try:
            self.s3.upload_file(
                local_file,
                bucket,
                key,
                ExtraArgs={
                    "StorageClass": "STANDARD_IA",
                    "Metadata": {
                        "uploaded-by": "vmie-script",
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                },
            )

            s3_url = f"s3://{bucket}/{key}"
            log_message(LogLevel.SUCCESS, f"File uploaded to S3: {s3_url}")
            return s3_url
        except Exception as e:
            error_and_exit(
                f"Failed to upload file to S3: {bucket}/{key}",
                Rule(),
                str(e),
                code=ERR_AWS_S3_UPLOAD_FAILED,
            )

    def setup_vmimport_role(self, bucket_name: str) -> None:
        """Set up vmimport IAM role for VM import operations."""
        try:
            # Check if role exists
            try:
                self.iam.get_role(RoleName=VMIMPORT_ROLE_NAME)
                log_message(LogLevel.INFO, "vmimport role already exists")
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchEntity":
                    # Create role
                    self.iam.create_role(
                        RoleName=VMIMPORT_ROLE_NAME, AssumeRolePolicyDocument=json.dumps(VMIMPORT_TRUST_POLICY)
                    )
                    log_message(LogLevel.INFO, "vmimport role created")
                else:
                    raise

            # Update role policies
            self.iam.put_role_policy(
                RoleName=VMIMPORT_ROLE_NAME, PolicyName="ec2", PolicyDocument=json.dumps(VMIMPORT_EC2_INLINE_POLICY)
            )
            self.iam.put_role_policy(
                RoleName=VMIMPORT_ROLE_NAME,
                PolicyName=bucket_name,
                PolicyDocument=json.dumps(get_vmimport_bucket_inline_policy(bucket_name)),
            )
            self.waiter.wait_for_role_update(VMIMPORT_ROLE_NAME)

            log_message(LogLevel.SUCCESS, "VM import role configured successfully")
        except Exception as e:
            error_and_exit(
                "Failed to setup VM import role",
                "Check IAM permissions for role creation and policy attachment",
                Rule(),
                str(e),
                code=ERR_AWS_VMIMPORT_ROLE_SETUP_FAILED,
            )

    def _execute_import_task(
        self,
        disk_containers: List[Dict],
        description: str,
        license_type: Optional[str] = None,
        usage_operation: Optional[str] = None,
    ) -> str:
        """
        Private helper method to execute image import task.

        :param disk_containers: List of disk container configurations
        :param description: Description of the import task
        :param license_type: License type to be used for the AMI (AWS or BYOL)
        :param usage_operation: Usage operation value for the AMI
        :return: AMI ID
        """
        try:
            # Build the import parameters
            import_params = {"Description": description, "DiskContainers": disk_containers}

            # Add optional parameters if provided
            if license_type:
                import_params["LicenseType"] = license_type

            if usage_operation:
                import_params["UsageOperation"] = usage_operation

            response = self.ec2.import_image(**import_params)
            task_id = response["ImportTaskId"]
            log_message(LogLevel.SUCCESS, f"Import task started: {task_id}")
            ami_id = self.waiter.wait_for_import(task_id, IMPORT_TIMEOUT_MINUTES)
            return ami_id
        except Exception as e:
            error_and_exit(
                "Failed to start import task",
                Rule(),
                str(e),
                code=ERR_AWS_IMPORT_TASK_FAILED,
            )

    def import_image(
        self,
        s3_url: str,
        description: str,
        format_type: str,
        license_type: Optional[str] = None,
        usage_operation: Optional[str] = None,
    ) -> str:
        """
        Import VM image from S3 and return AMI ID.

        :param s3_url: S3 URL of the image to import
        :param description: Description of the import task
        :param format_type: Format type of the image
        :param license_type: License type to be used for the AMI (AWS or BYOL)
        :param usage_operation: Usage operation value for the AMI
        :return: AMI ID
        """
        bucket, key = s3_url.replace("s3://", "").split("/", 1)
        disk_containers = [
            {
                "Description": description,
                "Format": format_type.upper(),
                "UserBucket": {"S3Bucket": bucket, "S3Key": key},
            }
        ]
        return self._execute_import_task(disk_containers, description, license_type, usage_operation)

    def import_image_from_disk_containers(
        self,
        disk_containers: List[Dict],
        description: str,
        license_type: Optional[str] = None,
        usage_operation: Optional[str] = None,
    ) -> str:
        """
        Import VM image from disk containers and return AMI ID.

        :param disk_containers: List of disk container configurations
        :param description: Description of the import task
        :param license_type: License type to be used for the AMI (AWS or BYOL)
        :param usage_operation: Usage operation value for the AMI
        :return: AMI ID
        """
        return self._execute_import_task(disk_containers, description, license_type, usage_operation)

    def export_image(self, ami_id: str, s3_bucket: str, s3_prefix: str, description: str) -> str:
        """Export AMI to S3 and return task ID."""
        try:
            response = self.ec2.export_image(
                ImageId=ami_id,
                DiskImageFormat="RAW",
                S3ExportLocation={"S3Bucket": s3_bucket, "S3Prefix": s3_prefix},
                Description=description,
            )

            task_id = response["ExportImageTaskId"]
            log_message(LogLevel.SUCCESS, f"Export task started: {task_id}")
            export_url = self.waiter.wait_for_export(task_id, EXPORT_TIMEOUT_MINUTES)
            return export_url
        except Exception as e:
            error_and_exit(
                "Failed to start export task",
                Rule(),
                str(e),
                code=ERR_AWS_EXPORT_TASK_FAILED,
            )

    def create_instance_profile(self, profile_name: str = DEFAULT_INSTANCE_PROFILE) -> str:
        """Create IAM instance profile for SSM access."""
        try:
            role_name = f"{profile_name}Role"

            # Create role
            try:
                self.iam.get_role(RoleName=role_name)
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchEntity":
                    self.iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(EC2_TRUST_POLICY))

            # Attach AWS managed policy for SSM access
            self.iam.attach_role_policy(
                RoleName=role_name, PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
            )

            # Create instance profile
            try:
                self.iam.get_instance_profile(InstanceProfileName=profile_name)
            except ClientError as e:
                if e.response["Error"]["Code"] == "NoSuchEntity":
                    self.iam.create_instance_profile(InstanceProfileName=profile_name)

            # Attach role to instance profile
            try:
                self.iam.add_role_to_instance_profile(InstanceProfileName=profile_name, RoleName=role_name)
                self.waiter.wait_for_instance_profile(profile_name)
            except ClientError as e:
                # Role is already attached to the instance profile
                if e.response["Error"]["Code"] == "LimitExceeded":
                    pass

            log_message(LogLevel.SUCCESS, f"Instance profile ready: {profile_name}")
            return profile_name
        except Exception as e:
            error_and_exit(
                f"Failed to create instance profile: {profile_name}",
                Rule(),
                str(e),
                code=ERR_AWS_INSTANCE_PROFILE_CREATE_FAILED,
            )

    def launch_instance(self, ami_id: str, instance_type: str, instance_profile: str) -> str:
        """Launch EC2 instance and return instance ID."""
        try:
            response = self.ec2.run_instances(
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=instance_type,
                IamInstanceProfile={"Name": instance_profile},
                TagSpecifications=[
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": "VMIE-Sanbootable-Install"},
                            {"Key": "CreatedBy", "Value": "vmie-script"},
                        ],
                    }
                ],
                UserData=self._get_ssm_install_script(),
            )

            instance_id = response["Instances"][0]["InstanceId"]
            log_message(LogLevel.SUCCESS, f"Instance launched: {instance_id}")
            return instance_id
        except Exception as e:
            error_and_exit(
                "Failed to launch instance",
                Rule(),
                str(e),
                code=ERR_AWS_INSTANCE_LAUNCH_FAILED,
            )

    def _get_ssm_install_script(self) -> str:
        """Get the SSM installation script content for user data."""
        try:

            script_path = Path(__file__).parent.parent / "scripts" / "install_ssm.sh"

            if not script_path.exists():
                error_and_exit(
                    "SSM install script not found",
                    f"Expected path: {script_path}",
                    "Please ensure the installation script is included in the package",
                    code=ERR_AWS_SSM_SCRIPT_NOT_FOUND,
                )

            # Read the script content
            with open(script_path, "r", encoding="utf-8") as f:
                script_content = f.read()

            return script_content

        except Exception as e:
            error_and_exit(
                "Failed to load SSM install script",
                Rule(),
                str(e),
                code=ERR_AWS_SSM_SCRIPT_LOAD_FAILED,
            )

    def execute_ssm_command(self, instance_id: str, commands: List[str], timeout_seconds: int = 1800) -> None:
        """Execute SSM commands on instance.

        Args:
            instance_id: EC2 instance ID
            commands: List of command strings to execute
            timeout_seconds: Command timeout in seconds

        Returns:
            bool: True if successful, False otherwise
        """
        try:

            response = self.ssm.send_command(
                InstanceIds=[instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={"commands": commands},
                TimeoutSeconds=timeout_seconds,
            )

            command_id = response["Command"]["CommandId"]
            log_message(LogLevel.INFO, f"SSM command sent: {command_id}")

            self.waiter.wait_for_ssm_command(command_id, instance_id)
            log_message(LogLevel.SUCCESS, f"SSM command completed successfully: {command_id}")

        except Exception as e:
            error_and_exit(
                "Failed to execute SSM command",
                Rule(),
                str(e),
                code=ERR_AWS_SSM_COMMAND_FAILED,
            )

    def terminate_instance(self, instance_id: str) -> None:
        """Terminate EC2 instance."""
        try:
            self.ec2.terminate_instances(InstanceIds=[instance_id])
            log_message(LogLevel.INFO, f"Instance terminated: {instance_id}")
        except Exception as e:
            log_message(LogLevel.WARN, f"Failed to terminate instance {instance_id}: {e}")

    def create_ami_from_instance(self, instance_id: str, name: str, description: str, original_ami_id: str) -> str:
        """Create AMI from instance using snapshot approach, supporting multiple volumes."""
        try:
            log_message(LogLevel.INFO, "Creating snapshots and new AMI...")

            # Get instance details
            instance_response = self.ec2.describe_instances(InstanceIds=[instance_id])
            if not instance_response["Reservations"] or not instance_response["Reservations"][0]["Instances"]:
                error_and_exit(
                    f"Instance not found: {instance_id}",
                    "Please verify the instance ID",
                    code=ERR_AWS_INSTANCE_NOT_FOUND,
                )

            instance = instance_response["Reservations"][0]["Instances"][0]
            if not instance.get("BlockDeviceMappings"):
                error_and_exit(
                    f"No block device mappings found for instance: {instance_id}",
                    "Instance must have attached volumes to create an AMI",
                    code=ERR_AWS_INSTANCE_NO_BLOCK_DEVICES,
                )

            # Create snapshots for all volumes
            snapshots = {}
            for bdm in instance["BlockDeviceMappings"]:
                if "Ebs" in bdm:
                    volume_id = bdm["Ebs"]["VolumeId"]
                    device_name = bdm["DeviceName"]
                    log_message(LogLevel.INFO, f"Creating snapshot for volume {volume_id} ({device_name})...")

                    snapshot_response = self.ec2.create_snapshot(
                        VolumeId=volume_id,
                        Description=f"{name} snapshot for {device_name} - {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
                        TagSpecifications=[
                            {
                                "ResourceType": "snapshot",
                                "Tags": [
                                    {"Key": "Name", "Value": f"{name}-sanbootable-snapshot-{device_name}"},
                                    {"Key": "CreatedBy", "Value": "vmie-script"},
                                ],
                            }
                        ],
                    )
                    snapshots[device_name] = snapshot_response["SnapshotId"]

            # Wait for all snapshots to complete
            for snapshot_id in snapshots.values():
                self.waiter.wait_for_snapshot_completed(snapshot_id)
                log_message(LogLevel.SUCCESS, f"Snapshot completed: {snapshot_id}")

            # Get original AMI details
            log_message(LogLevel.INFO, "Getting original AMI details...")
            ami_response = self.ec2.describe_images(ImageIds=[original_ami_id])
            if not ami_response["Images"]:
                error_and_exit(
                    f"Original AMI not found: {original_ami_id}",
                    "Please verify the AMI ID is correct",
                    code=ERR_AWS_AMI_NOT_FOUND,
                )

            original_ami = ami_response["Images"][0]
            root_device_name = original_ami["RootDeviceName"]
            architecture = original_ami["Architecture"]

            # Create block device mappings for new AMI
            block_device_mappings = []
            for bdm in original_ami.get("BlockDeviceMappings", []):
                if "Ebs" in bdm:
                    new_bdm = {
                        "DeviceName": bdm["DeviceName"],
                        "Ebs": {
                            "SnapshotId": snapshots.get(bdm["DeviceName"], bdm["Ebs"].get("SnapshotId")),
                            "VolumeSize": bdm["Ebs"].get("VolumeSize", 8),
                            "DeleteOnTermination": bdm["Ebs"].get("DeleteOnTermination", True),
                            "VolumeType": bdm["Ebs"].get("VolumeType", "gp2"),
                        },
                    }
                    block_device_mappings.append(new_bdm)

            # Create new AMI
            log_message(LogLevel.INFO, "Creating new AMI...")
            timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
            ami_name = f"{name}-with-sanbootable-{timestamp}"
            ami_description = f"{description} - created {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"

            register_response = self.ec2.register_image(
                Name=ami_name,
                Description=ami_description,
                Architecture=architecture,
                RootDeviceName=root_device_name,
                BlockDeviceMappings=block_device_mappings,
                VirtualizationType="hvm",
                EnaSupport=True,
            )

            new_ami_id = register_response["ImageId"]
            log_message(LogLevel.INFO, f"New AMI created: {new_ami_id}")

            # Wait for AMI to be available
            self.waiter.wait_for_ami_available(new_ami_id)
            log_message(LogLevel.SUCCESS, f"New AMI is now available: {new_ami_id}")

            # Tag the new AMI
            self.ec2.create_tags(
                Resources=[new_ami_id],
                Tags=[
                    {"Key": "Name", "Value": f"{name}-with-sanbootable"},
                    {"Key": "CreatedBy", "Value": "vmie-script"},
                    {"Key": "OriginalAMI", "Value": original_ami_id},
                    {"Key": "CreatedDate", "Value": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                    {"Key": "SanbootableInstalled", "Value": "true"},
                ],
            )

            return new_ami_id

        except Exception as e:
            error_and_exit(
                f"Failed to create AMI from instance: {instance_id}",
                Rule(),
                str(e),
                code=ERR_AWS_AMI_CREATE_FAILED,
            )
