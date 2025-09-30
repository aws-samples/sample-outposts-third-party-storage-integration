# Launch Wizard for EC2 with External Storage

The Launch Wizard provides a Python-based solution for launching EC2 instances on AWS Outposts that connect to external storage arrays during boot. This implementation demonstrates how to leverage vendor-specific client libraries and AWS SDK to launch EC2 instances with user data templates that configure the necessary settings to attach network storage at boot time.

## Features

- **Multi-vendor Support**: Dell, HPE, NetApp, Pure Storage, and generic storage providers
- **Multi-protocol Support**: iSCSI and NVMe connectivity options
- **OS Support**: Both Linux and Windows guest operating systems
- **Storage Features**: Data volumes, LocalBoot, and SAN boot configurations
- **Secondary Data Volumes Workflow**: Optional post-boot data volume configuration for SAN boot and LocalBoot
- **Interactive CLI**: Guided experience with validation at each step
- **User Data Generation**: Generate and save user data scripts without launching instances
- **AWS Integration**: Native AWS SDK integration with proper error handling
- **Type Safety**: Full type hints throughout the codebase

## Prerequisites

### AWS Requirements

- AWS CLI configured with appropriate permissions
- Access to an AWS Outpost with external storage arrays configured
- Appropriate IAM permissions for EC2, IAM, Outposts, and Secrets Manager

### Storage Array Requirements

- Dell, HPE, NetApp, or Pure Storage storage array accessible from your Outpost
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

- Dell: `iscsi`, `nvme`
- HPE: `iscsi`, `nvme`
- NetApp: `iscsi`, `nvme`
- Pure Storage: `iscsi`, `nvme`
- Generic: `iscsi`, `nvme`

### Vendor SDK Compatibility

This CLI tool leverages vendor-specific Python SDKs to interact with storage arrays. The compatibility of the tool extends to any device models supported by these underlying libraries:

#### Dell

