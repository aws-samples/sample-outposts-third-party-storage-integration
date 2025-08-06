"""
AWS EC2 core operations and helper functions.
"""

from typing import Any, Dict, List, Optional, Tuple, cast

import boto3
from botocore.exceptions import ClientError
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

from launch_wizard.aws.iam import get_available_instance_profile_names
from launch_wizard.aws.pagination import paginate_aws_response
from launch_wizard.common.constants import DEFAULT_MINIMUM_ROOT_VOLUME_SIZE, VERIFIED_AMIS
from launch_wizard.common.enums import EBSVolumeType, FeatureName, OperationSystemType, OutpostHardwareType
from launch_wizard.common.error_codes import (
    ERR_AWS_AMI_NOT_FOUND,
    ERR_AWS_CLIENT,
    ERR_AWS_INSTANCE_PROFILE_NOT_FOUND,
    ERR_AWS_KEY_PAIR_NOT_FOUND,
    ERR_AWS_SECURITY_GROUP_NOT_FOUND,
    ERR_AWS_SUBNET_LNI_CONFIG_INVALID,
    ERR_AWS_SUBNET_NOT_FOUND,
    ERR_USER_ABORT,
)
from launch_wizard.utils.data_utils import find_first_by_property
from launch_wizard.utils.display_utils import (
    print_table_with_multiple_columns,
    print_table_with_single_column,
    style_var,
)
from launch_wizard.utils.ui_utils import auto_confirm, error_and_exit, prompt_with_trim
from launch_wizard.utils.user_data_utils import (
    generate_user_data_iscsi,
    generate_user_data_nvme,
    save_user_data_path_to_file,
)


def validate_ami(ec2_client: boto3.client, ami_id: Optional[str]) -> str:
    """
    Validate that the specified AMI is from a verified operating system family.

    This function checks if the provided AMI belongs to one of the verified OS families
    that have been tested with this utility. If no AMI is provided, it prompts the user
    for input. For unverified AMIs, it asks for user confirmation before proceeding.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        ami_id: The AMI ID to validate. If None, the user will be prompted to enter one.

    Returns:
        The validated AMI ID as a string.

    Raises:
        typer.Exit: If the user chooses not to proceed with an unverified AMI or if an AWS error occurs.
    """

    def validate_ami_name(ami_name: str) -> bool:
        for verified_ami in VERIFIED_AMIS:
            included_ami_name_patterns = verified_ami.get("includes", [])
            for included_ami_name_pattern in included_ami_name_patterns:
                if included_ami_name_pattern in ami_name:
                    return True
        return False

    # If no AMI is specified, prompt for input
    if not ami_id:
        ami_id = prompt_with_trim("Please enter an AMI ID")
        ami_id = cast(str, ami_id)

    ami_name = get_ami_name(ec2_client, ami_id)

    if validate_ami_name(ami_name):
        Console().print(f"{style_var(ami_name)} ({style_var(ami_id)}) is a verified AMI.")
    else:
        Console().print(f"{style_var(ami_name)} ({style_var(ami_id)}) is not a verified AMI.")
        if not auto_confirm("Do you want to continue with this unverified AMI?"):
            error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    return ami_id


def validate_subnet(ec2_client: boto3.client, subnet_id: Optional[str]) -> Tuple[str, str]:
    """
    Validate that the specified subnet exists and is associated with an AWS Outpost.

    This function retrieves all available Outpost subnets and validates that the provided
    subnet ID exists and is properly associated with an Outpost. If no subnet ID is provided,
    it displays available options and prompts the user to select one.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        subnet_id: The subnet ID to validate. If None, the user will be prompted to select one.

    Returns:
        A tuple containing the validated subnet ID and the associated Outpost ARN.

    Raises:
        typer.Exit: If the subnet is not found, not associated with an Outpost, or if an AWS error occurs.
    """

    available_subnets_for_outposts = get_available_subnets_for_outposts(ec2_client)

    if not subnet_id:
        print_table_with_multiple_columns("Available Outpost subnets", available_subnets_for_outposts)

        subnet_id = prompt_with_trim("Please enter a subnet ID")
        subnet_id = cast(str, subnet_id)

    selected_subnet = find_first_by_property(items=available_subnets_for_outposts, key="subnet_id", value=subnet_id)

    if not selected_subnet:
        error_and_exit(
            f"Subnet {style_var(subnet_id, color='yellow')} is not available. It either does not exist or is not associated with an Outpost.",
            code=ERR_AWS_SUBNET_NOT_FOUND,
        )

    outpost_arn = selected_subnet["outpost_arn"]

    Console().print(f"Using subnet {style_var(subnet_id)} associated with Outpost {style_var(outpost_arn)}.")

    return subnet_id, outpost_arn


