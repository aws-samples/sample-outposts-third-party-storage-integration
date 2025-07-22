from enum import Enum


class FeatureName(str, Enum):
    DATA_VOLUMES = "data_volumes"
    LOCALBOOT = "localboot"
    SANBOOT = "sanboot"


class OperationSystemType(str, Enum):
    LINUX = "linux"
    WINDOWS = "windows"


class StorageProtocol(str, Enum):
    ISCSI = "iscsi"
    NVME = "nvme"


class EBSVolumeType(str, Enum):
    GP2 = "gp2"
    GP3 = "gp3"
    IO1 = "io1"
    IO2 = "io2"
    SC1 = "sc1"
    ST1 = "st1"
    STANDARD = "standard"


class OutpostHardwareType(str, Enum):
    # Valid values: https://docs.aws.amazon.com/outposts/latest/APIReference/API_Outpost.html#outposts-Type-Outpost-SupportedHardwareType
    RACK = "RACK"
    SERVER = "SERVER"
