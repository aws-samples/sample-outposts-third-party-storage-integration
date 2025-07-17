import typer

from launch_wizard.purestorage.iscsi import iscsi
from launch_wizard.purestorage.nvme import nvme

purestorage_app = typer.Typer()
purestorage_app.command()(iscsi)
purestorage_app.command()(nvme)
