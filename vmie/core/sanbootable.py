"""Sanbootable installation for VM Import/Export operations."""

import time
from pathlib import Path

from rich.rule import Rule

from vmie.common import (
    ERR_SANBOOTABLE_AMI_CREATE_FAILED,
    ERR_SANBOOTABLE_INSTALL_FAILED,
    ERR_SANBOOTABLE_SCRIPT_INSTALL_FAILED,
    ERR_SANBOOTABLE_SCRIPT_NOT_FOUND,
    ERR_SANBOOTABLE_WINDOWS_NOT_SUPPORTED,
    LogLevel,
)
from vmie.utils import error_and_exit, log_message, log_step


class SanbootableInstaller:
    """Handles sanbootable installation on EC2 instances."""

    def __init__(self, aws_client):
        """Initialize sanbootable installer."""
        self.aws_client = aws_client

    def install_sanbootable(self, ami_id: str, instance_type: str, instance_profile: str) -> str:
        """Install sanbootable on AMI and return new AMI ID."""
        instance_id = None

        try:
            # Validate AMI platform - sanbootable is only supported on Linux
            log_step(1, 5, f"Validating AMI platform compatibility: {ami_id}")

            if self.aws_client.is_windows_ami(ami_id):
                error_and_exit(
                    "Sanbootable installation is not supported on Windows AMIs",
                    f"AMI {ami_id} is a Windows AMI",
                    "Sanbootable installation is currently supported only on Linux AMIs",
                    "Please use a Linux AMI or remove the --install-sanbootable option",
                    code=ERR_SANBOOTABLE_WINDOWS_NOT_SUPPORTED,
                )

            log_message(LogLevel.SUCCESS, "AMI platform validated: Linux")

            # Launch instance
            log_step(2, 5, "Launching EC2 instance")
            instance_id = self.aws_client.launch_instance(ami_id, instance_type, instance_profile)

            # Wait for instance to be running
            log_step(3, 5, "Waiting for instance to be running")
            self.aws_client.waiter.wait_for_instance_running(instance_id)
            log_message(LogLevel.SUCCESS, f"Instance running: {instance_id}")

            # Wait for SSM agent
            log_step(4, 5, "Waiting for SSM agent to be online")
            self.aws_client.waiter.wait_for_ssm_agent(instance_id)
            log_message(LogLevel.SUCCESS, f"SSM agent online for instance: {instance_id}")

            # Install sanbootable using auto-detection script
            log_step(5, 5, "Installing sanbootable")
            self._install_sanbootable_with_script(instance_id)

            # Create new AMI
            new_ami_id = self._create_sanbootable_ami(instance_id, ami_id)

            log_message(LogLevel.SUCCESS, f"Sanbootable AMI created: {new_ami_id}")
            return new_ami_id

        except Exception as e:
            error_and_exit(
                "Failed to install sanbootable",
                Rule(),
                str(e),
                code=ERR_SANBOOTABLE_INSTALL_FAILED,
            )
        finally:
            # Clean up instance
            if instance_id:
                log_message(LogLevel.INFO, f"Terminating instance: {instance_id}")
                self.aws_client.terminate_instance(instance_id)

    def _install_sanbootable_with_script(self, instance_id: str) -> None:
        """Install sanbootable using script."""
        try:
            log_message(LogLevel.INFO, "Executing sanbootable installation script...")

            commands = []
            script_path = Path(__file__).parent.parent / "scripts" / "install_sanbootable.sh"
            if not script_path.exists():
                error_and_exit(
                    f"Installation script not found: {script_path}",
                    "Please ensure the installation script is included in the package",
                    code=ERR_SANBOOTABLE_SCRIPT_NOT_FOUND,
                )
            with open(script_path, "r", encoding="utf-8") as f:
                for line in f:
                    # Strip whitespace from the beginning and end of the line
                    stripped_line = line.strip()

                    # Skip empty lines and comments
                    if stripped_line and not stripped_line.startswith("#"):
                        commands.append(stripped_line)

            # Execute the installation script via SSM
            self.aws_client.execute_ssm_command(instance_id, commands, timeout_seconds=1800)  # 30 minutes
            log_message(LogLevel.SUCCESS, "Sanbootable installation completed successfully")

        except Exception as e:
            error_and_exit(
                f"Failed to install sanbootable with script: {e}", code=ERR_SANBOOTABLE_SCRIPT_INSTALL_FAILED
            )

    def _create_sanbootable_ami(self, instance_id: str, original_ami_id: str) -> str:
        """Create AMI from instance with sanbootable installed."""
        try:
            # Get original AMI details for naming
            ami_details = self.aws_client.get_ami(original_ami_id)
            original_name = ami_details.get("Name", "unknown")

            # Create AMI name and description
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            ami_name = f"{original_name}-sanbootable-{timestamp}"
            description = f"AMI with sanbootable installed - created from {original_ami_id}"

            # Create AMI
            new_ami_id = self.aws_client.create_ami_from_instance(instance_id, ami_name, description, original_ami_id)

            return new_ami_id

        except Exception as e:
            error_and_exit(
                "Failed to create sanbootable AMI",
                Rule(),
                str(e),
                code=ERR_SANBOOTABLE_AMI_CREATE_FAILED,
            )
