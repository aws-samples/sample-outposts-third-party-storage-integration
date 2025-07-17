import typer

from launch_wizard.generic.iscsi import iscsi
from launch_wizard.generic.nvme import nvme

generic_app = typer.Typer()
generic_app.command()(iscsi)
generic_app.command()(nvme)
