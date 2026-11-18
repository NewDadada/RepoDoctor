"""Offline unit tests for the tool layer.

Nothing here touches the network or an API key: clone_repo is only inspected
for its schema, while read_file / search_code run against tmp_path trees.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from repo_doctor.tools import build_tools
from repo_doctor.tools.fs import CloneArgs


@pytest.fixture()
def tools() -> dict:
    return build_tools("./workspace")


def test_registry_exposes_expected_tools(tools):
    assert set(tools) == {"clone_repo", "read_file", "search_code"}


def test_tool_schemas_are_openai_compatible(tools):
    for tool in tools.values():
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] == tool.name
        assert function["description"]
        assert function["parameters"]["type"] == "object"
        assert function["parameters"]["required"]


def test_read_file_returns_requested_slice(tools, tmp_path):
    target = tmp_path / "sample.py"
    target.write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")

    result = tools["read_file"].run(str(target), start=3, end=5)

    assert result.ok
    assert result.data["total_lines"] == 10
    assert result.data["content"] == "line3\nline4\nline5"


def test_read_file_missing_path_suggests_exploring(tools, tmp_path):
    result = tools["read_file"].run(str(tmp_path / "nope.py"))

    assert not result.ok
    assert "no file" in result.error.lower()
    assert result.hint


def test_search_code_lists_matches_per_file(tools, tmp_path):
    for i in range(3):
        (tmp_path / f"mod{i}.py").write_text("raise HTTPError()\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("raise HTTPError()\n", encoding="utf-8")

    result = tools["search_code"].run(str(tmp_path), "HTTPError")

    assert result.ok
    assert result.data["count"] == 3
    assert {Path(hit["path"]).name for hit in result.data["hits"]} == {
        "mod0.py",
        "mod1.py",
        "mod2.py",
    }


def test_search_code_rejects_invalid_regex(tools, tmp_path):
    result = tools["search_code"].run(str(tmp_path), "[")

    assert not result.ok
    assert "bad regex" in result.error.lower()


def test_clone_args_require_repo_url():
    with pytest.raises(ValidationError):
        CloneArgs()

    args = CloneArgs(repo_url="https://github.com/psf/requests.git", ref="main")
    assert args.repo_url.endswith(".git")
