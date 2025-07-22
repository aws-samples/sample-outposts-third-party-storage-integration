"""
Configuration management for the launch wizard.
"""


class Config:
    """
    Configuration settings for the launch wizard.
    """

    def __init__(self):
        self.assume_yes: bool = False


# Global configuration instance
global_config = Config()
