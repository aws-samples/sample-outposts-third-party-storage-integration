"""
This module defines project-level constants.
"""

from typing import Dict, List

# Default values
INSTANCE_TYPE = "t3.micro"
DEFAULT_INSTANCE_PROFILE = "VMIEInstanceProfile"
DEFAULT_TIMEOUT_MINUTES = 60
IMPORT_TIMEOUT_MINUTES = 60 * 12
EXPORT_TIMEOUT_MINUTES = 60 * 12

# Supported image formats and their extensions
SUPPORTED_FORMATS: Dict[str, List[str]] = {
    "ova": [".ova"],
    "vmdk": [".vmdk"],
    "vhd": [".vhd", ".vhdx"],
    "raw": [".raw", ".img"],
}

# Compressed file extensions
COMPRESSED_EXTENSIONS = [".xz", ".gz", ".bz2"]

# EC2 instance trust policy for SSM access
EC2_TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}

# VM import role and policy
VMIMPORT_ROLE_NAME = "vmimport"
VMIMPORT_TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "vmie.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {"StringEquals": {"sts:Externalid": "vmimport"}},
        }
    ],
}

VMIMPORT_EC2_INLINE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["ec2:ModifySnapshotAttribute", "ec2:CopySnapshot", "ec2:RegisterImage", "ec2:Describe*"],
            "Resource": "*",
        }
    ],
}


def get_vmimport_bucket_inline_policy(bucket_name: str) -> Dict:
    """Generate VM import policy for the specified bucket."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetBucketLocation", "s3:GetObject", "s3:ListBucket", "s3:PutObject", "s3:GetBucketAcl"],
                "Resource": [f"arn:aws:s3:::{bucket_name}", f"arn:aws:s3:::{bucket_name}/*"],
            }
        ],
    }
