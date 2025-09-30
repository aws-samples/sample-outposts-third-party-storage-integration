import typer

from launch_wizard.vendors.hpe.iscsi import iscsi
from launch_wizard.vendors.hpe.nvme import nvme

hpe_app = typer.Typer()
hpe_app.command()(iscsi)
hpe_app.command()(nvme)
