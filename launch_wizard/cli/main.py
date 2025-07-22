"""
Main CLI application setup and configuration.
"""

import typer
from rich.console import Console

from launch_wizard.cli.commands import main_command
from launch_wizard.vendors.generic import generic_app
from launch_wizard.vendors.netapp import netapp_app
from launch_wizard.vendors.purestorage import purestorage_app

console = Console()


def create_app() -> typer.Typer:
    """
    Create and configure the main Typer application.
    """

    cli_app = typer.Typer(
        name="launch_wizard",
        help="Launch EC2 instances with external storage arrays on AWS Outposts",
        no_args_is_help=True,
    )

    # Add the main command callback
    cli_app.callback()(main_command)

    # Add vendor-specific sub-commands
    cli_app.add_typer(generic_app, name="generic", help="Generic storage array integration")
    cli_app.add_typer(netapp_app, name="netapp", help="NetApp storage array integration")
    cli_app.add_typer(purestorage_app, name="purestorage", help="Pure Storage array integration")

    return cli_app


# Create the main application instance
app = create_app()
