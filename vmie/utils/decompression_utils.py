"""Decompression utility functions for VM Import/Export operations."""

import lzma
import subprocess
from pathlib import Path

from rich.rule import Rule

from vmie.common import (
    COMPRESSED_EXTENSIONS,
    ERR_FILE_DECOMPRESS_BZ2_FAILED,
    ERR_FILE_DECOMPRESS_FAILED,
    ERR_FILE_DECOMPRESS_GZ_FAILED,
    ERR_FILE_UNSUPPORTED_COMPRESSION,
    LogLevel,
)
from vmie.utils.logging_utils import error_and_exit, log_message


def decompress_file(compressed_path: Path, decompressed_path: Path) -> Path:
    """Decompress a compressed file."""
    try:
        log_message(LogLevel.INFO, f"Decompressing file: {compressed_path.name}")

        if compressed_path.name.lower().endswith(".xz"):
            _decompress_xz(compressed_path, decompressed_path)
        elif compressed_path.name.lower().endswith(".gz"):
            _decompress_gz(compressed_path, decompressed_path)
        elif compressed_path.name.lower().endswith(".bz2"):
            _decompress_bz2(compressed_path, decompressed_path)
        else:
            error_and_exit(
                f"Unsupported compression format: {compressed_path}",
                "Supported formats: .gz, .bz2, .xz",
                code=ERR_FILE_UNSUPPORTED_COMPRESSION,
            )

        log_message(LogLevel.SUCCESS, f"Decompression completed successfully: {decompressed_path}")
        return decompressed_path

    except Exception as e:
        error_and_exit(
            "Failed to decompress file",
            Rule(),
            str(e),
            code=ERR_FILE_DECOMPRESS_FAILED,
        )


def get_decompressed_path(compressed_path: Path, target_dir: Path) -> Path:
    """Provides the decompressed path from a compressed file and a target directory."""
    decompressed_name = get_decompressed_filename(compressed_path.name)
    return target_dir / decompressed_name


def is_compressed_file(filename: str) -> bool:
    """Check if file is compressed based on extension."""
    filename_lower = filename.lower()
    return any(filename_lower.endswith(ext) for ext in COMPRESSED_EXTENSIONS)


def get_decompressed_filename(filename: str) -> str:
    """Get the decompressed filename by removing compression extension."""
    filename_lower = filename.lower()
    for ext in COMPRESSED_EXTENSIONS:
        if filename_lower.endswith(ext):
            return filename[: -len(ext)]
    return filename


def _decompress_xz(input_path: Path, output_path: Path) -> None:
    """Decompress XZ file."""
    with lzma.open(input_path, "rb") as compressed_file:
        with open(output_path, "wb") as decompressed_file:
            # Read and write in chunks to handle large files
            while True:
                chunk = compressed_file.read(8192)
                if not chunk:
                    break
                decompressed_file.write(chunk)


def _decompress_gz(input_path: Path, output_path: Path) -> None:
    """Decompress GZ file using gunzip."""
    try:
        with open(output_path, "wb") as output_file:
            subprocess.run(["gunzip", "-c", str(input_path)], stdout=output_file, check=True)
    except subprocess.CalledProcessError as e:
        error_and_exit(
            "Failed to decompress gzip file",
            Rule(),
            str(e),
            code=ERR_FILE_DECOMPRESS_GZ_FAILED,
        )


def _decompress_bz2(input_path: Path, output_path: Path) -> None:
    """Decompress BZ2 file using bunzip2."""
    try:
        with open(output_path, "wb") as output_file:
            subprocess.run(["bunzip2", "-c", str(input_path)], stdout=output_file, check=True)
    except subprocess.CalledProcessError as e:
        error_and_exit(
            "Failed to decompress bzip2 file",
            Rule(),
            str(e),
            code=ERR_FILE_DECOMPRESS_BZ2_FAILED,
        )
