"""
Pytest fixtures for versed tests.
"""

import json
import pytest
from pathlib import Path


TEST_DIR = Path(__file__).parent
FIXTURES_DIR = TEST_DIR / "fixtures"
DATA_DIR = TEST_DIR.parent / "src" / "versed" / "_data"


@pytest.fixture(scope="session")
def qcf_mapping_path():
    """Path to QCF mapping file."""
    path = DATA_DIR / "qcf_mapping.min.json"
    if not path.exists():
        pytest.skip("QCF mapping file not found")
    return path


@pytest.fixture(scope="session")
def qcf_mapping(qcf_mapping_path):
    """Loaded QCF mapping data."""
    with open(qcf_mapping_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sabon_pdf_path():
    """Path to sabon mojibake test PDF."""
    path = FIXTURES_DIR / "sabon_mojibake.pdf"
    if not path.exists():
        pytest.skip("sabon_mojibake.pdf not found")
    return str(path)
