import typer

from launch_wizard.vendors.dell.iscsi import iscsi
from launch_wizard.vendors.dell.nvme import nvme

dell_app = typer.Typer()
dell_app.command()(iscsi)
dell_app.command()(nvme)
