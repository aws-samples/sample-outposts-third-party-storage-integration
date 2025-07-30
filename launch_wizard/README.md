# Launch Wizard for EC2 with External Storage

The Launch Wizard provides a Python-based solution for launching EC2 instances on AWS Outposts that connect to external storage arrays during boot. This implementation demonstrates how to leverage vendor-specific client libraries and AWS SDK to launch EC2 instances with user data templates that configure the necessary settings to attach network storage at boot time.

## Features

- **Multi-vendor Support**: NetApp, Pure Storage, and generic storage providers
- **Multi-protocol Support**: iSCSI and NVMe connectivity options
- **OS Support**: Both Linux and Windows guest operating systems
- **Storage Features**: Data volumes, LocalBoot, and SAN boot configurations
- **Interactive CLI**: Guided experience with validation at each step
- **AWS Integration**: Native AWS SDK integration with proper error handling
- **Type Safety**: Full type hints throughout the codebase

## Prerequisites

### AWS Requirements

- AWS CLI configured with appropriate permissions
- Access to an AWS Outpost with external storage arrays configured
- Appropriate IAM permissions for EC2, IAM, Outposts, and Secrets Manager

### Storage Array Requirements

- NetApp or Pure Storage storage array accessible from your Outpost
- Storage array credentials (stored in AWS Secrets Manager or provided during execution)
- Network connectivity between your Outpost and storage arrays

## IAM Permissions

The Launch Wizard requires specific IAM permissions to function properly. Below is a sample IAM policy that provides the minimum necessary permissions:

**EC2 Permissions**

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "ec2:ModifySubnetAttribute",
            "Resource": "<subnet arn>"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:AllocateAddress",
                "ec2:AssociateAddress",
                "ec2:DescribeCoipPools",
                "ec2:DescribeImages",
                "ec2:DescribeKeyPairs",
                "ec2:DescribeLocalGatewayRouteTables",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeSubnets",
                "ec2:RunInstances"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": ["ec2:CreateNetworkInterface", "ec2:CreateTags"],
            "Resource": ["<subnet arn>", "<security group arn>"]
        }
    ]
}
```

**IAM Permissions**

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "iam:ListInstanceProfiles",
            "Resource": "*"
        }
    ]
}
```

**Outposts Permissions**

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["outposts:GetOutpost", "outposts:GetOutpostInstanceTypes"],
            "Resource": "<outpost arn>"
        }
    ]
}
```

If Secrets Manager is used, you also need the following minimum permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "secretsmanager:ListSecrets",
            "Resource": "*"
        }
    ]
}
```

For production environments, it's recommended to restrict the `Resource` sections to specific resources where applicable, following the principle of least privilege.

### Instance Profile Requirements

If you're using an instance profile with your EC2 instances, ensure it has the necessary permissions for the instance to:

1. Retrieve storage array credentials from Secrets Manager (if applicable)
2. Access any additional AWS services based on your usage scenario (e.g., S3, CloudWatch)

A sample instance profile policy for Secrets Manager might include:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "SecretsManagerPermissions",
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": ["<secret arn 1>", "<secret arn 2>", "..."]
        }
    ]
}
```

## Installation

### Install Dependencies

```bash
pip install -r requirements.txt
```

Notes:

- During the installation process, the `py-pure-client` library needs to be built locally. It may fail if there's insufficient space in `/tmp` on macOS or Linux. In such cases, build the library in a directory with more space: `TMPDIR="directory-path-with-more-available-space" pip install -r requirements.txt`.

## Usage

The Launch Wizard provides a command-line interface with subcommands for each storage vendor:

```bash
# Basic usage pattern
python -m launch_wizard [COMMON OPTIONS (optional)] [VENDOR] [PROTOCOL] [VENDOR-SPECIFIC OPTIONS (optional)]
```

**Command Structure:**

- **Common options** (such as `--region`, `--ami-id`, etc.) go after the main command and before the vendor/protocol
- **Vendor-specific options** (such as `--netapp-management-ip`, `--pure-api-token`, etc.) go after the vendor and protocol subcommands

### Supported Vendors and Protocols

- NetApp: `iscsi`, `nvme`
- Pure Storage: `iscsi`, `nvme`
- Generic: `iscsi`, `nvme`

### Examples

```bash
# Basic examples (interactive mode)
# Launch an EC2 instance with NetApp NVMe storage
python -m launch_wizard netapp nvme

