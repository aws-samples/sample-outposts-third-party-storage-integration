"""Logging utility functions for VMIE operations."""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, NoReturn, Optional

from rich.console import Console, Group, RenderableType
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.text import Text

from vmie.common import LogLevel

_logger: Optional[logging.Logger] = None
_console = Console()


def get_logger() -> logging.Logger:
    """Get the global VMIE logger instance."""
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger


class VMIELogFileFormatter(logging.Formatter):
    """Custom formatter for VMIE log files"""

    def format(self, record):
        # Create timestamp in ISO format (industry standard)
        record.asctime = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

        # Get the message and remove Rich markup
        message = record.getMessage()
        clean_message = Text.from_markup(message).plain

        # Format the message with proper alignment
        formatted = f"{record.asctime} | {record.levelname:<8} | {clean_message}"
        return formatted


def _setup_file_logging() -> Path:
    """Set up logging configuration and return log file path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"vmie_{timestamp}.log"


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up _console logging configuration.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """

    # Create logger
    logger = logging.getLogger("vmie")
    logger.setLevel(getattr(logging, log_level.upper()))

    # Clear any existing handlers
    logger.handlers.clear()

    # Console handler with Rich for beautiful output
    console_handler = RichHandler(
        console=_console,
        show_time=True,
        omit_repeated_times=False,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
        log_time_format="[%Y-%m-%d %H:%M:%S]",
    )
    console_handler.setLevel(getattr(logging, log_level.upper()))
    logger.addHandler(console_handler)

    # File handler for persistent logging
    log_file = _setup_file_logging()
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # Always log everything to file
    file_handler.setFormatter(VMIELogFileFormatter())
    logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    logger.info(
        f"Log file: {log_file}",
    )

    return logger


def log_message(level: LogLevel, message: str) -> None:
    """
    Log a message.

    Args:
        level: Log level (mapped to standard logging levels)
        message: Message to log
    """
    logger = get_logger()

    # Map custom LogLevel to standard logging levels
    level_mapping = {
        LogLevel.DEBUG: logging.DEBUG,
        LogLevel.INFO: logging.INFO,
        LogLevel.SUCCESS: logging.INFO,  # Map SUCCESS to INFO with special formatting
        LogLevel.WARN: logging.WARNING,
        LogLevel.ERROR: logging.ERROR,
    }

    log_level = level_mapping.get(level, logging.INFO)

    # Special handling for SUCCESS level
    if level == LogLevel.SUCCESS:
        # Use subtle green checkmark for success
        logger.info(f"[bright_green]✓[/bright_green] {message}")
    elif level == LogLevel.ERROR:
        # Use subtle red X for errors
        logger.error(f"[bright_red]✗[/bright_red] {message}")
    elif level == LogLevel.WARN:
        # Use warning symbol for warnings
        logger.warning(f"[yellow]⚠[/yellow] {message}")
    else:
        logger.log(log_level, message)


def log_section(title: str, section_level: int = 1) -> None:
    """
    Log a section header with formatting based on section level.

    Args:
        title: The title of the section
        section_level: Integer indicating the section level (1 for main, 2+ for subsections)
    """
    _console.print(Rule(title, style="blue", characters="─" if section_level == 1 else "-"))


def log_step(step_number: int, total_steps: int, description: str) -> None:
    """Log a step in a multi-step process."""
    logger = get_logger()
    logger.info(f"[bold blue]Step {step_number}/{total_steps}:[/bold blue] {description}")


def error_and_exit(*parts: RenderableType, code: int) -> NoReturn:
    """
    Display an error message and exit the application.

    Args:
        *parts: Renderable parts to display in the error message.
        code: Exit code to use when exiting.
    """
    # Log the error through the logging system first
    logger = get_logger()

    # Process parts, making Rules red
    processed_parts = []
    for part in parts:
        if isinstance(part, Rule):
            # Create a new Rule with red style, preserving other properties
            processed_part = Rule(title=part.title, align=part.align, characters=part.characters, style="red")
        elif isinstance(part, str):
            processed_part = Text.from_markup(part)
            logger.error(f"Fatal error (exit code {code}): {processed_part}")
        else:
            processed_part = part
        processed_parts.append(processed_part)

    # Display rich error panel with styling
    group = Group(*processed_parts)
    _console.print(Panel(group, title="[bold red]Error[/bold red]", border_style="red", padding=(1, 2)))

    # Flush output to ensure error message is displayed
    _console.file.flush()

    # Clean exit
    sys.exit(code)


def wait_with_progress(description: str, check_function, timeout_seconds: int = 3600, check_interval: int = 30) -> bool:
    """
    Wait for a condition with progress display.

    Args:
        description: Base description for the progress display
        check_function: Function that returns:
            - Dict: {"completed": bool, "progress": int, "description": str}
        timeout_seconds: Maximum time to wait
        check_interval: Time between checks

    Returns:
        bool: True if condition was met within timeout, False otherwise
    """
    logger = get_logger()
    logger.info(description)

    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=_console,
        transient=True,
    ) as progress:
        task = progress.add_task(description, total=None)

        while time.time() - start_time < timeout_seconds:
            result = check_function()

            completed = result.get("completed", False)
            progress_percent = result.get("progress", 0)
            progress_desc = result.get("description", description)

            if completed:
                return True

            # Update progress display with percentage and description
            display_desc = f"{progress_desc} ({progress_percent}%)" if progress_percent > 0 else progress_desc
            progress.update(task, description=display_desc)

            time.sleep(check_interval)

    logger.warning(f"[yellow]⚠[/yellow] Timeout: {description} did not complete within {timeout_seconds} seconds")
    return False


def display_summary(title: str, items: Dict) -> None:
    """Display a summary panel with key-value pairs."""
    logger = get_logger()
    logger.info(f"[bold cyan]{title}[/bold cyan]")

    # Log each item with formatting
    for key, value in items.items():
        logger.info(f"  [bold]{key}:[/bold] {value}")

    # Also display as a rich panel for visual appeal
    content = "\n".join([f"[bold]{key}:[/bold] {value}" for key, value in items.items()])
    panel = Panel(content, title=title, border_style="cyan", padding=(1, 2))
    _console.print(panel)
