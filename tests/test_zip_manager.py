import os
import shutil
import tempfile
import zipfile
import pytest
from app.services.zip_manager import ZipManager, ZipValidationError

def test_zip_extraction_and_dockerfile_detection():
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "test.zip")
    extract_dir = os.path.join(temp_dir, "extracted")

    try:
        # Create a valid zip file with Dockerfile
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("app/Dockerfile", "FROM python:3.12-slim\nCMD ['python']\n")
            zf.writestr("app/main.py", "print('hello')\n")

        ZipManager.validate_and_extract_zip(zip_path, extract_dir)
        context_dir, error = ZipManager.find_dockerfile_context(extract_dir)

        assert error is None
        assert context_dir is not None
        assert os.path.exists(os.path.join(context_dir, "Dockerfile"))

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_zip_path_traversal_prevention():
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "malicious.zip")
    extract_dir = os.path.join(temp_dir, "extracted")

    try:
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("../evil.txt", "evil content")

        with pytest.raises(ZipValidationError):
            ZipManager.validate_and_extract_zip(zip_path, extract_dir)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