def validate_network(ec2_client: boto3.client, subnet_id: str, outpost_hardware_type: OutpostHardwareType) -> None:
    """
    Validate and configure network settings for the specified subnet and Outpost hardware type.

    For Outpost Servers, this function ensures that the subnet has Local Network Interface (LNI)
    configured at device index 1, which is required for instances to connect to the on-premises
    network. If LNI is not configured, it offers to update the subnet configuration automatically.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        subnet_id: The ID of the subnet to validate and configure.
        outpost_hardware_type: The type of Outpost hardware (RACK or SERVER).

    Raises:
        typer.Exit: If LNI configuration is required but not enabled, the user declines to configure it,
                   or if an AWS error occurs.
    """

    try:
        if outpost_hardware_type == OutpostHardwareType.SERVER:
            describe_subnets_response = ec2_client.describe_subnets(SubnetIds=[subnet_id])
            subnet = describe_subnets_response["Subnets"][0]

            if "EnableLniAtDeviceIndex" not in subnet or int(subnet["EnableLniAtDeviceIndex"]) != 1:
                if auto_confirm(
                    "This tool requires the subnet to have Local Network Interface (LNI) configured at device index 1. Would you like to update the subnet configuration?"
                ):
                    # Enable LNI at the specified device index
                    ec2_client.modify_subnet_attribute(SubnetId=subnet_id, EnableLniAtDeviceIndex=1)
                    # Update the subnet with the new data
                    describe_subnets_response = ec2_client.describe_subnets(SubnetIds=[subnet_id])
                    subnet = describe_subnets_response["Subnets"][0]
                else:
                    error_and_exit(
                        "Subnet doesn't have Local Network Interface (LNI) configured at device index 1.",
                        code=ERR_AWS_SUBNET_LNI_CONFIG_INVALID,
                    )

            Console().print(
                f"Subnet {style_var(subnet_id)} has Local Network Interface (LNI) configured at index {style_var(subnet['EnableLniAtDeviceIndex'])}."
            )
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)


def validate_key_pair(ec2_client: boto3.client, key_pair_name: Optional[str]) -> Optional[str]:
    """
    Validate that the specified key pair exists in the AWS account.

    This function checks if the provided key pair name exists in the account. If no key pair
    is provided, it offers the option to proceed without one or displays available key pairs
    for the user to select from.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        key_pair_name: The key pair name to validate. If None, the user will be prompted.

    Returns:
        The validated key pair name as a string, or None if proceeding without a key pair.

    Raises:
        typer.Exit: If the key pair is not found in the account or if an AWS error occurs.
    """

    if not key_pair_name and auto_confirm(
        "No key pair name specified. Would you like to proceed without a key pair? (This will limit your ability to connect to the instance)"
    ):
        return None

    available_key_pair_names = get_available_key_pair_names(ec2_client)

    if not key_pair_name:
        print_table_with_single_column("Available key pairs", available_key_pair_names, column_name="Key Pair Name")

        key_pair_name = prompt_with_trim("Please enter a key pair name")
        key_pair_name = cast(str, key_pair_name)

    if key_pair_name not in available_key_pair_names:
        error_and_exit(
            f"Key pair {style_var(key_pair_name, color='yellow')} is not available in your account.",
            code=ERR_AWS_KEY_PAIR_NOT_FOUND,
        )

    return key_pair_name


def validate_security_group(ec2_client: boto3.client, security_group_id: Optional[str]) -> Optional[str]:
    """
    Validate that the specified security group exists in the AWS account.

    This function checks if the provided security group ID exists in the account. If no security
    group is provided, it offers the option to use the default VPC security group or displays
    available security groups for the user to select from.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        security_group_id: The security group ID to validate. If None, the user will be prompted.

    Returns:
        The validated security group ID as a string, or None if using the default security group.

    Raises:
        typer.Exit: If the security group is not found in the account or if an AWS error occurs.
    """

    if not security_group_id and auto_confirm(
        "No security group specified. Would you like to use the default security group in the VPC?"
    ):
        return None

    available_security_group_ids = get_available_security_group_ids(ec2_client)

    if not security_group_id:
        print_table_with_single_column(
            "Available security groups", available_security_group_ids, column_name="Security Group ID"
        )

        security_group_id = prompt_with_trim("Please enter a security group ID")
        security_group_id = cast(str, security_group_id)

    if security_group_id not in available_security_group_ids:
        error_and_exit(
            f"Security group {style_var(security_group_id, color='yellow')} is not available in your account.",
            code=ERR_AWS_SECURITY_GROUP_NOT_FOUND,
        )

    return security_group_id


