"""
Display and formatting utility functions for presenting information to users.

These utilities help format and display data in a consistent, user-friendly manner
using the rich library for enhanced terminal output.
"""

from typing import Any, Dict, List

from rich.console import Console
from rich.markup import escape
from rich.table import Table


def style_var(value: Any, color: str = "cyan") -> str:
    """
    Style a variable for display with rich markup.

    Args:
        value: The value to style.
        color: The color to use for styling. Defaults to "cyan".

    Returns:
        The styled string with rich markup.
    """

    return f"[bold {color}]{escape(str(value))}[/bold {color}]"


def print_table_with_single_column(title: str, items: List[str], column_name: str = "") -> None:
    """
    Draws a table using the rich library with a single column.

    Args:
        title: The title of the table.
        items: A list of strings to be displayed in the table.
        column_name: The name of the column. Defaults to "".
    """

    if not items:
        Console().print(title)
        Console().print("No data to display.")
        return

    table = Table(title=title)
    table.add_column(column_name, style="cyan")
    for item in items:
        table.add_row(item)
    Console().print(table)


def print_table_with_multiple_columns(title: str, data: List[Dict[str, Any]]) -> None:
    """
    Draws a formatted table using the rich library with multiple columns.

    Args:
        title: The title of the table to display at the top.
        data: A list of dictionaries representing rows.
              Each dictionary's keys are column names and values are cell values.
    """

    if not data:
        Console().print(title)
        Console().print("No data to display.")
        return

    # Extract columns from the keys in all rows
    columns = []
    for row in data:
        for key in row.keys():
            if key not in columns:
                columns.append(key)

    table = Table(title=title)

    # Add columns
    for column in columns:
        table.add_column(column, style="cyan")

    # Add rows
    for row in data:
        table.add_row(*(str(row.get(column, "")) for column in columns))

    Console().print(table)