# Launch an EC2 instance with Pure Storage iSCSI storage
python -m launch_wizard purestorage iscsi

# Launch an EC2 instance with generic iSCSI storage
python -m launch_wizard generic iscsi

# Example with common options and vendor-specific options
python -m launch_wizard --region us-west-2 --ami-id ami-12345 netapp nvme --netapp-management-ip 10.0.0.10

# Example with guest OS scripts (for localboot/sanboot features only)
python -m launch_wizard purestorage iscsi --guest-os-script /path/to/config.yml --guest-os-script /path/to/setup.sh
```

### Common Options

The Launch Wizard uses an interactive approach by default. The following common options are placed after the main command (`python -m launch_wizard`) and before the vendor/protocol subcommands. The examples below show some of the commonly used options, but this is not a complete list. If any of these options are not specified as command-line arguments, the tool will present interactive prompts to collect the required information:

- `--region`: AWS Region where the target Outpost is homed
- `--ami-id`: ID of the AMI to launch
- `--subnet-id`: Outpost subnet where the instance will be launched
- `--instance-type`: Instance type to launch
- `--key-name`: Key pair name for SSH access
- `--assume-yes`: Automatically answer yes to all prompts

For a complete list of common options, you can use:

```bash
python -m launch_wizard --help
```

### Guest OS Scripts

The Launch Wizard supports the inclusion of additional guest OS scripts for **LocalBoot** (`localboot`) and **SAN boot** (`sanboot`) features only. These scripts are executed during the instance initialization process and can be used to perform custom configuration tasks.

#### Supported Script Types

- **Shell Scripts** (`.sh`, `.bash` files or files starting with `#!/`): Executed as shell scripts
- **Cloud-Config** (`.yml`, `.yaml` files or files starting with `#cloud-config`): Processed as cloud-init configuration

#### Script Usage

Guest OS scripts are specified as **vendor-specific options** using the `--guest-os-script` option with each vendor subcommand. You can specify one or more script files:

```bash
# Single script with NetApp NVMe
python -m launch_wizard netapp nvme --guest-os-script /path/to/script.sh

# Multiple scripts with Pure Storage iSCSI
python -m launch_wizard purestorage iscsi --guest-os-script /path/to/config.yml --guest-os-script /path/to/setup.sh
```

#### Interactive Mode

When using **LocalBoot** (`localboot`) and **SAN boot** (`sanboot`) features, if no guest OS scripts are specified via command-line options, the tool will interactively prompt you to:

1. Proceed without guest OS scripts, or
2. Provide script file paths interactively

This interactive mode allows you to add multiple script files one at a time and validates that each file exists before proceeding.

#### Important Notes

- Guest OS scripts are **only supported** for `localboot` and `sanboot` features
- Scripts specified for `data_volumes` feature will be ignored with a warning message
- Scripts are executed in the order they are specified
- Ensure scripts have appropriate permissions and are compatible with the target AMI's operating system

#### Example Scripts

**Shell Script Example** (`setup.sh`):

```bash
#!/bin/bash
# Custom instance setup script
echo "Configuring custom settings..."
# Add your custom configuration here
```

**Cloud-Config Example** (`config.yml`):

```yaml
#cloud-config
packages:
    - htop
    - vim
runcmd:
    - echo "Custom configuration complete" >> /var/log/custom-setup.log
```

### Vendor-Specific Options

In addition to the common options above, each vendor subcommand has its own set of options. These vendor-specific options are placed after the vendor and protocol subcommands (e.g., `netapp nvme --netapp-management-ip ...`). These are also interactive by default. The examples below show some of the commonly used options, but this is not a complete list:

#### Common Vendor Options

All vendor subcommands support the following option:

- `--guest-os-script`: Path to additional guest OS script files to execute

#### NetApp Options