def validate_instance_profile(iam_client: boto3.client, instance_profile_name: Optional[str]) -> Optional[str]:
    """
    Validate that the specified IAM instance profile exists in the AWS account.

    This function checks if the provided instance profile name exists in the account. If no
    instance profile is provided, it offers the option to proceed without one or displays
    available instance profiles for the user to select from.

    Args:
        iam_client: The boto3 IAM client for AWS API calls.
        instance_profile_name: The instance profile name to validate. If None, the user will be prompted.

    Returns:
        The validated instance profile name as a string, or None if proceeding without one.

    Raises:
        typer.Exit: If the instance profile is not found in the account or if an AWS error occurs.
    """

    if not instance_profile_name and auto_confirm(
        "No instance profile specified. Would you like to proceed without an instance profile? (This will limit the instance's ability to access AWS services)"
    ):
        return None

    available_instance_profile_names = get_available_instance_profile_names(iam_client)

    if not instance_profile_name:
        print_table_with_single_column(
            "Available instance profiles", available_instance_profile_names, column_name="Instance Profile Name"
        )

        instance_profile_name = prompt_with_trim("Please enter an instance profile name")
        instance_profile_name = cast(str, instance_profile_name)

    if instance_profile_name not in available_instance_profile_names:
        error_and_exit(
            f"Instance profile {style_var(instance_profile_name, color='yellow')} is not available in your account.",
            code=ERR_AWS_INSTANCE_PROFILE_NOT_FOUND,
        )

    return instance_profile_name


def validate_instance_name(instance_name: Optional[str]) -> Optional[str]:
    """
    Validate and prompt for EC2 instance name if not provided.

    This function handles the instance name parameter. If no instance name is provided,
    it prompts the user to enter one. The instance name will be used as the 'Name' tag
    for the EC2 instance.

    Args:
        instance_name: The instance name to validate. If None, the user will be prompted.

    Returns:
        The validated instance name as a string, or None if the user chooses to proceed without one.
    """

    if not instance_name:
        if auto_confirm("No instance name specified. Would you like to proceed without naming the instance?"):
            return None

        instance_name = prompt_with_trim("Please enter an instance name")
        instance_name = cast(str, instance_name)

    return instance_name


def validate_root_volume_options(
    ec2_client: boto3.client, ami_id: str, root_volume_size: Optional[int], root_volume_type: Optional[EBSVolumeType]
) -> Tuple[Optional[int], Optional[EBSVolumeType], Optional[str]]:
    """
    Validate and configure root volume size and type options for the EC2 instance.

    This function validates the root volume configuration by checking the AMI's default settings
    and prompting the user for custom values if needed. It ensures that the volume size meets
    minimum requirements and that the volume type is valid.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        ami_id: The AMI ID to get default volume configuration from.
        root_volume_size: The desired root volume size in GiB. If None, user will be prompted.
        root_volume_type: The desired root volume type. If None, user will be prompted.

    Returns:
        A tuple containing the validated volume size, volume type, and root device name.
        Returns (None, None, None) if using AMI defaults.

    Raises:
        typer.Exit: If the volume size is below minimum requirements or if an AWS error occurs.
    """

    # Get AMI details to determine default volume size, type, and root device name
    try:
        describe_images_response = ec2_client.describe_images(ImageIds=[ami_id])
        if not describe_images_response["Images"]:
            error_and_exit(f"AMI {style_var(ami_id, color='yellow')} not found.", code=ERR_AWS_AMI_NOT_FOUND)

        ami = describe_images_response["Images"][0]

        # Get root device name
        root_device_name = ami["RootDeviceName"]

        # Find the root device mapping to get default size and type
        default_volume_size = DEFAULT_MINIMUM_ROOT_VOLUME_SIZE
        default_volume_type = None

        for block_device in ami.get("BlockDeviceMappings", []):
            if block_device["DeviceName"] == root_device_name and "Ebs" in block_device:
                ebs_config = block_device["Ebs"]
                default_volume_size = ebs_config.get("VolumeSize", DEFAULT_MINIMUM_ROOT_VOLUME_SIZE)
                default_volume_type = ebs_config.get("VolumeType")
                break

    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)

    # If neither option is specified, return early with None values
    if not root_volume_size and not root_volume_type:
        if auto_confirm(
            "No root volume size or type specified. Would you like to use the default configuration from the selected AMI?"
        ):
            return None, None, None

    # Prompt for root volume size if not provided
    if not root_volume_size:
        size_prompt = f"Would you like to use the default root volume size ({default_volume_size} GiB)?"

        if not auto_confirm(size_prompt):
            while True:
                try:
                    size_input = prompt_with_trim(
                        f"Please enter the root volume size (minimum {default_volume_size} GiB)",
                        default=default_volume_size,
                    )
                    root_volume_size = int(size_input)

                    if root_volume_size < default_volume_size:
                        Console().print(
                            style_var(f"Volume size must be at least {default_volume_size} GiB.", color="red")
                        )
                        continue
                    break
                except ValueError:
                    Console().print(style_var("Please enter a valid number.", color="red"))
                    continue
    else:
        # Validate provided size
        if root_volume_size < default_volume_size:
            error_and_exit(
                f"Root volume size {style_var(root_volume_size)} GiB is less than the minimum required {style_var(default_volume_size)} GiB for this AMI.",
                code=ERR_AWS_CLIENT,
            )

    # Prompt for root volume type if not provided
    if not root_volume_type:
        if default_volume_type:
            type_prompt = f"Would you like to use the default root volume type ({default_volume_type})?"
        else:
            type_prompt = "Would you like to use the default root volume type?"

        if not auto_confirm(type_prompt):
            available_volume_types = [volume_type.value for volume_type in EBSVolumeType]
            print_table_with_single_column(
                "Available EBS volume types", available_volume_types, column_name="Volume Type"
            )

            while True:
                try:
                    volume_type_input = prompt_with_trim(
                        "Please enter the root volume type", default=default_volume_type
                    )
                    root_volume_type = EBSVolumeType(volume_type_input)
                    break
                except ValueError:
                    Console().print(style_var("Please enter a valid volume type from the list above.", color="red"))
                    continue

    # Return the root device name only if there are customizations
    return root_volume_size, root_volume_type, root_device_name if (root_volume_size or root_volume_type) else None


