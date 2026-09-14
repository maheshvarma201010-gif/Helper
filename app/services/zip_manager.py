import os
import re
import shutil
import zipfile
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

MAX_FILES = 5000
MAX_TOTAL_SIZE = 500 * 1024 * 1024  # 500 MB limit
MAX_SINGLE_FILE_SIZE = 100 * 1024 * 1024  # 100 MB limit

class ZipValidationError(Exception):
    pass

class ZipManager:
    @staticmethod
    def sanitize_project_name(filename: str) -> str:
        # Strip extension
        name = os.path.splitext(os.path.basename(filename))[0]
        # Replace non-alphanumeric chars with hyphen
        name = re.sub(r'[^a-zA-Z0-9_-]', '-', name).strip('-').lower()
        if not name:
            name = f"project-{uuid.uuid4().hex[:6]}"
        return name

    @staticmethod
    def generate_project_id() -> str:
        # Format example: AZF-7F29A1 or AZF7F29A
        suffix = uuid.uuid4().hex[:6].upper()
        return f"AZF-{suffix}"

    @classmethod
    def validate_and_extract_zip(cls, zip_file_path: str, extract_dir: str) -> None:
        if not zipfile.is_zipfile(zip_file_path):
            raise ZipValidationError("Invalid or corrupted ZIP archive.")

        total_size = 0
        file_count = 0

        with zipfile.ZipFile(zip_file_path, 'r') as zf:
            target_path = Path(extract_dir).resolve()

            for member in zf.infolist():
                file_count += 1
                if file_count > MAX_FILES:
                    raise ZipValidationError("ZIP contains too many files (exceeds limit of 5000 files).")

                # Path traversal / Absolute path check
                filename = member.filename
                # Check for path traversal elements
                if filename.startswith("/") or filename.startswith("\\") or ".." in Path(filename).parts:
                    raise ZipValidationError(f"Malicious file path detected in ZIP: {filename}")

                # Calculate extracted path and verify target directory
                extracted_file_path = (target_path / filename).resolve()
                if not str(extracted_file_path).startswith(str(target_path)):
                    raise ZipValidationError(f"Path traversal security violation: {filename}")

                # Check uncompressed size
                total_size += member.file_size
                if member.file_size > MAX_SINGLE_FILE_SIZE:
                    raise ZipValidationError(f"File {filename} exceeds single file size limit.")
                if total_size > MAX_TOTAL_SIZE:
                    raise ZipValidationError("ZIP total extraction size exceeds limit (500 MB).")

            # Perform safe extraction
            for member in zf.infolist():
                filename = member.filename
                extracted_file_path = (target_path / filename).resolve()

                # Check for symlink/external attribute tricks
                # Pythons zipfile does not automatically create symlinks unless instructed,
                # but let's ensure directory creation and file writing are safe.
                if member.is_dir():
                    extracted_file_path.mkdir(parents=True, exist_ok=True)
                else:
                    extracted_file_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as source, open(extracted_file_path, "wb") as target:
                        shutil.copyfileobj(source, target)

    @classmethod
    def find_dockerfile_context(cls, extract_dir: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Returns (build_context_path, error_message)
        If success, build_context_path is returned and error_message is None.
        If error, build_context_path is None and error_message is string.
        """
        base = Path(extract_dir).resolve()

        # Search for all files named Dockerfile or dockerfile (case insensitive)
        dockerfiles = []
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower() == "dockerfile":
                    dockerfiles.append(Path(root) / f)

        if not dockerfiles:
            return None, "❌ Dockerfile not found."

        if len(dockerfiles) == 1:
            context_dir = str(dockerfiles[0].parent)
            return context_dir, None

        # If multiple Dockerfiles found:
        # Check if one is at root and others are nested subdirectories or if they are ambiguous
        root_dockerfile = base / "Dockerfile"
        if root_dockerfile.exists() and len(dockerfiles) > 1:
            # Check if all other dockerfiles are inside node_modules, .git, venv, etc.
            filtered_dockerfiles = [
                d for d in dockerfiles
                if not any(part.startswith(".") or part in ("node_modules", "venv", "__pycache__") for part in d.parts)
            ]
            if len(filtered_dockerfiles) == 1:
                return str(filtered_dockerfiles[0].parent), None

        return None, (
            "⚠️ Multiple Dockerfiles found.\n\n"
            "Please upload a ZIP containing one clear project Dockerfile."
        )

    @classmethod
    def cleanup_dir(cls, directory: str) -> None:
        if directory and os.path.exists(directory):
            try:
                shutil.rmtree(directory)
            except Exception:
                pass
