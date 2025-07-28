"""AWS waiter functions for VM Import/Export operations."""

import time
from typing import Dict

from rich.rule import Rule

from vmie.common import (
    ERR_AWS_AMI_NOT_FOUND,
    ERR_AWS_AMI_STATUS_CHECK_FAILED,
    ERR_AWS_AMI_TIMEOUT,
    ERR_AWS_INSTANCE_STATUS_CHECK_FAILED,
    ERR_AWS_INSTANCE_TIMEOUT,
    ERR_AWS_SNAPSHOT_FAILED,
    ERR_AWS_SNAPSHOT_NOT_FOUND,
    ERR_AWS_SNAPSHOT_STATUS_CHECK_FAILED,
    ERR_AWS_SNAPSHOT_TIMEOUT,
    ERR_AWS_SSM_STATUS_CHECK_FAILED,
    ERR_AWS_SSM_TIMEOUT,
    ERR_AWS_TASK_RESULT_FAILED,
    ERR_AWS_TASK_STATUS_CHECK_FAILED,
    ERR_AWS_TASK_TIMEOUT,
    ERR_GENERAL_OPERATION_FAILED,
    LogLevel,
)
from vmie.utils import error_and_exit, log_message, wait_with_progress


class AWSWaiter:
    """AWS waiter functions for various operations."""

    def __init__(self, ec2_client, ssm_client, iam_client=None):
        """Initialize AWS waiter with clients."""
        self.ec2 = ec2_client
        self.ssm = ssm_client
        self.iam = iam_client

    def _wait_for_task(self, task_id: str, operation_type: str, timeout_minutes: int) -> str:
        """
        Generic wait function for both import and export tasks.

        Args:
            task_id: The ID of the task to wait for
            operation_type: Either 'import' or 'export'


        Returns:
            str: AMI ID for imports, S3 URL for exports
        """
        # Define operation-specific parameters
        if operation_type == "import":
            describe_method = self.ec2.describe_import_image_tasks
            task_id_param = {"ImportTaskIds": [task_id]}
            tasks_key = "ImportImageTasks"
            result_key = "ImageId"
        elif operation_type == "export":
            describe_method = self.ec2.describe_export_image_tasks
            task_id_param = {"ExportImageTaskIds": [task_id]}
            tasks_key = "ExportImageTasks"
            result_key = "S3ExportLocation"
        else:
            error_and_exit(
                f"Invalid operation type: {operation_type}",
                "Supported types: import, export",
                code=ERR_GENERAL_OPERATION_FAILED,
            )

        description = f"Waiting for {operation_type} task {task_id}"
        result = None

        def check_task_status() -> Dict:
            nonlocal result
            try:
                response = describe_method(**task_id_param)
                task = response[tasks_key][0]
                status = task["Status"]

                if status == "completed":
                    if operation_type == "import":
                        result = task[result_key]
                    else:  # export
                        s3_location = task[result_key]
                        bucket = s3_location["S3Bucket"]
                        prefix = s3_location["S3Prefix"]
                        result = f"s3://{bucket}/{prefix}{task_id}.raw"
                    return {
                        "completed": True,
                        "progress": 100,
                        "description": f"{operation_type.capitalize()} completed",
                    }

                elif status in ["cancelled", "deleted"]:
                    error_and_exit(
                        f"{operation_type.capitalize()} task {status}: {task_id}", code=ERR_AWS_TASK_STATUS_CHECK_FAILED
                    )

                progress_value = task.get("Progress", 0)
                # Handle both string and numeric progress values
                if isinstance(progress_value, str):
                    try:
                        progress_value = int(progress_value) if progress_value != "unknown" else 0
                    except ValueError:
                        progress_value = 0

                progress_desc = f"Waiting for {operation_type} task {task_id} (Status: {status})"

                return {"completed": False, "progress": progress_value, "description": progress_desc}

            except Exception as e:
                error_and_exit(
                    f"Failed to check {operation_type} status",
                    Rule(),
                    str(e),
                    code=ERR_AWS_TASK_STATUS_CHECK_FAILED,
                )

        success = wait_with_progress(
            description=description,
            check_function=check_task_status,
            timeout_seconds=timeout_minutes * 60,
            check_interval=30,
        )

        if not success:
            error_and_exit(
                f"{operation_type.capitalize()} task timed out after {timeout_minutes} minutes",
                code=ERR_AWS_TASK_TIMEOUT,
            )

        if result is None:
            error_and_exit(
                f"Failed to get result from {operation_type} task",
                "Task completed but no result was returned",
                code=ERR_AWS_TASK_RESULT_FAILED,
            )

        return result

    def wait_for_import(self, task_id: str, timeout_minutes: int = 60) -> str:
        """Wait for import task to complete and return AMI ID."""
        return self._wait_for_task(task_id, "import", timeout_minutes)

    def wait_for_export(self, task_id: str, timeout_minutes: int = 90) -> str:
        """Wait for export task to complete and return S3 location."""
        return self._wait_for_task(task_id, "export", timeout_minutes)

    def wait_for_instance_running(self, instance_id: str, timeout_minutes: int = 10) -> None:
        """Wait for instance to be in running state."""
        description = f"Waiting for instance {instance_id} to be running"
        time.sleep(1)

        def check_instance_status() -> Dict:
            try:
                response = self.ec2.describe_instances(InstanceIds=[instance_id])
                instance = response["Reservations"][0]["Instances"][0]
                state = instance["State"]["Name"]

                if state == "running":
                    return {"completed": True, "description": f"Instance {instance_id} is running"}
                elif state in ["terminated", "stopping", "stopped"]:
                    error_and_exit(
                        f"Instance {instance_id} is in {state} state", code=ERR_AWS_INSTANCE_STATUS_CHECK_FAILED
                    )

                progress_desc = f"Instance {instance_id} state: {state}"
                return {"completed": False, "description": progress_desc}

            except Exception as e:
                error_and_exit(
                    "Failed to check instance status",
                    Rule(),
                    str(e),
                    code=ERR_AWS_INSTANCE_STATUS_CHECK_FAILED,
                )

        success = wait_with_progress(
            description=description,
            check_function=check_instance_status,
            timeout_seconds=timeout_minutes * 60,
            check_interval=15,
        )

        if not success:
            error_and_exit(
                f"Instance {instance_id} did not reach running state within {timeout_minutes} minutes",
                code=ERR_AWS_INSTANCE_TIMEOUT,
            )

    def wait_for_ssm_agent(self, instance_id: str, timeout_minutes: int = 10) -> None:
        """Wait for SSM agent to be online."""
        description = f"Waiting for SSM agent on instance {instance_id}"

        def check_ssm_status() -> Dict:
            try:
                response = self.ssm.describe_instance_information(
                    Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
                )

                if response["InstanceInformationList"]:
                    return {
                        "completed": True,
                        "description": f"SSM agent online for instance {instance_id}",
                    }

                progress_desc = f"SSM agent not yet online for instance: {instance_id}"
                return {"completed": False, "description": progress_desc}

            except Exception as e:
                progress_desc = f"SSM agent check failed (retrying): {e}"
                log_message(LogLevel.INFO, progress_desc)
                return {
                    "completed": False,
                    "description": f"SSM agent check failed for instance {instance_id}",
                }

        success = wait_with_progress(
            description=description,
            check_function=check_ssm_status,
            timeout_seconds=timeout_minutes * 60,
            check_interval=15,
        )

        if not success:
            error_and_exit(
                "SSM agent failed to come online within the timeout period",
                "Please check instance connectivity and SSM agent installation",
                code=ERR_AWS_SSM_TIMEOUT,
            )

    def wait_for_ssm_command(self, command_id: str, instance_id: str, timeout_minutes: int = 10) -> None:
        """
        Wait for an SSM command to finish executing.

        Args:
            command_id: The SSM command ID to wait for
            instance_id: The instance ID where the command is running
            timeout_minutes: Maximum time to wait in minutes
        """
        description = f"Waiting for SSM command {command_id} to complete on instance {instance_id}"

        def check_command_status() -> Dict:
            try:
                response = self.ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)

                status = response["Status"]

                if status == "Success":
                    return {
                        "completed": True,
                        "description": f"SSM command {command_id} completed successfully",
                    }
                elif status in ["Failed", "Cancelled", "TimedOut"]:
                    error_msg = response.get("StandardErrorContent", "No error details available")
                    error_and_exit(
                        f"SSM command {command_id} {status.lower()}: {error_msg}", code=ERR_AWS_SSM_STATUS_CHECK_FAILED
                    )
                elif status in ["InProgress", "Pending"]:
                    progress_desc = f"SSM command {command_id} status: {status}"
                    return {"completed": False, "description": progress_desc}
                else:
                    progress_desc = f"SSM command {command_id} status: {status}"
                    return {"completed": False, "description": progress_desc}

            except self.ssm.exceptions.InvocationDoesNotExist:
                progress_desc = f"SSM command {command_id} invocation not yet available"
                return {"completed": False, "description": progress_desc}
            except Exception as e:
                error_and_exit(
                    "Failed to check SSM command status",
                    Rule(),
                    str(e),
                    code=ERR_AWS_SSM_STATUS_CHECK_FAILED,
                )

        success = wait_with_progress(
            description=description,
            check_function=check_command_status,
            timeout_seconds=timeout_minutes * 60,
            check_interval=10,  # Check every 10 seconds
        )

        if not success:
            error_and_exit(
                f"SSM command {command_id} did not complete within {timeout_minutes} minutes",
                code=ERR_AWS_SSM_TIMEOUT,
            )

    def wait_for_ami_available(self, ami_id: str, timeout_minutes: int = 30) -> None:
        """Wait for AMI to be available."""
        description = f"Waiting for AMI {ami_id} to be available"

        def check_ami_status() -> Dict:
            try:
                response = self.ec2.describe_images(ImageIds=[ami_id])
                if not response["Images"]:
                    error_and_exit(
                        f"AMI not found: {ami_id}",
                        "Please verify the AMI ID is correct",
                        code=ERR_AWS_AMI_NOT_FOUND,
                    )

                image = response["Images"][0]
                state = image["State"]

                if state == "available":
                    return {"completed": True, "description": f"AMI {ami_id} is available"}
                elif state in ["failed", "deregistered"]:
                    error_and_exit(
                        f"AMI {ami_id} is in {state} state",
                        "AMI creation may have failed",
                        code=ERR_AWS_AMI_STATUS_CHECK_FAILED,
                    )

                progress_desc = f"AMI {ami_id} state: {state}"

                return {"completed": False, "description": progress_desc}

            except Exception as e:
                error_and_exit(
                    "Failed to check AMI status",
                    Rule(),
                    str(e),
                    code=ERR_AWS_AMI_STATUS_CHECK_FAILED,
                )

        success = wait_with_progress(
            description=description,
            check_function=check_ami_status,
            timeout_seconds=timeout_minutes * 60,
            check_interval=30,
        )

        if not success:
            error_and_exit(
                f"AMI {ami_id} did not become available within {timeout_minutes} minutes",
                code=ERR_AWS_AMI_TIMEOUT,
            )

    def wait_for_snapshot_completed(self, snapshot_id: str, timeout_minutes: int = 30) -> None:
        """Wait for snapshot to be completed."""
        description = f"Waiting for snapshot {snapshot_id} to complete"

        def check_snapshot_status() -> Dict:
            try:
                response = self.ec2.describe_snapshots(SnapshotIds=[snapshot_id])
                if not response["Snapshots"]:
                    error_and_exit(
                        f"Snapshot not found: {snapshot_id}",
                        "Please verify the snapshot ID is correct",
                        code=ERR_AWS_SNAPSHOT_NOT_FOUND,
                    )

                snapshot = response["Snapshots"][0]
                state = snapshot["State"]

                if state == "completed":
                    return {"completed": True, "description": f"Snapshot {snapshot_id} completed"}
                elif state == "error":
                    error_and_exit(
                        f"Snapshot failed: {snapshot_id}",
                        "Snapshot creation encountered an error",
                        code=ERR_AWS_SNAPSHOT_FAILED,
                    )

                progress_desc = f"Snapshot {snapshot_id} (state: {state})"

                return {"completed": False, "description": progress_desc}

            except Exception as e:
                error_and_exit(
                    "Failed to check snapshot status",
                    Rule(),
                    str(e),
                    code=ERR_AWS_SNAPSHOT_STATUS_CHECK_FAILED,
                )

        success = wait_with_progress(
            description=description,
            check_function=check_snapshot_status,
            timeout_seconds=timeout_minutes * 60,
            check_interval=15,
        )

        if not success:
            error_and_exit(
                f"Snapshot {snapshot_id} did not complete within {timeout_minutes} minutes",
                code=ERR_AWS_SNAPSHOT_TIMEOUT,
            )

    def _wait_for_propagation(self, resource_type: str, resource_name: str, wait_seconds: int = 20) -> None:
        """
        Generic wait function for AWS resource propagation.

        Args:
            resource_type: Type of resource (e.g., "instance profile", "role")
            resource_name: Name of the resource
            wait_seconds: Number of seconds to wait
        """
        description = f"Waiting for {resource_type} {resource_name} to be available"
        start_time = time.time()

        def check_ready() -> Dict:
            elapsed = time.time() - start_time
            if elapsed >= wait_seconds:
                return {
                    "completed": True,
                    "progress": 100,
                    "description": f"{resource_type.capitalize()} {resource_name} is available",
                }

            progress_value = int((elapsed / wait_seconds) * 100)
            progress_desc = f"Waiting for {resource_type} {resource_name}"

            return {"completed": False, "progress": progress_value, "description": progress_desc}

        wait_with_progress(
            description=description,
            check_function=check_ready,
            timeout_seconds=wait_seconds + 5,  # Slightly longer timeout to ensure completion
            check_interval=2,
        )

    def wait_for_instance_profile(self, profile_name: str) -> None:
        """
        Wait for an instance profile to be created and available.

        Args:
            profile_name: Name of the instance profile to wait for
        """
        self._wait_for_propagation("instance profile", profile_name, 20)

    def wait_for_role_update(self, role_name: str) -> None:
        """
        Wait for a role to be updated.

        Args:
            role_name: Name of the role to wait for
        """
        self._wait_for_propagation("role", role_name, 20)
