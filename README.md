# Outposts Third-Party Storage Integration Public Samples

This repository provides a collection of tools and utilities for integrating EC2 instances with external storage solutions, particularly focused on AWS Outposts deployments. These samples demonstrate best practices for connecting EC2 instances to various external storage arrays including NetApp, Pure Storage, and generic storage providers.

## Tools Overview

This repository contains three main tools:

### 1. Launch Wizard

A Python-based solution for launching EC2 instances on Outposts that connect to external storage arrays during boot. The Launch Wizard supports multiple storage vendors and protocols (iSCSI, NVMe/TCP) and provides a streamlined experience for configuring and launching instances with external storage.

[Learn more about Launch Wizard →](./launch_wizard/README.md)

### 2. VMIE (VM Import/Export)

A comprehensive Python implementation of the VM Import/Export tool for AWS EC2. This tool provides a complete solution for importing VM images to AWS EC2 and exporting AMIs to RAW format, leveraging the [AWS EC2 VM Import/Export service](https://aws.amazon.com/ec2/vm-import/). Includes support for sanbootable installation for sanboot compatibility.

[Learn more about VMIE →](./vmie/README.md)

### 3. Scripts

Utility scripts to help with common tasks related to EC2 external storage integration, such as obtaining temporary AWS credentials.

[Learn more about Scripts →](./scripts/README.md)

## Prerequisites

### Python Requirements

- Python 3.8 or higher
- Required Python packages (install via `pip install -r requirements.txt`)

### AWS Configuration

- AWS CLI installed and configured with appropriate permissions
- For Outposts deployments: Access to an AWS Outpost with external storage arrays configured

### Storage Array Access

- Appropriate credentials and network access to your storage arrays
- Storage arrays must be properly configured and accessible from your Outposts network

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/aws-samples/sample-outposts-third-party-storage-integration.git
cd sample-outposts-third-party-storage-integration
```

### 2. Set Up Python Environment

For macOS/Linux:

```bash
# Create a virtual environment
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

For Windows:

```powershell
# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure AWS Credentials

Use the provided script to obtain temporary AWS credentials:

```bash
python3 scripts/get_temporary_credentials_awscli.py
```

Follow the instructions to set the environment variables in your shell.

### 4. Choose Your Tool

- For launching EC2 instances with external storage: [Launch Wizard](./launch_wizard/README.md)
- For VM import/export operations: [VMIE](./vmie/README.md)
- For utility scripts: [Scripts](./scripts/README.md)

## Security Best Practices

- Always use temporary credentials when possible
- Follow the principle of least privilege when creating IAM roles and policies
- Secure your storage array credentials using AWS Secrets Manager
- Ensure proper network security groups and firewall rules are in place
- Regularly rotate credentials and audit access

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for details on how to contribute to this project.

## License

This project is licensed under the [MIT-0 License](./LICENSE).

## Code of Conduct

See [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) for details on our code of conduct.

## Disclaimer

These samples are provided as-is and are not officially supported by AWS. They are intended for demonstration and educational purposes only. AWS is not responsible for issues that may occur when using these samples in a production environment.
