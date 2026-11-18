import subprocess, os, re, shutil
from pathlib import Path
from pydantic import BaseModel, Field
from .base import Tool, ToolResult


class CloneArgs(BaseModel):
    repo_url: str = Field(..., description="Github rep URL")
    ref: str = Field(..., description="branch or commit")

class CloneRepoTool(Tool):
    name = "clone_repo"
    description = "Clone a git repo into workspace. Returns the local path."
    args_schema = CloneArgs

    def __init__(self, workspace: str):
        self.workspace = workspace

    def run(self, repo_url: str,  ref: str = "") -> ToolResult:
        name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        Path(self.workspace).mkdir(parents=True, exist_ok=True)
        path = Path(self.workspace) / name

        # 只有存在且是有效 git 仓库，才算缓存命中
        if path.exists() and (path / ".git").exists():
            return ToolResult(ok=True, data={"path": str(path), "cached": True})

        # 存在但不是有效仓库（空目录/半成品），先删掉再 clone
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["-b", ref]
        cmd += [repo_url, str(path)]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            shutil.rmtree(path, ignore_errors=True)
            return ToolResult(ok=False, error="git clone timeout (>120s)")

        if r.returncode != 0:
            shutil.rmtree(path, ignore_errors=True)
            return ToolResult(ok=False, error=r.stderr[-500:], hint="check url or branch name")

        return ToolResult(ok=True, data={"path": str(path), "cached": False})


class ReadFileArgs(BaseModel):
    path: str
    start: int = Field(1, ge=1)
    end: int = Field(200, le=500, description="max 500 lines per call")

class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a slice of a file. Always use specify start/end."
    args_schema = ReadFileArgs

    def run(self, path: str, start: int = 1, end: int = 200) -> ToolResult:
        p = Path(path)
        if not p.exists():
            return ToolResult(ok=False, error="There is no file at this path" ,hint="use list_files to explore first")
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        chunk = lines[start-1:end]
        return ToolResult(ok=True, data={"path": path, "start": start, "total_lines": len(lines), "content": "\n".join(chunk),})

class SearchArgs(BaseModel):
    root: str
    pattern: str = Field(..., description="regex")
    glob: str = Field("*.py", description="file glob filter")


class SearchCodeTool(Tool):
    name = "search_code"
    description = "Regex search across files. Returns file:line matches (max 50)."
    args_schema = SearchArgs

    def run(self, root: str, pattern: str, glob: str = "*.py") -> ToolResult:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return ToolResult(ok=False, error=f"bad regex: {e}")
        hits = []
        for f in Path(root).rglob(glob):
            if not f.is_file():
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if rx.search(line):
                    hits.append({"path": str(f), "line": i, "text": line.strip()[:200]})
                    if len(hits) >= 50:
                        break
            if len(hits) >= 50:
                break
        return ToolResult(ok=True, data={"count": len(hits), "hits": hits})