- `--netapp-management-ip`: Management IP address of the NetApp storage array
- `--netapp-username`: Username for NetApp storage array authentication
- `--netapp-password`: Password for NetApp storage array authentication

#### Pure Storage Options

- `--pure-management-ip`: Management IP address of the Pure storage array
- `--pure-api-token`: API token for Pure storage array authentication

For a complete list of vendor-specific options, you can:

- Use the `--help` option with the specific vendor and protocol subcommand. For example:
    ```bash
    python -m launch_wizard netapp nvme --help
    python -m launch_wizard purestorage iscsi --help
    python -m launch_wizard generic nvme --help
    ```
- Examine the source code for each vendor module in the respective directories

### Automation

For automation scenarios where interactive prompts are not desired, you must:

1. Specify all required common CLI options in your command
2. Specify all required vendor-specific options for your chosen vendor
3. Include the `--assume-yes` flag to automatically accept any confirmations

Example of a fully automated command for NetApp NVMe:

```bash
python -m launch_wizard \
    --feature-name sanboot \
    --guest-os-type linux \
    --region us-west-2 \
    --ami-id ami-0123456789abcdef0 \
    --subnet-id subnet-0123456789abcdef0 \
    --instance-type m5.large \
    --key-name my-key-pair \
    --security-group-id sg-0123456789abcdef0 \
    --instance-profile-name MyInstanceProfile \
    --root-volume-size 100 \
    --root-volume-type gp3 \
    --assume-yes \
    netapp nvme \
    --netapp-management-ip 10.0.0.10 \
    --netapp-username admin \
    --netapp-password "SecurePassword123" \
    --guest-os-script /path/to/config.yml \
    --guest-os-script /path/to/setup.sh \
    # additional options ...
```

This approach is ideal for scripting and CI/CD pipelines where human interaction is not possible. For security reasons, consider using AWS Secrets Manager to store and retrieve vendor credentials rather than including them directly in command-line arguments.

## Architecture

### Module Organization

The Launch Wizard is organized into the following modules:

- **Vendor-specific modules**: `netapp`, `purestorage`, `generic`
- **Utilities**: Common utilities for AWS interactions, validation, and user data generation
- **User data templates**: Templates for generating instance user data scripts
- **EC2 Helper**: Functions for validating and launching EC2 instances

### Workflow

1. **Parameter Collection**: Collect and validate all required parameters
2. **AWS Resource Validation**: Validate AMI, subnet, instance type, etc.
3. **Storage Configuration**: Configure storage array settings based on vendor
4. **User Data Generation**: Generate appropriate user data script based on vendor, protocol, and OS
5. **Instance Launch**: Launch EC2 instance with the generated user data
6. **Status Reporting**: Report instance launch status and connection information

## Customization

### Adding New Vendors

To add support for a new storage vendor:

1. Create a new directory under `launch_wizard` with the vendor name
2. Implement the required interface for the vendor
3. Add the vendor to the main CLI in `__main__.py`

### Customizing User Data Templates

User data templates are located in the `user_data_templates` directory and are organized by vendor, protocol, and OS type. You can customize these templates to fit your specific requirements.

## Troubleshooting

### Common Issues

- **AWS Credential Issues**: Ensure your AWS credentials are properly configured
- **Network Connectivity**: Verify network connectivity between your Outpost and storage arrays
- **Storage Array Credentials**: Ensure storage array credentials are correct and accessible
- **Instance Launch Failures**: Check security groups, subnet configurations, and IAM permissions
- **Guest OS Script Issues**: Ensure script files exist, are readable, and have correct format (shell script or cloud-config)

### Logs and Debugging

The Launch Wizard provides detailed error messages and validation checks. For more detailed debugging:

```bash
# Enable debug logging
export PYTHONVERBOSE=1
python -m launch_wizard [VENDOR] [PROTOCOL]
```

## Security Considerations

- Store storage array credentials in AWS Secrets Manager
- Use IAM roles with least privilege
- Ensure proper network security groups and firewall rules
- Regularly rotate credentials and audit access

## Disclaimer

This tool is provided as a sample and is not officially supported by AWS. It is intended for demonstration and educational purposes only. AWS is not responsible for issues that may occur when using this tool in a production environment.
