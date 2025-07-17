"""
Network validation and parsing utility functions.

These utilities provide validation and parsing for IP addresses, ports, and network endpoints
to ensure proper formatting and validation before use in network operations.
"""

from ipaddress import ip_address
from typing import List, Optional, Tuple


def validate_ip(ip_str: str) -> str:
    """
    Validates that the given string is a valid IP address (IPv4 or IPv6).

    Args:
        ip_str: The IP address string to validate.

    Returns:
        The normalized IP address string if valid.

    Raises:
        ValueError: If the IP address format is invalid.
    """

    try:
        return str(ip_address(ip_str))
    except ValueError as e:
        raise ValueError(f"Invalid IP address: {ip_str}") from e


def validate_port(port_str: str) -> str:
    """
    Validates the given port string.

    Args:
        port_str: The port number string to validate.

    Returns:
        The original port string if valid.

    Raises:
        ValueError: If the port is not a numeric value or is outside the valid range (0-65535).
    """

    if not port_str.isdigit():
        raise ValueError(f"Port must be a numeric value: {port_str}")
    port_num = int(port_str)
    if not 0 <= port_num <= 65535:
        raise ValueError(f"Port number must be between 0 and 65535: {port_num}")
    return port_str


def parse_ip_and_port(s: str) -> Tuple[str, Optional[str]]:
    """
    Parses a string representing an IP address or IP:PORT combination.

    Supports both IPv4 and IPv6 formats:
    - IPv4 addresses, with or without port (e.g., "192.168.1.1", "192.168.1.1:8080")
    - IPv6 addresses, with or without port (e.g., "2001:db8::1", "[2001:db8::1]:443")

    Args:
        s: The input string to parse.

    Returns:
        A tuple where the first element is the normalized IP address string,
        and the second is the port string (or None if no port was specified).

    Raises:
        ValueError: If the input is not a valid IP address or IP:PORT combination.
    """

    if s.startswith("["):  # Possibly [IPv6]:PORT
        ip_end = s.find("]")
        if ip_end == -1:
            raise ValueError("Invalid format: missing closing ']' for IPv6 address")
        ip_part = s[1:ip_end]
        rest = s[ip_end + 1 :]
        if rest:
            if not rest.startswith(":"):
                raise ValueError("Invalid format: expected ':' after ']' for port specification")
            port_part = rest[1:]
        else:
            port_part = None
    else:
        parts = s.rsplit(":", 1)
        if len(parts) == 2:
            ip_part, port_part = parts
        else:
            ip_part = parts[0]
            port_part = None

    validated_ip = validate_ip(ip_part)
    validated_port = validate_port(port_part) if port_part is not None else None

    return validated_ip, validated_port


def validate_ip_and_port(value: str) -> str:
    """
    Validates that the input is a valid IP address or IP:PORT combination.

    Args:
        value: The IP:PORT string to validate.

    Returns:
        The original value if valid.

    Raises:
        ValueError: If the input is not a valid IP:PORT combination.
    """

    parse_ip_and_port(value)
    return value


def validate_ip_list(value_list: Optional[List[str]]) -> List[str]:
    """
    Validates that all items in the input list are valid IP addresses.

    Args:
        value_list: List of IP address strings to validate.

    Returns:
        The validated list of IP addresses.

    Raises:
        ValueError: If any IP address in the list has an invalid format.
    """

    # The value_list is None when there's no input to the CLI
    if value_list is None:
        return []

    for value in value_list:
        validate_ip(value)

    return value_list


def validate_ip_and_port_list(value_list: Optional[List[str]]) -> List[str]:
    """
    Validates that all items in the input list are valid IP address or IP:PORT combinations.

    Args:
        value_list: List of IP:PORT strings to validate.

    Returns:
        The validated list of IP:PORT combinations.

    Raises:
        ValueError: If any IP:PORT combination in the list has an invalid format.
    """

    # The value_list is None when there's no input to the CLI
    if value_list is None:
        return []

    for value in value_list:
        validate_ip_and_port(value)

    return value_list
