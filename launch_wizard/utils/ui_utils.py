"""
User interface and interaction utility functions.
"""

from typing import Any, Callable, NoReturn, Optional, Union

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


def prompt_with_trim(
    text: str,
    default: Optional[Any] = None,
    hide_input: bool = False,
    confirmation_prompt: Union[bool, str] = False,
    prompt_type: Optional[Any] = None,
    value_proc: Optional[Callable[[str], Any]] = None,
    prompt_suffix: str = ": ",
    show_default: bool = True,
    err: bool = False,
    show_choices: bool = True,
) -> Any:
    """
    Prompt user for input with automatic whitespace trimming.

    This function wraps typer.prompt to automatically strip leading and trailing
    whitespaces from user input, providing a consistent and clean user experience
    across the application.

    Args:
        text: The text to show for the prompt.
        default: The default value to use if no input happens.
        hide_input: If this is set to true then the input value will be hidden.
        confirmation_prompt: Prompt a second time to confirm the value. Can be set
            to a string instead of True to customize the message.
        prompt_type: The type to convert the result to.
        value_proc: If this parameter is provided it's a function that is invoked
            instead of the type conversion to convert a value.
        prompt_suffix: A suffix that should be added to the prompt.
        show_default: Shows or hides the default value in the prompt.
        err: If set to true the file defaults to stderr instead of stdout,
            the same as with echo.
        show_choices: Show or hide choices if the passed type is a Choice.

    Returns:
        The user input with leading and trailing whitespaces stripped if it's a string,
        otherwise returns the original value unchanged.
    """

    result = typer.prompt(
        text=text,
        default=default,
        hide_input=hide_input,
        confirmation_prompt=confirmation_prompt,
        type=prompt_type,
        value_proc=value_proc,
        prompt_suffix=prompt_suffix,
        show_default=show_default,
        err=err,
        show_choices=show_choices,
    )
    if isinstance(result, str):
        return result.strip()
    return result


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