def get_ami_name(ec2_client: boto3.client, ami_id: str) -> str:
    """
    Retrieve the name of the specified AMI.

    This function queries AWS to get the human-readable name associated with the given AMI ID.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        ami_id: The AMI ID to retrieve the name for.

    Returns:
        The name of the AMI as a string.

    Raises:
        typer.Exit: If the AMI is not found or if an AWS error occurs.
    """

    try:
        describe_images_response = ec2_client.describe_images(ImageIds=[ami_id])
        if not describe_images_response["Images"]:
            error_and_exit(f"AMI {style_var(ami_id, color='yellow')} could not be found.", code=ERR_AWS_AMI_NOT_FOUND)

        return describe_images_response["Images"][0]["Name"]
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)


def get_available_subnets_for_outposts(ec2_client: boto3.client) -> List[Dict[str, str]]:
    """
    Retrieve all subnets that are associated with AWS Outposts.

    This function queries all subnets in the account and filters them to return only those
    that are associated with Outposts. It returns a simplified list containing just the
    subnet ID and Outpost ARN for each subnet.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.

    Returns:
        A list of dictionaries, each containing 'subnet_id' and 'outpost_arn' keys.

    Raises:
        typer.Exit: If no Outpost subnets are found or if an AWS error occurs.
    """

    # Use the paginate function to get all subnets
    available_subnets = paginate_aws_response(ec2_client.describe_subnets, "Subnets")

    subnets_for_outposts = [subnet for subnet in available_subnets if "OutpostArn" in subnet]

    if not subnets_for_outposts:
        error_and_exit("There are no subnets associated with Outposts in your account.", code=ERR_AWS_SUBNET_NOT_FOUND)

    # Only return a subset of the properties in the response
    result = []
    for subnet in subnets_for_outposts:
        result.append({"subnet_id": subnet["SubnetId"], "outpost_arn": subnet["OutpostArn"]})
    return result


def get_available_key_pair_names(ec2_client: boto3.client) -> List[str]:
    """
    Retrieve all key pair names available in the AWS account.

    This function queries all key pairs in the account and returns their names
    for use in instance launching and SSH access configuration.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.

    Returns:
        A list of key pair names as strings.

    Raises:
        typer.Exit: If an AWS error occurs during the API call.
    """

    # Use the paginate function to get all key pairs
    available_key_pairs = paginate_aws_response(ec2_client.describe_key_pairs, "KeyPairs")

    available_key_pair_names = [key_pair["KeyName"] for key_pair in available_key_pairs]

    return available_key_pair_names


def get_available_security_group_ids(ec2_client: boto3.client) -> List[str]:
    """
    Retrieve all security group IDs available in the AWS account.

    This function queries all security groups in the account and returns their IDs
    for use in instance network security configuration.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.

    Returns:
        A list of security group IDs as strings.

    Raises:
        typer.Exit: If an AWS error occurs during the API call.
    """

    available_security_groups = paginate_aws_response(ec2_client.describe_security_groups, "SecurityGroups")

    available_security_group_ids = [security_group["GroupId"] for security_group in available_security_groups]

    return available_security_group_ids


