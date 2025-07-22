import typer

from launch_wizard.vendors.netapp.iscsi import iscsi
from launch_wizard.vendors.netapp.nvme import nvme

netapp_app = typer.Typer()
netapp_app.command()(iscsi)
netapp_app.command()(nvme)
