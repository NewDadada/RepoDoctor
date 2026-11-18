"""Packaging metadata stays in sync with the code."""

import re
import sys
from pathlib import Path

import repo_doctor

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def read_pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_package_exposes_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", repo_doctor.__version__)


def test_version_matches_pyproject():
    metadata = read_pyproject()
    assert repo_doctor.__version__ == metadata["project"]["version"]


def test_license_is_declared_and_shipped():
    metadata = read_pyproject()
    assert metadata["project"]["license"] == "MIT"
    assert metadata["project"]["license-files"] == ["LICENSE"]
    assert (ROOT / "LICENSE").is_file()
