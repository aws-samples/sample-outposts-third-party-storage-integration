"""
User interface and interaction utility functions.
"""

from typing import NoReturn

import typer
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from launch_wizard.common.config import global_config


def auto_confirm(message: str) -> bool:
    """
    Auto-confirm a message if assume_yes is set, otherwise prompt the user.

    Args:
        message: The confirmation message to display.

    Returns:
        True if confirmed, False otherwise.
    """

    if global_config.assume_yes:
        typer.echo(f"{message} [auto-yes]")
        return True
    return typer.confirm(message)


def error_and_exit(*parts: RenderableType, code: int) -> NoReturn:
    """
    Display an error message and exit the application.

    Args:
        *parts: Renderable parts to display in the error message.
        code: Exit code to use when exiting.

    Raises:
        typer.Exit: Always raises to exit the application.
    """

    group = Group(*[Text.from_markup(part) if isinstance(part, str) else part for part in parts])
    Console().print(Panel(group, title="Error", style="bold red"))
    raise typer.Exit(code=code)