def get_root_volume_device_name(ec2_client: boto3.client, ami_id: str) -> str:
    """
    Retrieve the root volume device name for the specified AMI.

    This function queries the AMI details to determine the device name used for the root volume,
    which is needed for configuring custom root volume settings during instance launch.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        ami_id: The AMI ID to query for root device information.

    Returns:
        The root device name as a string (e.g., '/dev/sda1' or '/dev/xvda').

    Raises:
        typer.Exit: If the AMI is not found or if an AWS error occurs.
    """

    try:
        Console().print(f"Using AMI {style_var(ami_id)}.")
        describe_images_response = ec2_client.describe_images(ImageIds=[ami_id])

        if not describe_images_response["Images"]:
            error_and_exit(f"AMI {style_var(ami_id, color='yellow')} not found.", code=ERR_AWS_AMI_NOT_FOUND)

        return describe_images_response["Images"][0]["RootDeviceName"]
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)


def get_vpc_id(ec2_client: boto3.client, subnet_id: str) -> str:
    """
    Retrieve the VPC ID associated with the specified subnet.

    This function queries the subnet details to determine which VPC it belongs to,
    which is needed for security group and network configuration.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        subnet_id: The subnet ID to query for VPC information.

    Returns:
        The VPC ID as a string.

    Raises:
        typer.Exit: If the subnet is not found or if an AWS error occurs.
    """

    try:
        describe_subnets_response = ec2_client.describe_subnets(SubnetIds=[subnet_id])

        if not describe_subnets_response["Subnets"]:
            error_and_exit(
                f"No subnet found with ID {style_var(subnet_id, color='yellow')}.", code=ERR_AWS_SUBNET_NOT_FOUND
            )

        return describe_subnets_response["Subnets"][0]["VpcId"]
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)


def get_default_security_group_id(ec2_client: boto3.client, vpc_id: str) -> str:
    """
    Retrieve the default security group ID for the specified VPC.

    This function finds the default security group within a VPC, which is used
    when no specific security group is provided for instance launch.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        vpc_id: The VPC ID to find the default security group for.

    Returns:
        The default security group ID as a string.

    Raises:
        typer.Exit: If no default security group is found for the VPC or if an AWS error occurs.
    """

    try:
        describe_security_groups_response = ec2_client.describe_security_groups(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}, {"Name": "group-name", "Values": ["default"]}]
        )

        if not describe_security_groups_response["SecurityGroups"]:
            error_and_exit(
                f"No security group found for VPC {style_var(vpc_id, color='yellow')}.",
                code=ERR_AWS_SECURITY_GROUP_NOT_FOUND,
            )

        return describe_security_groups_response["SecurityGroups"][0]["GroupId"]
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)


def create_network_interface_with_coip(ec2_client: boto3.client, subnet_id: str, security_group_id: str) -> str:
    """
    Create a network interface with Customer-owned IP (CoIP) address allocation.

    This function creates a network interface in the specified subnet, allocates an elastic
    IPv4 address from the Customer-owned IP pool associated with the Outpost, and associates
    the IP with the network interface. This is required for Outpost RACK hardware to enable
    connectivity to on-premises networks.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        subnet_id: The subnet ID where the network interface will be created.
        security_group_id: The security group ID to associate with the network interface.

    Returns:
        The network interface ID as a string.

    Raises:
        typer.Exit: If any step in the process fails or if an AWS error occurs.
    """

    try:
        # Create a network interface
        create_network_interface_response = ec2_client.create_network_interface(
            SubnetId=subnet_id, Groups=[security_group_id]
        )
        network_interface_id = create_network_interface_response["NetworkInterface"]["NetworkInterfaceId"]
        Console().print(f"Created network interface with ID: {style_var(network_interface_id)}.")

        # Find the Outpost ARN associated with the subnet
        describe_subnets_response = ec2_client.describe_subnets(SubnetIds=[subnet_id])
        outpost_arn = describe_subnets_response["Subnets"][0]["OutpostArn"]
        Console().print(f"Using Outpost with ARN: {style_var(outpost_arn)}.")

        # Find the local gateway ID associated with the Outpost ARN
        local_gateway_route_tables = paginate_aws_response(
            ec2_client.describe_local_gateway_route_tables,
            "LocalGatewayRouteTables",
            Filters=[{"Name": "outpost-arn", "Values": [outpost_arn]}],
        )
        local_gateway_route_table_id = local_gateway_route_tables[0]["LocalGatewayRouteTableId"]
        Console().print(f"Using local gateway route table with ID: {style_var(local_gateway_route_table_id)}.")

        # Find the CoIP pool ID associated with the local gateway ID
        coip_pools = paginate_aws_response(
            ec2_client.describe_coip_pools,
            "CoipPools",
            Filters=[{"Name": "coip-pool.local-gateway-route-table-id", "Values": [local_gateway_route_table_id]}],
        )
        coip_pool_id = coip_pools[0]["PoolId"]
        Console().print(f"Using Customer-owned IP (CoIP) pool with ID: {style_var(coip_pool_id)}.")

        # Allocate an elastic IPv4 address pool
        allocate_address_response = ec2_client.allocate_address(CustomerOwnedIpv4Pool=coip_pool_id)
        allocation_id = allocate_address_response["AllocationId"]
        Console().print(
            f"Allocated elastic IP address with allocation ID: {style_var(allocation_id)} from CoIP pool: {style_var(coip_pool_id)}."
        )

        # Associate the IP pool with the network interface
        ec2_client.associate_address(AllocationId=allocation_id, NetworkInterfaceId=network_interface_id)
        Console().print(
            f"Associated elastic IP address (allocation ID: {style_var(allocation_id)}) with network interface: {style_var(network_interface_id)}."
        )

        return network_interface_id
    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)


