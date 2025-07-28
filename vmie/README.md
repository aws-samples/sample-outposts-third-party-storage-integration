# VMIE - VM Import/Export Tool

A comprehensive Python implementation of the VM Import/Export tool for AWS EC2. This tool provides a complete solution for importing VM images to AWS EC2 and exporting AMIs to RAW format, with support for sanbootable installation for sanboot compatibility.

VMIE leverages the [AWS EC2 VM Import/Export service](https://aws.amazon.com/ec2/vm-import/) to convert virtual machine images from your existing virtualization environment to Amazon EC2. The tool handles the complexities of the import/export process while providing a streamlined interface for common operations.

**Important**: Errors during import and export operations may be due to limitations or requirements of the underlying AWS EC2 VM Import/Export service. Please refer to the [VM Import/Export documentation](https://aws.amazon.com/ec2/vm-import/) for supported formats, operating systems, and known limitations.

## Features

- **Multi-format Support**: OVA, VMDK, VHD, VHDX, RAW
- **Multi-source Support**: HTTP/HTTPS URLs, S3 URLs, local files, JSON disk containers
- **Flexible Workflows**: Import-only, export-only, or full pipeline
- **Sanbootable Support**: Optional sanboot compatibility
- **Progress Tracking**: Rich progress bars and status updates
- **Comprehensive Logging**: Multiple log levels with file output
- **Type Safety**: Full type hints throughout the codebase
- **Error Handling**: Robust error handling with structured error codes
- **AWS Integration**: Native AWS SDK integration with waiters

## Prerequisites

### AWS Requirements

- AWS CLI configured with appropriate permissions
- Required Python packages (see requirements.txt)
- Appropriate IAM permissions for EC2, IAM, S3, and Systems Manager

### Sanbootable Installation Requirements

**For the `--install-sanbootable` option, your AWS account must have:**

- **Default VPC**: A default VPC must be configured in your AWS account and region
- **Default Subnets**: Default subnets must be available in the default VPC
- **Internet Access**: The default subnets must have internet access for package installation

If your account doesn't have a default VPC, you can create one by following the [AWS documentation on working with default VPCs](https://docs.aws.amazon.com/vpc/latest/userguide/work-with-default-vpc.html).

**Note**: The sanbootable installation feature launches a temporary EC2 instance in your default VPC to install the sanboot software. This instance is automatically terminated after the process completes.

### Python Requirements

- Python 3.8 or higher
- Required Python packages (install via `pip install -r requirements.txt`)

## Installation

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Module Organization

### 🔧 Core (`vmie.core`)
Contains the main business logic and orchestration:
- **VMIECore**: Main orchestrator class that coordinates all operations
- **SourceProcessor**: Handles downloading and processing images from various sources with progress tracking
- **SanbootableInstaller**: Manages sanbootable installation on EC2 instances

### ☁️ AWS (`vmie.aws`)
AWS-specific functionality with comprehensive error handling:
- **AWSClient**: Comprehensive AWS service wrapper with credential validation
- **AWSWaiter**: Progress-aware waiting functions for AWS operations

### 🖥️ CLI (`vmie.cli`)
Modern command-line interface built with Typer:
- **__main__.py**: CLI with subcommands (import, export, convert) and rich help text

### 🔄 Common (`vmie.common`)
Shared utilities and components:
- **constants.py**: Configuration constants, AWS policies, and supported formats
- **enums.py**: Operation modes, log levels, image formats, and source types
- **error_codes.py**: Error code definitions for consistent error handling

### 🛠️ Utils (`vmie.utils`)
Specialized utility modules organized by functionality:
- **decompression_utils.py**: File decompression for XZ, GZ, and BZ2 formats
- **display_utils.py**: Progress bars, panels, and console output formatting
- **file_utils.py**: File operations, format detection, and temporary directory management
- **logging_utils.py**: Logging configuration with multiple levels and file output
- **source_utils.py**: Image source processing (S3, URL, local file handling)
- **validation_utils.py**: Input validation for AMI IDs, URLs, and file paths

### 📜 Scripts (`vmie.scripts`)
- Shell scripts for system-level operations
- Installation utilities for sanbootable support

## Usage

### Important Notes

- **S3 URL Sources**: When using S3 URLs as image sources (e.g., `s3://bucket/path/image.ova`), the S3 object must be located in the same bucket specified by the `--s3-bucket` argument. Cross-bucket references are not supported.

- **JSON Source Requirements**: When using a JSON file as the source (for multi-disk imports), **all disk images referenced in the JSON file must be pre-uploaded to the S3 bucket specified by the `--s3-bucket` argument**. The JSON file format should contain an array of disk containers:

```json
[
    {
        "Description": "Boot disk",
        "Format": "vhd",
        "UserBucket": {
            "S3Bucket": "your-bucket-name",
            "S3Key": "path/to/boot.vhd"
        }
    },
    {
        "Description": "Data disk",
        "Format": "vhd",
        "UserBucket": {
            "S3Bucket": "your-bucket-name",
            "S3Key": "path/to/data.vhd"
        }
    }
]
```

**Important**: The `S3Bucket` values in the JSON file should match the bucket name provided via the `--s3-bucket` argument, and all referenced objects must already exist in that bucket before running the import command.

- **SSM Agent Installation**: When using the `--install-sanbootable` option, the SSM agent will be automatically installed on the AMI if it is not already present. This ensures that the sanbootable installation process has the necessary SSM connectivity to execute commands on the EC2 instance. If SSM is already installed, it will not be reinstalled.

- **Sanbootable Linux Support**: The `--install-sanbootable` option is currently supported only on Linux AMIs. Windows AMIs are not supported for sanbootable installation at this time. The tool will automatically detect the AMI platform and prevent sanbootable installation on Windows AMIs.

- **Export Prefix**: The `--s3-export-prefix` option allows you to specify a custom S3 prefix for the exported image. If not specified, a default prefix with a timestamp will be used (e.g., `exports/vmie-export-20250718-220000/`). The prefix should end with a forward slash (`/`), but the tool will add one if it's missing.

- **License Type and Usage Operation**: The `--license-type` and `--usage-operation` parameters are mutually exclusive. You can specify only one of these options per import operation, as documented in the [AWS VM Import/Export licensing documentation](https://docs.aws.amazon.com/vm-import/latest/userguide/licensing-specify-option.html).

### Command Line Interface

The tool provides three main subcommands for different workflows:

#### Import Command
Import a VM image to AWS EC2 as an AMI:

```bash
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source https://example.com/image.ova
```

#### Export Command
Export an existing AMI to RAW format:

```bash
python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0
```

#### Convert Command
Full workflow: Import VM image and export to RAW format:

```bash
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source https://example.com/image.ova
```

### Command Options

#### Common Options (All Commands)
| Option                  | Short  | Description                                               | Required        | Default             |
|-------------------------|--------|-----------------------------------------------------------|-----------------|---------------------|
| `--region`              | `-r`   | AWS region (e.g., us-west-2)                              | Yes             |                     |
| `--s3-bucket`           | `-b`   | S3 bucket name for operations                             | Yes             |                     |
| `--install-sanbootable` |        | Install sanbootable for sanboot support (Linux AMIs only) | No              | False               |
| `--instance-profile`    |        | IAM instance profile name                                 | No              | VMIEInstanceProfile |

#### Import-Specific Options
| Option             | Short | Description                                                                                                                                                                                                                                                                                         | Required  |
|--------------------|-------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|
| `--source`         | `-s`  | VM image source: URL (http/https), S3 URL (s3://), local file path, or JSON file with disk containers. **Note**: S3 URLs must reference objects in the same bucket specified by the `--s3-bucket` argument. For JSON files, all referenced disk images must be pre-uploaded to the specified bucket | Yes       |
| `--license-type`   |       | License type to be used for the AMI (AWS or BYOL)                                                                                                                                                                                                                                                  | No        |
| `--usage-operation`|       | Usage operation value for the AMI                                                                                                                                                                                                                                                                  | No        |

#### Export-Specific Options
| Option               | Short  | Description                                              | Required |
|----------------------|--------|----------------------------------------------------------|----------|
| `--ami-id`           | `-a`   | AMI ID to export                                         | Yes      |
| `--s3-export-prefix` |        | S3 prefix for exported image (e.g., 'exports/my-image/') | No       |

#### Convert-Specific Options
| Option               | Short  | Description                                                                                                                                                                                                                                                                                         | Required |
|----------------------|--------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------|
| `--source`           | `-s`   | VM image source: URL (http/https), S3 URL (s3://), local file path, or JSON file with disk containers. **Note**: S3 URLs must reference objects in the same bucket specified by the `--s3-bucket` argument. For JSON files, all referenced disk images must be pre-uploaded to the specified bucket | Yes      |
| `--s3-export-prefix` |        | S3 prefix for exported image (e.g., 'exports/my-image/')                                                                                                                                                                                                                                            | No       |
| `--license-type`     |        | License type to be used for the AMI (AWS or BYOL)                                                                                                                                                                                                                                                  | No       |
| `--usage-operation`  |        | Usage operation value for the AMI                                                                                                                                                                                                                                                                  | No       |

### Examples

#### Import Examples

```bash
# Import from HTTP URL
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source https://example.com/image.ova

# Import from S3 URL (must be in the same bucket as specified by --s3-bucket)
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source s3://my-bucket/image.vmdk

# Import from local file
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source /path/to/image.ova

# Import with sanbootable installation
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source https://example.com/image.ova --install-sanbootable

# Import with BYOL license type
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source ./image.ova --license-type BYOL

# Import with custom usage operation
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source ./image.ova --usage-operation RunInstances:0010

# Import with custom instance profile
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source ./image.ova --instance-profile MyCustomProfile

# Import from JSON file with multiple disk containers
python -m vmie import --region us-west-2 --s3-bucket my-bucket --source disk-containers.json
```

#### Export Examples

```bash
# Export AMI to RAW format
python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0

# Export with sanbootable installation
python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0 --install-sanbootable

# Export with custom instance profile
python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0 --instance-profile MyCustomProfile

# Export with custom S3 prefix
python -m vmie export --region us-west-2 --s3-bucket my-bucket --ami-id ami-0123456789abcdef0 --s3-export-prefix exports/custom-prefix/
```

#### Convert Examples

```bash
# Full conversion from HTTP URL
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source https://example.com/image.ova

# Full workflow with sanbootable installation from S3 (must be in the same bucket)
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source s3://my-bucket/image.vmdk --install-sanbootable

# Convert from local file with BYOL license
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source ./image.ova --license-type BYOL

# Convert with custom usage operation
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source ./image.ova --usage-operation RunInstances:0010

# Convert with custom instance profile
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source /home/user/vm-images/image.ova --instance-profile MyProfile

# Convert from JSON file with multiple disk containers
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source disk-containers.json

# Convert with custom S3 export prefix and license type
python -m vmie convert --region us-west-2 --s3-bucket my-bucket --source ./image.ova --s3-export-prefix exports/custom-prefix/ --license-type BYOL
```

### Help and Documentation

Get help for any command:

```bash
# General help
python -m vmie --help

# Command-specific help
python -m vmie import --help
python -m vmie export --help
python -m vmie convert --help
```

## Python API

You can also use VMIE programmatically:

```python
from vmie import VMIECore, OperationMode

# Initialize VMIE
vmie = VMIECore(
    region="us-west-2",
    bucket_name="my-bucket",
    operation_mode=OperationMode.FULL,
    install_sanbootable=True
)

# Execute operation
results = vmie.execute("https://example.com/image.ova")
```

### Core Classes

#### VMIECore
Main orchestrator class that coordinates all operations.

```python
from vmie.core import VMIECore
from vmie.common import OperationMode

vmie = VMIECore(
    region="us-west-2",
    bucket_name="my-bucket",
    operation_mode=OperationMode.FULL,
    instance_type="t3.micro",
    instance_profile="VMIEInstanceProfile",
    install_sanbootable=True
)
```

#### AWSClient
AWS service wrapper with comprehensive error handling.

```python
from vmie.aws import AWSClient

client = AWSClient("us-west-2")
client.validate_credentials()
client.create_s3_bucket("my-bucket")
```

#### SourceProcessor
Handles downloading and processing images from various sources.

```python
from vmie.core import SourceProcessor
from pathlib import Path

processor = SourceProcessor()
image_path = processor.download_from_url(
    "https://example.com/image.ova",
    Path("/tmp")
)
```

#### SanbootableInstaller
Manages sanbootable installation on EC2 instances.

```python
from vmie.core import SanbootableInstaller

installer = SanbootableInstaller(aws_client)
new_ami_id = installer.install_sanbootable(
    "ami-12345678",
    "t3.micro",
    "VMIEInstanceProfile"
)
```

### Utility Functions

The utils package provides specialized functionality organized by purpose:

#### File Operations
```python
from vmie.utils import (
    detect_image_format,
    get_file_size,
    format_bytes,
    create_temp_directory,
    cleanup_temp_directory
)

# Detect image format
format = detect_image_format("image.ova")

# Get file size with formatting
size = get_file_size(Path("image.ova"))
formatted_size = format_bytes(size)

# Temporary directory management
temp_dir = create_temp_directory()
# ... use temp_dir ...
cleanup_temp_directory(temp_dir)
```

#### Decompression
```python
from vmie.utils import (
    decompress_file,
    is_compressed_file,
    get_decompressed_path
)

# Check if file needs decompression
if is_compressed_file("image.ova.xz"):
    # Get target path for decompressed file
    target_path = get_decompressed_path(
        Path("image.ova.xz"), 
        Path("/tmp")
    )
    # Decompress the file
    decompress_file(
        Path("image.ova.xz"), 
        target_path
    )
```

#### Source Processing
```python
from vmie.utils import (
    get_image_source_type,
    get_s3_info_from_url,
    validate_image_source
)

# Determine source type
source_type = get_image_source_type("s3://bucket/image.ova")

# Extract S3 information
bucket, key = get_s3_info_from_url("s3://bucket/path/image.ova")

# Validate image source
validate_image_source("https://example.com/image.ova")
```

#### Validation
```python
from vmie.utils import (
    validate_ami_id,
    validate_url,
    validate_local_file,
    validate_s3_url
)

# Validate different input types
validate_ami_id("ami-0123456789abcdef0")
validate_url("https://example.com/image.ova")
validate_local_file("/path/to/image.ova")
validate_s3_url("s3://bucket/image.ova")
```

#### Logging

```python
from vmie.utils import log_message
from vmie.common import LogLevel

# Log messages with different levels
log_message(LogLevel.INFO, "Operation started")
log_message(LogLevel.SUCCESS, "Operation completed")
log_message(LogLevel.ERROR, "Operation failed")
```

## Architecture

### Operation Flow

1. **Validation Phase**: Validate inputs, AWS credentials, and permissions
2. **Download Phase**: (Import) Download image from URL or S3
3. **Upload Phase**: (Import) Upload image to S3 for import
4. **IAM Setup Phase**: (Import) Configure vmimport role
5. **Import Phase**: (Import) Convert image to AMI
6. **Sanbootable Phase**: (Optional) Install sanbootable on AMI
7. **Export Phase**: (Export) Export AMI to RAW format
8. **Cleanup Phase**: Remove temporary resources

### Error Handling

The tool uses structured error codes for consistent error handling:

```python
from vmie.common import (
    ERR_AWS_AMI_NOT_FOUND,      # AWS AMI not found
    ERR_FILE_DOWNLOAD_FAILED,   # File download failed
    ERR_IMPORT_OPERATION_FAILED, # Import operation failed
)
```

Error codes are organized by category:
- General errors: -20000 to -20099
- AWS errors: -20100 to -20199  
- File/Source processing errors: -20200 to -20299
- Sanbootable installation errors: -20300 to -20399

## Configuration

### Environment Variables

- `AWS_DEFAULT_REGION`: Default AWS region
- `AWS_PROFILE`: AWS profile to use
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key

### Constants

Key constants can be found in `vmie/common/constants.py`:

```python
INSTANCE_TYPE = "t3.micro"
DEFAULT_INSTANCE_PROFILE = "VMIEInstanceProfile"
IMPORT_TIMEOUT_MINUTES = 60 * 12
EXPORT_TIMEOUT_MINUTES = 60 * 12
SUPPORTED_FORMATS = {
    "ova": [".ova"],
    "vmdk": [".vmdk"],
    "vhd": [".vhd"],
    "vhdx": [".vhdx"],
    "raw": [".raw", ".img"]
}
COMPRESSED_EXTENSIONS = [".xz", ".gz", ".bz2"]
```

## Logging

The tool provides comprehensive logging with multiple levels:

- **DEBUG**: Detailed debugging information
- **INFO**: General information messages
- **SUCCESS**: Success notifications (green)
- **WARN**: Warning messages (yellow)
- **ERROR**: Error messages (red)

Logs are written to both console (with colors) and file:

```python
from vmie.utils import log_message
from vmie.common import LogLevel

# Log messages with different levels
log_message(LogLevel.INFO, "Operation started")
log_message(LogLevel.SUCCESS, "Operation completed")
log_message(LogLevel.ERROR, "Operation failed")
```

### Log Analysis

Check log files for detailed error information:

```bash
# View latest log
tail -f logs/vmie_*.log

# Search for errors
grep ERROR logs/vmie_*.log
```

## Troubleshooting

### Common Issues

#### VM Import/Export Service Limitations

VMIE uses the [AWS EC2 VM Import/Export service](https://aws.amazon.com/ec2/vm-import/), which has specific requirements and limitations:

- **Supported Formats**: Only certain VM formats are supported (OVA, VMDK, VHD, VHDX, RAW)
- **Operating System Support**: Not all operating systems are supported for import
- **VM Configuration**: VMs must meet specific configuration requirements
- **Size Limits**: There are limits on disk size and VM specifications

**If you encounter import/export errors**, check the [VM Import/Export User Guide](https://docs.aws.amazon.com/vm-import/latest/userguide/) for:
- [Supported operating systems](https://docs.aws.amazon.com/vm-import/latest/userguide/vmie_prereqs.html#supported-os)
- [VM requirements](https://docs.aws.amazon.com/vm-import/latest/userguide/vmie_prereqs.html#vm-requirements)
- [Known limitations](https://docs.aws.amazon.com/vm-import/latest/userguide/vmie_prereqs.html#limitations)

#### Sanbootable Installation Issues

If `--install-sanbootable` fails:

1. **Check Default VPC**: Ensure your account has a default VPC
   ```bash
   aws ec2 describe-vpcs --filters "Name=isDefault,Values=true"
   ```

2. **Check Default Subnets**: Verify default subnets exist
   ```bash
   aws ec2 describe-subnets --filters "Name=defaultForAz,Values=true"
   ```

3. **Create Default VPC and Subnets** (if missing): https://docs.aws.amazon.com/vpc/latest/userguide/work-with-default-vpc.html


### Error Codes

VMIE provides structured error codes for common issues:

- **ERR_INVALID_SOURCE**: Invalid source format or location
- **ERR_SANBOOTABLE_WINDOWS_NOT_SUPPORTED**: Sanbootable not supported on Windows
- **ERR_SANBOOTABLE_SSM_AGENT_FAILED**: SSM agent connection failed
- **ERR_SANBOOTABLE_INSTALL_FAILED**: Sanbootable installation failed

Check the log files for detailed error messages and stack traces.

## Disclaimer

This tool is provided as a sample and is not officially supported by AWS. It is intended for demonstration and educational purposes only. AWS is not responsible for issues that may occur when using this tool in a production environment.
