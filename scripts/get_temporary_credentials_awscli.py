import os
import platform
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


def main() -> None:
    # Retrieve the temporary credentials using AWS CLI
    print("Requesting temporary AWS credentials...")
    try:
        sts = boto3.client("sts")
        response = sts.get_session_token()

        access_key = response["Credentials"]["AccessKeyId"]
        secret_key = response["Credentials"]["SecretAccessKey"]
        session_token = response["Credentials"]["SessionToken"]
        expiration = response["Credentials"]["Expiration"]
        aws_default_region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")

        if access_key and secret_key and session_token and expiration:
            # Convert the expiration time to datetime object
            expiration_time = expiration.replace(tzinfo=timezone.utc)
            now = datetime.now(tz=timezone.utc)
            duration = expiration_time - now
            duration_seconds = int(duration.total_seconds())
            duration_hours = duration_seconds // 3600
            duration_minutes = (duration_seconds % 3600) // 60

            # Display the temporary credentials in the desired format
            print()
            print("Temporary AWS credentials are generated successfully!")
            if duration_hours == 0:
                print(f"These credentials will be valid for {duration_minutes} minutes.")
            else:
                print(f"These credentials will be valid for {duration_hours} hours and {duration_minutes} minutes.")
            print("Please copy and paste the following commands into your shell to configure your AWS environment:")
            print()

            # Detect the operating system and print appropriate commands
            current_os = platform.system()

            if current_os == "Windows":
                # PowerShell commands for Windows
                print("# PowerShell commands:")
                print(f'$Env:AWS_ACCESS_KEY_ID="{access_key}"')
                print(f'$Env:AWS_SECRET_ACCESS_KEY="{secret_key}"')
                print(f'$Env:AWS_SESSION_TOKEN="{session_token}"')
                print(f'$Env:AWS_DEFAULT_REGION="{aws_default_region}"')
            else:
                # Bash/zsh commands for macOS and Linux
                print("# Bash/zsh commands:")
                print(f"export AWS_ACCESS_KEY_ID={access_key}")
                print(f"export AWS_SECRET_ACCESS_KEY={secret_key}")
                print(f"export AWS_SESSION_TOKEN={session_token}")
                print(f"export AWS_DEFAULT_REGION={aws_default_region}")
        else:
            print(
                "Error: Failed to retrieve complete temporary credentials. Please check your AWS configuration and try again."
            )
    except ClientError as e:
        print(f"Error: Failed to obtain temporary AWS credentials: {str(e)}")
        print("Please verify your AWS configuration and network connectivity, then try again.")


if __name__ == "__main__":
    main()
