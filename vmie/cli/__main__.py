#!/usr/bin/python3
"""VM Import/Export Tool for AWS EC2."""

from typing import Optional

import typer
from rich.console import Console
from rich.rule import Rule
from typing_extensions import Annotated

from vmie.common import (
    DEFAULT_INSTANCE_PROFILE,
    ERR_CONVERT_OPERATION_FAILED,
    ERR_EXPORT_OPERATION_FAILED,
    ERR_IMPORT_OPERATION_FAILED,
    OperationMode,
)
from vmie.core import VMIECore
from vmie.utils import error_and_exit, validate_ami_id, validate_image_source

console = Console()
app = typer.Typer(name="vmie", help="VM Import/Export Tool for AWS EC2", add_completion=False)


@app.command("import")
def import_image(
    region: Annotated[str, typer.Option("--region", "-r", help="AWS region (e.g., us-west-2)")],
    bucket: Annotated[str, typer.Option("--s3-bucket", "-b", help="S3 bucket name for import operation")],
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="VM image source: URL (http/https), S3 URL (s3://), local file path, or JSON file with disk containers",
            callback=validate_image_source,
        ),
    ],
    install_sanbootable: Annotated[bool, typer.Option(help="Install sanbootable for sanboot support")] = False,
    instance_profile: Annotated[
        str, typer.Option(help="IAM instance profile name for SSM access")
    ] = DEFAULT_INSTANCE_PROFILE,
) -> None:
    """
    Import a VM image to AWS EC2 as an AMI.

    This command imports a VM image from various sources and converts it to an AWS EC2 AMI.
    The image can be in OVA, VMDK, VHD, VHDX, or RAW format. Optionally install sanbootable
    for sanboot support.

    The source can be:
    - HTTP/HTTPS URL: https://example.com/image.ova
    - S3 URL: s3://bucket/path/image.vmdk
    - Local file path: /path/to/image.ova or ./image.ova
    - JSON file: disk-containers.json (contains array of disk containers for multi-disk imports)

    Examples:

    \b
    # Import from HTTP URL
    python -m vmie import --region us-west-2 --s3-bucket my-bucket --source https://example.com/image.ova

    \b
    # Import from S3 URL with sanbootable
    python -m vmie import --region us-west-2 --s3-bucket my-bucket --source s3://my-bucket/image.vmdk --install-sanbootable

    \b
    # Import from local file
    python -m vmie import --region us-west-2 --s3-bucket my-bucket --source /path/to/image.ova --install-sanbootable

    \b
    # Import from JSON file with multiple disk containers
    python -m vmie import --region us-west-2 --s3-bucket my-bucket --source disk-containers.json
    """
    try:
        vmie = VMIECore(
            region=region,
            bucket_name=bucket,
            image_source=source,
            operation_mode=OperationMode.IMPORT_ONLY,
            instance_profile=instance_profile,
            install_sanbootable=install_sanbootable,
        )

        results = vmie.execute()
        vmie.display_results(results)

    except Exception as e:
        error_and_exit(
            "Import operation failed",
            Rule(),
            str(e),
            code=ERR_IMPORT_OPERATION_FAILED,
        )


@app.command("export")
def export_ami(
    region: Annotated[str, typer.Option("--region", "-r", help="AWS region (e.g., us-west-2)")],
    bucket: Annotated[str, typer.Option("--s3-bucket", "-b", help="S3 bucket name for export operation")],
    ami_id: Annotated[
        str,
        typer.Option("--ami-id", "-a", help="AMI ID to export (e.g., ami-0123456789abcdef0)", callback=validate_ami_id),
    ],
    export_prefix: Annotated[
        Optional[str],
        typer.Option("--s3-export-prefix", help="S3 prefix for exported image (e.g., 'exports/my-image/')"),
    ] = None,
    install_sanbootable: Annotated[bool, typer.Option(help="Install sanbootable for sanboot support")] = False,
    instance_profile: Annotated[
        str, typer.Option(help="IAM instance profile name for SSM access")
    ] = DEFAULT_INSTANCE_PROFILE,
) -> None:
    """
    Export an existing AMI to RAW format in S3.

    This command exports an existing AMI to RAW format and stores it in the specified S3 bucket.
    Optionally install sanbootable for sanboot support before export.

    Examples:

    \b
    # Export AMI to RAW format
    python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0

    \b
    # Export with sanbootable installation
    python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0 --install-sanbootable

    \b
    # Export with custom S3 prefix
    python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0 --s3-export-prefix exports/custom-prefix/
    """
    try:
        vmie = VMIECore(
            region=region,
            bucket_name=bucket,
            ami_id=ami_id,
            operation_mode=OperationMode.EXPORT_ONLY,
            instance_profile=instance_profile,
            install_sanbootable=install_sanbootable,
            export_prefix=export_prefix,
        )

        results = vmie.execute()
        vmie.display_results(results)

    except Exception as e:
        error_and_exit(
            "Export operation failed",
            Rule(),
            str(e),
            code=ERR_EXPORT_OPERATION_FAILED,
        )


@app.command("convert")
def convert(
    region: Annotated[str, typer.Option("--region", "-r", help="AWS region (e.g., us-west-2)")],
    bucket: Annotated[str, typer.Option("--s3-bucket", "-b", help="S3 bucket name for operations")],
    source: Annotated[
        str,
        typer.Option(
            "--source",
            "-s",
            help="VM image source: URL (http/https), S3 URL (s3://), local file path, or JSON file with disk containers",
            callback=validate_image_source,
        ),
    ],
    export_prefix: Annotated[
        Optional[str],
        typer.Option("--s3-export-prefix", help="S3 prefix for exported image (e.g., 'exports/my-image/')"),
    ] = None,
    install_sanbootable: Annotated[bool, typer.Option(help="Install sanbootable for sanboot support")] = False,
    instance_profile: Annotated[
        str, typer.Option(help="IAM instance profile name for SSM access")
    ] = DEFAULT_INSTANCE_PROFILE,
) -> None:
    """
    Full workflow: Import VM image and export to RAW format.

    This command performs the complete workflow: imports a VM image from various sources,
    optionally installs sanbootable for sanboot support, and exports the result to RAW format.

    The source can be:
    - HTTP/HTTPS URL: https://example.com/image.ova
    - S3 URL: s3://bucket/path/image.vmdk
    - Local file path: /path/to/image.ova or ./image.ova
    - JSON file: disk-containers.json (contains array of disk containers for multi-disk imports)

    Examples:

    \b
    # Full conversion from HTTP URL
    python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source https://example.com/image.ova

    \b
    # Full workflow with sanbootable installation from S3
    python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source s3://my-bucket/image.vmdk --install-sanbootable

    \b
    # Convert from local file
    python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source ./image.ova --install-sanbootable

    \b
    # Convert from JSON file with multiple disk containers
    python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source disk-containers.json

    \b
    # Convert with custom S3 export prefix
    python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source ./image.ova --s3-export-prefix exports/custom-prefix/
    """
    try:
        vmie = VMIECore(
            region=region,
            bucket_name=bucket,
            image_source=source,
            operation_mode=OperationMode.FULL,
            instance_profile=instance_profile,
            install_sanbootable=install_sanbootable,
            export_prefix=export_prefix,
        )

        results = vmie.execute()
        vmie.display_results(results)

    except Exception as e:
        error_and_exit(
            "Convert operation failed",
            Rule(),
            str(e),
            code=ERR_CONVERT_OPERATION_FAILED,
        )


if __name__ == "__main__":
    app()
