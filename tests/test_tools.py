"""Offline unit tests for the tool layer.

Nothing here touches the network or an API key: clone_repo is only inspected
for its schema, while read_file / search_code run against tmp_path trees.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from repo_doctor.tools import build_tools
from repo_doctor.tools.fs import CloneArgs


@pytest.fixture()
def tools() -> dict:
    return build_tools("./workspace")


def test_registry_exposes_expected_tools(tools):
    assert set(tools) == {"clone_repo", "list_files", "read_file", "search_code"}


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


def test_clone_args_make_ref_optional():
    args = CloneArgs(repo_url="https://github.com/psf/requests")

    assert args.ref == ""


def _make_tree(root: Path) -> None:
    (root / "a.py").write_text("print(1)\n", encoding="utf-8")
    (root / "notes.md").write_text("# notes\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "stale.pyc").write_bytes(b"0")
    sub = root / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("print(2)\n", encoding="utf-8")
    deep = sub / "deep"
    deep.mkdir()
    (deep / "c.py").write_text("print(3)\n", encoding="utf-8")


def test_list_files_respects_depth_and_ignores_noise(tools, tmp_path):
    _make_tree(tmp_path)

    result = tools["list_files"].run(str(tmp_path), max_depth=2)

    assert result.ok
    entries = result.data["entries"]
    assert {"a.py", "notes.md", "sub/", "sub/b.py", "sub/deep/"} <= set(entries)
    assert "sub/deep/c.py" not in entries
    assert not any(entry.startswith((".git", "__pycache__")) for entry in entries)
    assert result.data["count"] == len(entries)
    assert result.data["truncated"] is False


def test_list_files_filters_files_by_pattern(tools, tmp_path):
    _make_tree(tmp_path)

    result = tools["list_files"].run(str(tmp_path), max_depth=3, pattern="*.py")

    files = [entry for entry in result.data["entries"] if not entry.endswith("/")]
    assert files == ["a.py", "sub/b.py", "sub/deep/c.py"]
    assert "sub/" in result.data["entries"]  # directories are still reported


def test_list_files_truncates_large_directories(tools, tmp_path):
    for i in range(5):
        (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
    tool = tools["list_files"]
    tool.max_entries = 3

    result = tool.run(str(tmp_path))

    assert result.ok
    assert result.data["count"] == 3
    assert result.data["truncated"] is True


def test_list_files_missing_directory_suggests_cloning(tools, tmp_path):
    result = tools["list_files"].run(str(tmp_path / "missing"))

    assert not result.ok
    assert result.hint


def test_clone_repo_creates_missing_workspace_parent(monkeypatch, tmp_path):
    workspace = tmp_path / "fresh" / "workspace"
    tools = build_tools(str(workspace))

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("repo_doctor.tools.fs.subprocess.run", fake_run)

    result = tools["clone_repo"].run("https://github.com/psf/requests")

    assert result.ok
    assert workspace.is_dir()
