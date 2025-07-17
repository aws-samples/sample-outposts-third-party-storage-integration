# Utility Scripts

This directory contains utility scripts to help with common tasks related to EC2 external storage integration. These scripts are designed to simplify setup, configuration, and management tasks when working with EC2 instances and external storage arrays.

## Available Scripts

### get_temporary_credentials_awscli.py

A utility script to obtain temporary AWS credentials using the AWS CLI. This script generates temporary credentials and provides the necessary export commands for your shell environment.

#### Features

- **Cross-platform Support**: Works on Windows, macOS, and Linux
- **Environment Detection**: Automatically detects your operating system and provides appropriate commands
- **Credential Duration**: Shows the validity period of the generated credentials
- **Error Handling**: Provides clear error messages if credential generation fails

#### Usage

```bash
python3 scripts/get_temporary_credentials_awscli.py
```

#### Example Output

```
Requesting temporary AWS credentials...

Temporary AWS credentials are generated successfully!
These credentials will be valid for 11 hours and 59 minutes.
Please copy and paste the following commands into your shell to configure your AWS environment:

# Bash/zsh commands:
export AWS_ACCESS_KEY_ID=ASIA1234567890EXAMPLE
export AWS_SECRET_ACCESS_KEY=abcdefghijklmnopqrstuvwxyz1234567890EXAMPLE
export AWS_SESSION_TOKEN=AQoEXAMPLEH4aoAH0gNCAPyJxz4BlCFFxWNE1OPTgk5TthT...
export AWS_DEFAULT_REGION=us-west-2
```

#### Requirements

- AWS CLI installed and configured
- Valid AWS credentials with permission to call the STS GetSessionToken API

## Adding New Scripts

When adding new utility scripts to this directory, please follow these guidelines:

1. **Naming Convention**: Use descriptive names with underscores (e.g., `get_temporary_credentials_awscli.py`)
2. **Documentation**: Include a docstring at the top of the script explaining its purpose and usage
3. **Error Handling**: Implement proper error handling with clear error messages
4. **Cross-platform**: Ensure scripts work across different operating systems when possible
5. **Type Hints**: Use Python type hints to improve code readability and maintainability
6. **Update README**: Add your script to this README with a description and usage examples

## Best Practices

- Keep scripts focused on a single task or related set of tasks
- Provide clear error messages and help text
- Use environment variables for configuration when appropriate
- Follow Python best practices for code style and organization
- Include proper error handling and input validation

## Security Considerations

- Never hardcode credentials in scripts
- Use temporary credentials when possible
- Follow the principle of least privilege when requesting permissions
- Be careful with script outputs that might contain sensitive information

## Disclaimer

These scripts are provided as-is and are not officially supported by AWS. They are intended for demonstration and educational purposes only. AWS is not responsible for issues that may occur when using these scripts in a production environment.
