"""Core VM Import/Export operations orchestrator."""

import time
from pathlib import Path
from typing import Dict, Optional, cast

from rich.rule import Rule

from vmie import AWSClient
from vmie.common import (
    DEFAULT_INSTANCE_PROFILE,
    ERR_GENERAL_OPERATION_FAILED,
    INSTANCE_TYPE,
    ImageSourceType,
    LogLevel,
    OperationMode,
)
from vmie.core import SanbootableInstaller, SourceProcessor
from vmie.utils import (
    cleanup_temp_directory,
    create_temp_directory,
    detect_image_format,
    display_summary,
    error_and_exit,
    format_bytes,
    get_file_size,
    get_image_source_type,
    get_s3_info_from_url,
    load_disk_containers_from_json,
    log_message,
    log_section,
)


class VMIECore:
    """Core VMIE operations orchestrator."""

    def __init__(
        self,
        region: str,
        bucket_name: str,
        image_source: Optional[str] = None,
        ami_id: Optional[str] = None,
        operation_mode: OperationMode = OperationMode.FULL,
        instance_profile: str = DEFAULT_INSTANCE_PROFILE,
        install_sanbootable: bool = False,
        export_prefix: Optional[str] = None,
        license_type: Optional[str] = None,
        usage_operation: Optional[str] = None,
    ):
        """Initialize VMIE core."""
        self.region = region
        self.bucket_name = bucket_name
        self.image_source = image_source
        self.ami_id = ami_id
        self.operation_mode = operation_mode
        self.instance_type = INSTANCE_TYPE
        self.instance_profile = instance_profile
        self.install_sanbootable = install_sanbootable
        self.export_prefix = export_prefix
        self.license_type = license_type
        self.usage_operation = usage_operation

        # Initialize components
        self.aws_client = AWSClient(region)
        self.source_processor = SourceProcessor()
        self.sanbootable_installer = SanbootableInstaller(
            self.aws_client,
        )

        # Working directory
        self.temp_dir = create_temp_directory()

        # Results tracking
        self.results: Dict[str, str] = {}

    def execute(self) -> Dict[str, str]:
        """Execute VMIE operation based on mode."""
        try:
            log_message(
                LogLevel.INFO,
                "Starting VM Import/Export operation",
            )

            # Create S3 bucket if it does not exist
            self.aws_client.create_s3_bucket(self.bucket_name)

            # Execute based on operation mode
            if self.operation_mode == OperationMode.IMPORT_ONLY:
                return self._execute_import_only()
            elif self.operation_mode == OperationMode.EXPORT_ONLY:
                return self._execute_export_only()
            else:  # FULL
                return self._execute_full_workflow()

        except Exception as e:
            log_message(
                LogLevel.ERROR,
                f"VM Import/Export operation failed: {e}",
            )
            error_and_exit(
                "VM Import/Export operation failed",
                Rule(),
                str(e),
                code=ERR_GENERAL_OPERATION_FAILED,
            )
        finally:
            # Cleanup
            cleanup_temp_directory(self.temp_dir)

    def _execute_import_only(self) -> Dict[str, str]:
        """Execute import-only workflow."""
        log_section("Import-Only Workflow", section_level=1)

        image_source = cast(str, self.image_source)

        # Import the image
        ami_id = self._import_image_from_source(image_source)

        results: Dict[str, str] = {
            "operation_mode": self.operation_mode.value,
            "image_source": image_source,
            "imported_ami": ami_id,
        }

        # Install sanbootable if requested
        if self.install_sanbootable:
            ami_id = self._install_sanbootable(ami_id)
            results["sanbootable_ami"] = ami_id

        return results

    def _execute_export_only(self) -> Dict[str, str]:
        """Execute export-only workflow."""
        log_section("Export-Only Workflow", section_level=1)

        ami_id = cast(str, self.ami_id)

        results: Dict[str, str] = {"operation_mode": self.operation_mode.value, "source_ami": ami_id}

        final_ami_id = ami_id
        # Install sanbootable if requested
        if self.install_sanbootable:
            final_ami_id = self._install_sanbootable(ami_id)
            results["sanbootable_ami"] = final_ami_id

        # Export AMI
        export_url = self._export_ami(final_ami_id)
        results["export_url"] = export_url

        return results

    def _execute_full_workflow(self) -> Dict[str, str]:
        """Execute full import-export workflow."""
        log_section("Full Import-Export Workflow", section_level=1)

        image_source = cast(str, self.image_source)

        # Import the image
        ami_id = self._import_image_from_source(image_source)

        results: Dict[str, str] = {
            "operation_mode": self.operation_mode.value,
            "image_source": image_source,
            "imported_ami": ami_id,
        }

        final_ami_id = ami_id
        # Install sanbootable if requested
        if self.install_sanbootable:
            final_ami_id = self._install_sanbootable(ami_id)
            results["sanbootable_ami"] = final_ami_id

        # Export phase
        export_url = self._export_ami(final_ami_id)
        results["export_url"] = export_url

        return results

    def _import_image_from_source(self, image_source: str) -> str:
        """Import image from various source types (S3, URL, local file, or JSON)."""
        # Setup VM import
        self._setup_vm_import()

        # Handle different source types
        source_type = get_image_source_type(image_source)

        if source_type == ImageSourceType.JSON:
            # JSON source - load disk containers and import directly
            filename = Path(image_source).resolve().name
            ami_id = self._import_image(image_source, filename)
        elif source_type == ImageSourceType.S3:
            # S3 source - validate bucket and import directly
            s3_key, filename = get_s3_info_from_url(image_source)
            ami_id = self._import_image(image_source, filename)
        elif source_type == ImageSourceType.URL:
            # URL source - download, optionally decompress, then upload
            image_path = self._download_from_url(image_source)
            s3_url = self._upload_to_s3(image_path)
            ami_id = self._import_image(s3_url, image_path.name)
        else:  # ImageSourceType.LOCAL
            # Local source - optionally decompress, then upload
            image_path = self._process_local_file(image_source)
            s3_url = self._upload_to_s3(image_path)
            ami_id = self._import_image(s3_url, image_path.name)

        return ami_id

    def _download_from_url(self, url: str) -> Path:
        """Download image from HTTP/HTTPS URL."""
        log_section("URL Download Phase", section_level=2)
        return self.source_processor.download_from_url(url, self.temp_dir)

    def _process_local_file(self, local_path: str) -> Path:
        """Process local file - optionally decompress if needed."""
        log_section("Local File Processing Phase", section_level=2)
        return self.source_processor.process_local_file(local_path, self.temp_dir)

    def _upload_to_s3(self, image_path: Path) -> str:
        """Upload image to S3."""
        log_section("S3 Upload Phase", section_level=2)

        file_size = get_file_size(image_path)
        log_message(
            LogLevel.INFO,
            f"Uploading file: {image_path} (size: {format_bytes(file_size)})",
        )

        s3_key = image_path.name
        s3_url = self.aws_client.upload_to_s3(str(image_path), self.bucket_name, s3_key)

        return s3_url

    def _setup_vm_import(self) -> None:
        """Setup VM import IAM role."""
        log_section("IAM Setup Phase", section_level=2)
        self.aws_client.setup_vmimport_role(self.bucket_name)

    def _import_image(self, image_source: str, filename: str) -> str:
        """Import VM image to AMI."""
        log_section("Image Import Phase", section_level=2)

        image_source_type = get_image_source_type(image_source)

        # Create description
        base_name = Path(filename).stem
        description = f"{base_name} imported via vmie script"

        if image_source_type == ImageSourceType.JSON:
            containers = load_disk_containers_from_json(image_source)
            ami_id = self.aws_client.import_image_from_disk_containers(
                containers, description, self.license_type, self.usage_operation
            )
        else:
            image_format = detect_image_format(filename)
            ami_id = self.aws_client.import_image(
                image_source, description, image_format.value, self.license_type, self.usage_operation
            )

        log_message(
            LogLevel.SUCCESS,
            f"Image imported successfully: {ami_id}",
        )
        return ami_id

    def _install_sanbootable(self, ami_id: str) -> str:
        """Install sanbootable on AMI."""
        log_section("Sanbootable Installation Phase", section_level=2)

        # Setup instance profile
        self.aws_client.create_instance_profile(self.instance_profile)

        # Install sanbootable
        new_ami_id = self.sanbootable_installer.install_sanbootable(ami_id, self.instance_type, self.instance_profile)

        return new_ami_id

    def _export_ami(self, ami_id: str) -> str:
        """Export AMI to RAW format."""
        log_section("AMI Export Phase", section_level=2)

        # Use provided export prefix or create one with timestamp
        export_prefix = self.export_prefix
        if not export_prefix:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            export_prefix = f"exports/vmie-export-{timestamp}/"

        # Ensure export prefix ends with a trailing slash
        if not export_prefix.endswith("/"):
            export_prefix += "/"

        # Create description
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        description = f"VMIE AMI export - {timestamp}"

        # Start export
        export_url = self.aws_client.export_image(ami_id, self.bucket_name, export_prefix, description)

        log_message(
            LogLevel.SUCCESS,
            f"AMI exported successfully: {export_url}",
        )
        return export_url

    def display_results(self, results: Dict[str, str]) -> None:
        """Display operation results."""
        log_section("Operation Summary", section_level=1)
        log_message(
            LogLevel.SUCCESS,
            "Operation completed successfully!",
        )

        # Prepare summary items
        summary_items = {"Operation Mode": results.get("operation_mode", "unknown")}

        if "image_source" in results:
            summary_items["Image Source"] = results["image_source"]

        if "source_ami" in results:
            summary_items["Source AMI"] = results["source_ami"]

        if "imported_ami" in results:
            summary_items["Imported AMI"] = results["imported_ami"]

        if "sanbootable_ami" in results:
            summary_items["Sanbootable AMI"] = results["sanbootable_ami"]

        if "export_url" in results:
            summary_items["Exported Image"] = results["export_url"]

        # Log individual items
        for key, value in summary_items.items():
            log_message(
                LogLevel.INFO,
                f"{key}: {value}",
            )

        # Display summary
        display_summary("VMIE Operation Results", summary_items)
