"""Image source processor for VM Import/Export operations."""

from pathlib import Path

import requests  # type: ignore
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.rule import Rule

from vmie.common import ERR_FILE_DOWNLOAD_FAILED, ERR_FILE_PROCESS_FAILED, LogLevel
from vmie.utils import (
    decompress_file,
    error_and_exit,
    extract_filename_from_url,
    format_file_size,
    get_decompressed_path,
    is_compressed_file,
    log_message,
)


class SourceProcessor:
    """Processes VM images from various sources."""

    def __init__(self):
        """Initialize source processor."""

    def download_from_url(self, url: str, output_dir: Path) -> Path:
        """Download image from HTTP/HTTPS URL."""
        try:
            filename = extract_filename_from_url(url)
            output_path = output_dir / filename

            log_message(LogLevel.INFO, f"Downloading image: {filename}")
            log_message(LogLevel.INFO, f"Source URL: {url}")

            # Start download with progress bar
            with requests.get(url, stream=True) as response:
                response.raise_for_status()

                total_size = int(response.headers.get("content-length", 0))

                with Progress(
                    TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
                    BarColumn(bar_width=None),
                    "[progress.percentage]{task.percentage:>3.1f}%",
                    "•",
                    DownloadColumn(),
                    "•",
                    TransferSpeedColumn(),
                    "•",
                    TimeRemainingColumn(),
                ) as progress:
                    task = progress.add_task("download", filename=filename, total=total_size)

                    with open(output_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                progress.update(task, advance=len(chunk))

            log_message(LogLevel.SUCCESS, f"Download completed successfully: {output_path}")

            # Handle compressed files
            if is_compressed_file(filename):
                decompressed_path = get_decompressed_path(output_path, output_path.parent)
                return decompress_file(output_path, decompressed_path)

            return output_path

        except requests.RequestException as e:
            error_and_exit(
                f"Failed to download from URL: {url}",
                f"Network error: {e}",
                "Please check the URL and your internet connection",
                code=ERR_FILE_DOWNLOAD_FAILED,
            )
        except Exception as e:
            error_and_exit(
                f"Failed to download from URL: {url}",
                Rule(),
                str(e),
                code=ERR_FILE_DOWNLOAD_FAILED,
            )

    def process_local_file(self, local_path: str, temp_dir: Path) -> Path:
        """Process local file efficiently - decompress only if needed."""
        try:
            source_path = Path(local_path).resolve()
            file_size = source_path.stat().st_size
            filename = source_path.name

            log_message(LogLevel.INFO, f"Processing local file: {filename}")
            log_message(LogLevel.INFO, f"Source path: {source_path}")
            log_message(LogLevel.INFO, f"File size: {format_file_size(file_size)}")

            # Check if file needs decompression
            if is_compressed_file(filename):
                log_message(LogLevel.INFO, "File is compressed, decompressing to temp directory")
                decompressed_path = get_decompressed_path(source_path, temp_dir)
                return decompress_file(source_path, decompressed_path)
            else:
                log_message(LogLevel.INFO, "File is not compressed, will be uploaded directly")
                # Return the original path - no need to copy uncompressed files
                return source_path

        except Exception as e:
            error_and_exit(
                f"Failed to process local file: {local_path}",
                Rule(),
                str(e),
                code=ERR_FILE_PROCESS_FAILED,
            )
