import typer

from launch_wizard.vendors.generic.iscsi import iscsi
from launch_wizard.vendors.generic.nvme import nvme

generic_app = typer.Typer()
generic_app.command()(iscsi)
generic_app.command()(nvme)
