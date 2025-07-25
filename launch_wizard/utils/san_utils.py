"""
SAN (Storage Area Network) related utility functions.
"""

import uuid
from typing import Any, Dict, List

from launch_wizard.common.constants import AWS_IQN_PREFIX, AWS_NQN_PREFIX

from .ui_utils import auto_confirm, prompt_with_trim


def generate_host_nqn() -> str:
    """
    Generates a random NQN (NVMe qualified name) for an NVMe host.

    Returns:
        A randomly generated NQN string.
    """

    # Generate a random UUID
    uuid_str = str(uuid.uuid4())

    # Format the NQN string, based on libnvme's nvmf_hostnqn_generate_from_hostid()
    nqn = f"{AWS_NQN_PREFIX}:{uuid_str}"

    return nqn


def generate_initiator_iqn() -> str:
    """
    Generates a random IQN (iSCSI qualified name) for an iSCSI initiator.

    Returns:
        A randomly generated IQN string.
    """

    # Generate a UUID and use the first 8 characters
    unique_part = str(uuid.uuid4())[:8]

    # Construct the IQN
    iqn = f"{AWS_IQN_PREFIX}:{unique_part}"

    return iqn


def generate_or_input_host_nqn() -> str:
    """
    Prompt the user to input a host NQN or to generate a new one.

    Returns:
        Either a user-provided NQN or a generated one.
    """

    if auto_confirm("No host NQN (NVMe Qualified Name) was provided. Would you like to generate one automatically?"):
        return generate_host_nqn()
    else:
        return prompt_with_trim("Please enter a host NQN")


def generate_or_input_initiator_iqn() -> str:
    """
    Prompt the user to input an initiator IQN or to generate a new one.

    Returns:
        Either a user-provided IQN or a generated one.
    """

    if auto_confirm(
        "No initiator IQN (iSCSI Qualified Name) was provided. Would you like to generate one automatically?"
    ):
        return generate_initiator_iqn()
    else:
        return prompt_with_trim("Please enter an initiator IQN")


def generate_discovery_portals(targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate unique discovery portals from a list of iSCSI targets.

    Args:
        targets: List of target dictionaries containing 'ip' and optionally 'port' keys

    Returns:
        List of unique portal dictionaries with 'ip' and 'port' keys
    """

    portals = []
    for target in targets:
        portal = {"ip": target.get("ip"), "port": target.get("port")}
        if portal not in portals:
            portals.append(portal)
    return portals