def launch_instance(
    ec2_client: boto3.client,
    outpost_hardware_type: OutpostHardwareType,
    ami_id: str,
    instance_type: str,
    subnet_id: str,
    user_data: str,
    key_name: Optional[str] = None,
    security_group_id: Optional[str] = None,
    instance_profile_name: Optional[str] = None,
    instance_name: Optional[str] = None,
    root_volume_device_name: Optional[str] = None,
    root_volume_size: Optional[int] = None,
    root_volume_type: Optional[EBSVolumeType] = None,
) -> None:
    """
    Launch an EC2 instance on AWS Outpost with the specified configuration.

    This function creates and launches an EC2 instance with the provided parameters and user data.
    It handles different network configurations based on the Outpost hardware type (RACK vs SERVER)
    and configures appropriate network interfaces, security groups, and storage options.

    Args:
        ec2_client: The boto3 EC2 client for AWS API calls.
        outpost_hardware_type: The type of Outpost hardware (RACK or SERVER).
        ami_id: The AMI ID to launch the instance from.
        instance_type: The EC2 instance type to launch.
        subnet_id: The subnet ID where the instance will be launched.
        user_data: The user data script to run on instance startup.
        key_name: The key pair name for SSH access (optional).
        security_group_id: The security group ID to associate (optional, uses default if not provided).
        instance_profile_name: The IAM instance profile name to attach (optional).
        instance_name: The name to assign to the instance as a 'Name' tag (optional).
        root_volume_device_name: The root volume device name for custom configuration (optional).
        root_volume_size: The root volume size in GiB (optional).
        root_volume_type: The root volume type (optional).

    Raises:
        typer.Exit: If the instance launch fails or if an AWS error occurs.
    """

    try:
        # Prepare the parameters for the instance
        instance_params: Dict[str, Any] = {
            "ImageId": ami_id,
            "InstanceType": instance_type,
            "MinCount": 1,
            "MaxCount": 1,
            "UserData": user_data,
        }

        if not security_group_id:
            # If the security group is not specified, use the default one of the VPC
            vpc_id = get_vpc_id(ec2_client, subnet_id)
            security_group_id = get_default_security_group_id(ec2_client, vpc_id)

        if outpost_hardware_type == OutpostHardwareType.SERVER:
            network_interfaces = [
                # Default interface
                {
                    "DeviceIndex": 0,
                    "SubnetId": subnet_id,
                    "Groups": [security_group_id],
                },
                # LNI
                {
                    "DeviceIndex": 1,
                    "SubnetId": subnet_id,
                    "Groups": [security_group_id],
                },
            ]
        else:
            # Create a network interface and associate it with the CoIP
            network_interface_id = create_network_interface_with_coip(ec2_client, subnet_id, security_group_id)

            # Use the created network interface
            network_interfaces = [{"DeviceIndex": 0, "NetworkInterfaceId": network_interface_id}]

        instance_params["NetworkInterfaces"] = network_interfaces

        if key_name:
            instance_params["KeyName"] = key_name

        if instance_profile_name:
            instance_params["IamInstanceProfile"] = {"Name": instance_profile_name}

        if root_volume_device_name:
            instance_params["BlockDeviceMappings"] = [
                {
                    "DeviceName": root_volume_device_name,
                    "Ebs": {},
                }
            ]
            if root_volume_size:
                instance_params["BlockDeviceMappings"][0]["Ebs"]["VolumeSize"] = root_volume_size
            if root_volume_type:
                instance_params["BlockDeviceMappings"][0]["Ebs"]["VolumeType"] = root_volume_type

        # Add Name tag if instance_name is provided
        if instance_name:
            instance_params["TagSpecifications"] = [
                {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": instance_name}]}
            ]

        Console().print("Launching the EC2 instance...")
        # Launch the instance
        run_instances_response = ec2_client.run_instances(**instance_params)

        #  Launch instance response
        Console().print(Pretty(run_instances_response))
        Console().print(
            f"Instance {style_var(run_instances_response['Instances'][0]['InstanceId'])} has been launched successfully."
        )

    except ClientError as e:
        error_and_exit(str(e), code=ERR_AWS_CLIENT)


def launch_instance_helper_nvme(
    feature_name: FeatureName,
    guest_os_type: OperationSystemType,
    ec2_client: boto3.client,
    outpost_hardware_type: OutpostHardwareType,
    ami_id: str,
    instance_type: str,
    subnet_id: str,
    key_name: Optional[str],
    security_group_id: Optional[str],
    instance_profile_name: Optional[str],
    instance_name: Optional[str],
    root_volume_device_name: Optional[str],
    root_volume_size: Optional[int],
    root_volume_type: Optional[EBSVolumeType],
    host_nqn: str,
    subsystems: List[Dict[str, str]],
    enable_dm_multipath: Optional[bool],
    guest_os_scripts: Optional[List[Dict[str, str]]],
    save_user_data_path: Optional[str],
    save_user_data_only: Optional[bool],
) -> None:
    """
    Launch an EC2 instance configured for NVMe storage connectivity.

    This function prepares and launches an EC2 instance with user data specifically configured
    for NVMe storage connections. It generates the appropriate user data script based on the
    provided NVMe subsystems and host NQN, displays it for user confirmation, and then
    launches the instance.

    Args:
        feature_name: The storage feature being configured (data_volumes, localboot, or sanboot).
        guest_os_type: The operating system type (linux or windows).
        ec2_client: The boto3 EC2 client for AWS API calls.
        outpost_hardware_type: The type of Outpost hardware (RACK or SERVER).
        ami_id: The AMI ID to launch the instance from.
        instance_type: The EC2 instance type to launch.
        subnet_id: The subnet ID where the instance will be launched.
        key_name: The key pair name for SSH access (optional).
        security_group_id: The security group ID to associate (optional).
        instance_profile_name: The IAM instance profile name to attach (optional).
        instance_name: The name to assign to the instance as a 'Name' tag (optional).
        root_volume_device_name: The root volume device name for custom configuration (optional).
        root_volume_size: The root volume size in GiB (optional).
        root_volume_type: The root volume type (optional).
        host_nqn: The NVMe host qualified name for the instance.
        subsystems: List of NVMe subsystem configurations.
        enable_dm_multipath: Whether to enable Device Mapper Multipath (optional).
        guest_os_scripts: List of additional guest OS scripts to include in user data (optional).
        save_user_data_path: File path to save the generated user data script (optional).
        save_user_data_only: If True, only generate and save user data without launching instance (optional).

    Raises:
        typer.Exit: If the user cancels the operation or if the instance launch fails.
    """

    # Generate user data script
    user_data = generate_user_data_nvme(
        feature_name=feature_name,
        guest_os_type=guest_os_type,
        host_nqn=host_nqn,
        subsystems=subsystems,
        enable_dm_multipath=enable_dm_multipath,
        guest_os_scripts=guest_os_scripts,
    )

    launch_instance_helper(
        ec2_client=ec2_client,
        outpost_hardware_type=outpost_hardware_type,
        ami_id=ami_id,
        instance_type=instance_type,
        subnet_id=subnet_id,
        user_data=user_data,
        key_name=key_name,
        security_group_id=security_group_id,
        instance_profile_name=instance_profile_name,
        instance_name=instance_name,
        root_volume_device_name=root_volume_device_name,
        root_volume_size=root_volume_size,
        root_volume_type=root_volume_type,
        save_user_data_path=save_user_data_path,
        save_user_data_only=save_user_data_only,
    )


def launch_instance_helper_iscsi(
    feature_name: FeatureName,
    guest_os_type: OperationSystemType,
    ec2_client: boto3.client,
    outpost_hardware_type: OutpostHardwareType,
    ami_id: str,
    instance_type: str,
    subnet_id: str,
    key_name: Optional[str],
    security_group_id: Optional[str],
    instance_profile_name: Optional[str],
    instance_name: Optional[str],
    root_volume_device_name: Optional[str],
    root_volume_size: Optional[int],
    root_volume_type: Optional[EBSVolumeType],
    initiator_iqn: str,
    targets: List[Dict[str, str]],
    portals: List[Dict[str, str]],
    guest_os_scripts: Optional[List[Dict[str, str]]],
    save_user_data_path: Optional[str],
    save_user_data_only: Optional[bool],
) -> None:
    """
    Launch an EC2 instance configured for iSCSI storage connectivity.

    This function prepares and launches an EC2 instance with user data specifically configured
    for iSCSI storage connections. It generates the appropriate user data script based on the
    provided iSCSI targets, portals, and initiator IQN, displays it for user confirmation,
    and then launches the instance.

    Args:
        feature_name: The storage feature being configured (data_volumes, localboot, or sanboot).
        guest_os_type: The operating system type (linux or windows).
        ec2_client: The boto3 EC2 client for AWS API calls.
        outpost_hardware_type: The type of Outpost hardware (RACK or SERVER).
        ami_id: The AMI ID to launch the instance from.
        instance_type: The EC2 instance type to launch.
        subnet_id: The subnet ID where the instance will be launched.
        key_name: The key pair name for SSH access (optional).
        security_group_id: The security group ID to associate (optional).
        instance_profile_name: The IAM instance profile name to attach (optional).
        instance_name: The name to assign to the instance as a 'Name' tag (optional).
        root_volume_device_name: The root volume device name for custom configuration (optional).
        root_volume_size: The root volume size in GiB (optional).
        root_volume_type: The root volume type (optional).
        initiator_iqn: The iSCSI initiator qualified name for the instance.
        targets: List of iSCSI target configurations.
        portals: List of iSCSI portal configurations for discovery.
        guest_os_scripts: List of additional guest OS scripts to include in user data (optional).
        save_user_data_path: File path to save the generated user data script (optional).
        save_user_data_only: If True, only generate and save user data without launching instance (optional).

    Raises:
        typer.Exit: If the user cancels the operation or if the instance launch fails.
    """

    # Generate user data script
    user_data = generate_user_data_iscsi(
        feature_name=feature_name,
        guest_os_type=guest_os_type,
        outpost_hardware_type=outpost_hardware_type,
        initiator_iqn=initiator_iqn,
        targets=targets,
        portals=portals,
        guest_os_scripts=guest_os_scripts,
    )

    launch_instance_helper(
        ec2_client=ec2_client,
        outpost_hardware_type=outpost_hardware_type,
        ami_id=ami_id,
        instance_type=instance_type,
        subnet_id=subnet_id,
        user_data=user_data,
        key_name=key_name,
        security_group_id=security_group_id,
        instance_profile_name=instance_profile_name,
        instance_name=instance_name,
        root_volume_device_name=root_volume_device_name,
        root_volume_size=root_volume_size,
        root_volume_type=root_volume_type,
        save_user_data_path=save_user_data_path,
        save_user_data_only=save_user_data_only,
    )


def launch_instance_helper(
    ec2_client: boto3.client,
    outpost_hardware_type: OutpostHardwareType,
    ami_id: str,
    instance_type: str,
    subnet_id: str,
    user_data: str,
    key_name: Optional[str],
    security_group_id: Optional[str],
    instance_profile_name: Optional[str],
    instance_name: Optional[str],
    root_volume_device_name: Optional[str],
    root_volume_size: Optional[int],
    root_volume_type: Optional[EBSVolumeType],
    save_user_data_path: Optional[str],
    save_user_data_only: Optional[bool],
) -> None:
    # Print out the generated user data script
    Console().print(Panel(user_data, title="User Data Script", style="cyan"))

    # Save user data to file if requested
    if save_user_data_path:
        save_user_data_path_to_file(user_data, save_user_data_path)

    # If save_user_data_only is True, skip instance launching
    if save_user_data_only:
        Console().print("User data generation completed. Skipping EC2 instance launch.")
        return

    if not auto_confirm("Would you like to proceed with launching the instance using the above user data script?"):
        error_and_exit("Operation aborted by user.", code=ERR_USER_ABORT)

    # Launch the instance
    launch_instance(
        ec2_client=ec2_client,
        outpost_hardware_type=outpost_hardware_type,
        ami_id=ami_id,
        instance_type=instance_type,
        subnet_id=subnet_id,
        user_data=user_data,
        key_name=key_name,
        security_group_id=security_group_id,
        instance_profile_name=instance_profile_name,
        instance_name=instance_name,
        root_volume_device_name=root_volume_device_name,
        root_volume_size=root_volume_size,
        root_volume_type=root_volume_type,
    )
