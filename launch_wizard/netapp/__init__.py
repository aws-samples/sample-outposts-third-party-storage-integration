import typer

from launch_wizard.netapp.iscsi import iscsi
from launch_wizard.netapp.nvme import nvme

netapp_app = typer.Typer()
netapp_app.command()(iscsi)
netapp_app.command()(nvme)