- **Library**: [`PyPowerStore`](https://github.com/dell/python-powerstore)
- **Supported Devices**: Dell PowerStore systems
- **Validated Devices**: Dell PowerStore 5200T

#### HPE

- **Library**: [`python-3parclient`](https://github.com/hpe-storage/python-3parclient)
- **Supported Devices**: HPE Alletra Storage MP, Alletra Storage 9000, Primera, and 3PAR systems
- **Validated Devices**: HPE Alletra Storage MP

#### NetApp

- **Library**: [`netapp-ontap`](https://github.com/NetApp/ontap-rest-python)
- **Supported Devices**: Any ONTAP-based storage systems
- **Validated Devices**: NetApp AFF A70, AFF A250

#### Pure Storage

- **Library**: [`py-pure-client`](https://github.com/PureStorage-OpenConnect/py-pure-client) (`flasharray` submodule)
- **Supported Devices**: Pure Storage FlashArray systems
- **Validated Devices**: Pure Storage FlashArray//X20

> **Note**: While the tool should be compatible with any device models supported by the respective vendor SDKs, the devices listed above have been specifically validated during development.

### Data Volumes Configuration

The Launch Wizard supports an optional **secondary data volumes workflow** that allows you to configure additional storage volumes after completing SAN boot (`sanboot`) or LocalBoot (`localboot`) operations.

#### How It Works

1. **Primary Workflow Completion**: After completing a SAN boot or LocalBoot workflow, the system will prompt you with an option to configure additional data volumes
2. **Protocol Selection**: You can choose between iSCSI or NVMe protocols for the data volumes (independent of the primary storage protocol)
3. **Vendor Configuration**: Configure storage array settings using the same vendor as your primary workflow
4. **Integrated User Data**: The data volume configuration scripts are automatically integrated into the primary instance's user data, ensuring data volumes are properly attached during the boot process

#### User Experience

When completing a SAN boot or LocalBoot workflow:

```
Data Volumes Configuration
You can optionally configure additional data volumes that will be attached to your instance after the boot process completes.

Would you like to configure additional data volumes? [y/N]: y

Please choose the storage protocol for your data volumes:
  iscsi - iSCSI protocol (default)
  nvme - NVMe over TCP protocol

Choose the protocol (or press Enter for default): nvme
```

#### Benefits

- **Single Workflow**: Complete both boot and data volume configuration in one streamlined process
- **Protocol Flexibility**: Use different protocols for boot volumes and data volumes if desired
- **Automatic Integration**: No manual steps required to attach data volumes after instance launch
- **Vendor Consistency**: Works with all supported storage vendors (Dell, HPE, NetApp, Pure Storage, and generic)

#### Automation Considerations

**Important**: The secondary data volumes workflow currently **only supports interactive mode**. This means it requires user input during execution and cannot be fully automated with the `--assume-yes` flag.

**For Full Automation**, you need to use a two-step approach:

1. **Generate Data Volumes User Data**: First, run the data volumes workflow separately and save the user data to a file:
    ```bash
    # Step 1: Generate data volumes user data
    python -m launch_wizard \
        --feature-name data_volumes \
        --guest-os-type linux \
        --save-user-data-path /tmp/data-volumes-userdata.sh \
        --save-user-data-only \
        --assume-yes \
        netapp nvme \
        --netapp-management-ip 10.0.0.10 \
        --netapp-username admin \
        --netapp-password "SecurePassword123"
    ```
2. **Run Primary Workflow with Data Volumes Script**: Then, run the `sanboot` or `localboot` workflow and specify the data volumes script:
    ```bash
    # Step 2: Run sanboot/localboot with data volumes script
    python -m launch_wizard \
        --feature-name sanboot \
        --guest-os-type linux \
        --region us-west-2 \
        --ami-id ami-0123456789abcdef0 \
        --subnet-id subnet-0123456789abcdef0 \
        --instance-type m5.large \
        --assume-yes \
        netapp nvme \
        --netapp-management-ip 10.0.0.10 \
        --netapp-username admin \
        --netapp-password "SecurePassword123" \
        --guest-os-script /tmp/data-volumes-userdata.sh
    ```

This approach allows you to achieve the same result as the integrated workflow while maintaining full automation compatibility.

### Examples

```bash
# Basic examples (interactive mode)

# Launch an EC2 instance with Dell NVMe storage
python -m launch_wizard dell nvme

# Launch an EC2 instance with HPE iSCSI storage
python -m launch_wizard hpe iscsi

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
- `--save-user-data-path`: Path to save the generated user data script to a local file
- `--save-user-data-only`: Generate and save user data only, without launching an EC2 instance
- `--assume-yes`: Automatically use default answers for all prompts

For a complete list of common options, you can use:

```bash
python -m launch_wizard --help
```

### User Data Generation and Saving

The Launch Wizard now supports generating and saving user data scripts without launching EC2 instances. This feature is useful for:

- **Script Generation**: Create user data scripts for later use or review
- **Automation**: Pre-generate scripts for use in other deployment tools
- **Debugging**: Examine the generated user data before instance launch

#### User Data Options

- `--save-user-data-path`: Specify a file path to save the generated user data script
- `--save-user-data-only`: Generate and save user data only, without launching an EC2 instance (requires `--save-user-data-path`)

#### User Data Generation Examples

Generate user data script without launching an instance:

```bash
# Generate NetApp NVMe user data script only
python -m launch_wizard --save-user-data-path /tmp/userdata.sh --save-user-data-only netapp nvme

# Generate Pure Storage iSCSI user data and launch instance
python -m launch_wizard --save-user-data-path /tmp/userdata.sh purestorage iscsi
```

#### Behavior

- When `--save-user-data-only` is specified without `--save-user-data-path`, the tool will prompt for a file path
- The tool will create the directory structure if it doesn't exist
- When using `--save-user-data-only`, AWS resource validation is skipped since no instance will be launched

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
- Guest OS scripts are **not supported** for Windows guest operating systems
    - Guest OS scripts require the multipart user data format, which Windows AMIs on EC2 do not support
    - Windows AMIs use EC2Config, EC2Launch, or EC2Launch v2 to handle user data and expect a single batch (`<script>…</script>`) or PowerShell (`<powershell>…</powershell>`) payload
    - There is no native support for multipart user data on Windows, unlike Linux images with cloud-init
    - Reference: [EC2 User Data Documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html)
    - **Workaround Disclaimer**: While it is technically possible to pre-install cloudbase-init in Windows OS before SAN boot or LocalBoot to handle multipart user data, this solution is **not validated** and has significant limitations:
        - cloudbase-init only works with IMDSv1, not IMDSv2, which goes against AWS security guidelines
        - This approach is unsupported and may lead to unpredictable behavior
        - Use this workaround at your own risk and only if absolutely necessary
- Scripts specified for `data_volumes` feature will be ignored with a warning message
- Scripts specified for Windows guest OS will be ignored with a warning message
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

#### Dell Options

- `--dell-management-ip`: Management IP address of the Dell storage array
- `--dell-username`: Username for Dell storage array authentication
- `--dell-password`: Password for Dell storage array authentication

#### HPE Options

- `--hpe-management-ip`: Management IP address of the HPE storage array
- `--hpe-username`: Username for HPE storage array authentication
- `--hpe-password`: Password for HPE storage array authentication

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
    python -m launch_wizard dell iscsi --help
    python -m launch_wizard hpe nvme --help
    python -m launch_wizard netapp iscsi --help
    python -m launch_wizard purestorage nvme --help
    python -m launch_wizard generic iscsi --help
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

#### User Data Generation Only

For scenarios where you only need to generate user data scripts without launching instances:

```bash
python -m launch_wizard \
    --save-user-data-path /path/to/userdata.sh \
    --save-user-data-only \
    --assume-yes \
    netapp nvme \
    --netapp-management-ip 10.0.0.10 \
    --netapp-username admin \
    --netapp-password "SecurePassword123" \
    # vendor-specific options ...
```

This approach is ideal for scripting and CI/CD pipelines where human interaction is not possible. For security reasons, consider using AWS Secrets Manager to store and retrieve vendor credentials rather than including them directly in command-line arguments.

## Architecture

### Module Organization

The Launch Wizard is organized into the following modules:

- **Vendor-specific modules**: `dell`, `hpe`, `netapp`, `purestorage`, `generic`
- **Utilities**: Common utilities for AWS interactions, validation, and user data generation
- **User data templates**: Templates for generating instance user data scripts
- **EC2 Helper**: Functions for validating and launching EC2 instances

### Workflow

1. **Parameter Collection**: Collect and validate all required parameters
2. **AWS Resource Validation**: Validate AMI, subnet, instance type, etc.
3. **Storage Configuration**: Configure storage array settings based on vendor
4. **User Data Generation**: Generate appropriate user data script based on vendor, protocol, and OS
5. **Data Volumes Workflow** (optional): For SAN boot and LocalBoot features, prompt for optional data volumes configuration and integrate into user data
6. **Instance Launch**: Launch EC2 instance with the generated user data (including data volumes if configured)
7. **Status Reporting**: Report instance launch status and connection information

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
