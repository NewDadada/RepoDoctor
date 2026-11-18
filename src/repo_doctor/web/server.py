"""Local, dependency-free web UI for Repo Doctor.

The server exposes a tiny JSON + Server-Sent-Events API and serves a static
single-page app.  It is intentionally built on ``http.server`` so the UI works
without adding FastAPI/uvicorn to the core dependency list.

Endpoints
---------
``GET  /``                 single-page UI
``GET  /api/info``         model / workspace / sample repositories
``POST /api/run``          start a run, stream progress as SSE
``POST /api/cancel``       ask a running task to stop
``GET  /api/health``       liveness probe
"""

from __future__ import annotations

import argparse
import errno
import json
import mimetypes
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEFAULT_PORT = 8765
STATIC_DIR = (Path(__file__).resolve().parent / "static").resolve()
MAX_BODY_BYTES = 1_000_000
MAX_STEPS_LIMIT = 30

SAMPLES = [
    {"label": "psf/requests", "url": "https://github.com/psf/requests"},
    {"label": "pallets/flask", "url": "https://github.com/pallets/flask"},
    {"label": "fastapi/fastapi", "url": "https://github.com/fastapi/fastapi"},
    {"label": "tiangolo/typer", "url": "https://github.com/tiangolo/typer"},
]

DEFAULT_GOAL = "找出一个具体的 bug、TODO 或过期接口，引用相关代码并给出修复建议。"

_REPO_SHORT = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_RUN_ID = re.compile(r"[^A-Za-z0-9_-]")

_RUNS: dict[str, threading.Event] = {}
_RUNS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class ClientGone(Exception):
    """Raised when the browser closes an SSE connection."""


def project_root() -> Path | None:
    """Best-effort lookup of the checkout root (used so ``.env`` is found)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def normalize_repo_url(value: Any) -> str:
    """Accept ``owner/repo``, ``github.com/owner/repo`` or a full https URL."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("请填写仓库地址")
    if len(raw) > 500:
        raise ValueError("仓库地址过长")

    if raw.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(raw)
        if not parsed.netloc:
            raise ValueError("仓库地址缺少域名")
        return raw.rstrip("/")

    if raw.startswith("git@github.com:"):
        raw = "https://github.com/" + raw.split(":", 1)[1]
        return raw.rstrip("/").removesuffix(".git")

    if raw.startswith("github.com/"):
        return "https://" + raw.rstrip("/")

    if _REPO_SHORT.fullmatch(raw):
        return "https://github.com/" + raw

    raise ValueError("仓库地址格式不对，支持 https://github.com/owner/repo 或 owner/repo")


def _clip(value: Any, limit: int = 2000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "…"


def _short_obj(value: Any, limit: int = 1200, depth: int = 0) -> Any:
    """Recursively trim strings so one tool result cannot flood the browser."""
    if depth > 4:
        return "…"
    if isinstance(value, str):
        return _clip(value, limit)
    if isinstance(value, dict):
        return {str(k): _short_obj(v, limit, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        return [_short_obj(v, limit, depth + 1) for v in list(value)[:60]]
    return value


def _display_path(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        path = Path(text).resolve()
        cwd = Path.cwd().resolve()
        if path.is_relative_to(cwd):
            return path.relative_to(cwd).as_posix()
        return path.as_posix()
    except (OSError, ValueError):
        return text


def serialize_step(number: int, step: Any) -> dict:
    """Turn a ``Step`` into the compact JSON shape consumed by the UI."""
    result = step.result if isinstance(step.result, dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    tool = step.tool or "unknown"
    ok = bool(result.get("ok"))

    payload: dict[str, Any] = {
        "step": number,
        "tool": tool,
        "thought": _clip(step.thought, 3000),
        "args": _short_obj(step.args, 800),
        "ok": ok,
        "error": _clip(result.get("error"), 1200),
        "hint": _clip(result.get("hint"), 600),
        "duration_ms": int(getattr(step, "duration_ms", 0) or 0),
    }

    if tool == "read_file" and ok:
        content = str(data.get("content") or "")
        payload["data"] = {
            "path": _display_path(data.get("path")),
            "start": data.get("start", 1),
            "total_lines": data.get("total_lines"),
            "content": content[:16000],
            "truncated": len(content) > 16000,
        }
    elif tool == "search_code" and ok:
        hits = data.get("hits") if isinstance(data.get("hits"), list) else []
        payload["data"] = {
            "count": data.get("count", len(hits)),
            "hits": [
                {
                    "path": _display_path(hit.get("path")),
                    "line": hit.get("line"),
                    "text": _clip(hit.get("text"), 400),
                }
                for hit in hits[:50]
                if isinstance(hit, dict)
            ],
        }
    elif tool == "clone_repo" and ok:
        payload["data"] = {
            "path": _display_path(data.get("path")),
            "cached": bool(data.get("cached")),
        }
    elif tool == "list_files" and ok:
        entries = data.get("entries") if isinstance(data.get("entries"), list) else []
        payload["data"] = {
            "path": _display_path(data.get("path")),
            "count": data.get("count", len(entries)),
            "entries": [_clip(entry, 300) for entry in entries[:200] if isinstance(entry, str)],
            "truncated": bool(data.get("truncated")) or len(entries) > 200,
        }
    else:
        payload["data"] = _short_obj(data, 800)

    return payload


def _sse_frame(event: str, payload: Any) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


class EventStream:
    """Thread-safe SSE writer with a heartbeat for long model calls."""

    def __init__(self, handler: BaseHTTPRequestHandler):
        self.handler = handler
        self._lock = threading.Lock()
        self._closed = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start_heartbeat(self, interval: float = 12.0) -> None:
        def beat() -> None:
            while not self._stop.wait(interval):
                try:
                    self.comment("keep-alive")
                except ClientGone:
                    return

        self._thread = threading.Thread(target=beat, name="rd-sse-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _write(self, data: bytes) -> None:
        with self._lock:
            if self._closed:
                raise ClientGone
            try:
                self.handler.wfile.write(data)
                self.handler.wfile.flush()
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError, ValueError) as exc:
                self._closed = True
                raise ClientGone from exc

    def send(self, event: str, payload: Any) -> None:
        self._write(_sse_frame(event, payload))

    def comment(self, text: str = "ping") -> None:
        self._write(f": {text}\n\n".encode("utf-8"))


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "RepoDoctorUI/1.1"
    protocol_version = "HTTP/1.1"

    # -- logging ---------------------------------------------------------

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        if self.path.startswith("/api/") or str(code).startswith(("4", "5")):
            sys.stderr.write(f"[web] {self.command} {self.path} -> {code}\n")

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        pass

    def log_error(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[web] " + (fmt % args) + "\n")

    # -- responses -------------------------------------------------------

    def _send_json(self, status: int, payload: Any, close: bool = False) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if close:
            # An unread request body would otherwise reset the connection.
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _send_bytes(
        self,
        data: bytes,
        content_type: str,
        status: int = 200,
        cache: str = "no-cache",
        csp: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        if csp:
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                "frame-ancestors 'none'",
            )
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    # -- routing ---------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_file("index.html", csp=True)
            return
        if path.startswith("/static/"):
            self._serve_file(urllib.parse.unquote(path[len("/static/") :]))
            return
        if path == "/api/info":
            self._handle_info()
            return
        if path == "/api/health":
            self._send_json(200, {"ok": True})
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/run":
            self._handle_run()
            return
        if path == "/api/cancel":
            self._handle_cancel()
            return
        self._send_json(404, {"error": "not found"})

    def _serve_file(self, rel: str, csp: bool = False) -> None:
        candidate = (STATIC_DIR / rel).resolve()
        if candidate == STATIC_DIR or not candidate.is_relative_to(STATIC_DIR) or not candidate.is_file():
            self._send_json(404, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in (
            "application/javascript",
            "application/json",
            "image/svg+xml",
        ):
            content_type += "; charset=utf-8"
        try:
            data = candidate.read_bytes()
        except OSError:
            self._send_json(500, {"error": "cannot read asset"})
            return
        self._send_bytes(data, content_type, csp=csp)

    def _reject_cross_origin(self) -> bool:
        """Block drive-by POSTs from other websites to the local server."""
        origin = self.headers.get("Origin")
        if not origin:
            return False
        host = self.headers.get("Host") or ""
        try:
            same_origin = urllib.parse.urlparse(origin).netloc == host
        except ValueError:
            same_origin = False
        if same_origin:
            return False
        self._discard_body()
        self._send_json(403, {"error": "拒绝跨站请求"}, close=True)
        return True

    def _discard_body(self) -> None:
        """Consume an unread request body so the socket can close cleanly."""
        try:
            remaining = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            remaining = 0
        remaining = min(max(remaining, 0), MAX_BODY_BYTES)
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            remaining -= len(chunk)

    def _read_json(self) -> dict | None:
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            self._send_json(415, {"error": "Content-Type 必须是 application/json"})
            return None
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "无效的 Content-Length"})
            return None
        if length <= 0:
            self._send_json(400, {"error": "请求体为空"})
            return None
        if length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "请求体过大"})
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": "请求体不是合法 JSON"})
            return None
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "请求体必须是 JSON 对象"})
            return None
        return payload

    # -- API -------------------------------------------------------------

    def _handle_info(self) -> None:
        from .. import __version__
        from ..config import settings

        self._send_json(
            200,
            {
                "version": __version__,
                "model": settings.model,
                "max_steps": settings.max_steps,
                "workspace": _display_path(settings.workspace_dir),
                "has_key": bool((settings.deepseek_api_key or "").strip()),
                "default_goal": DEFAULT_GOAL,
                "samples": SAMPLES,
            },
        )

    def _handle_cancel(self) -> None:
        if self._reject_cross_origin():
            return
        payload = self._read_json()
        if payload is None:
            return
        run_id = _RUN_ID.sub("", str(payload.get("run_id") or ""))[:80]
        with _RUNS_LOCK:
            cancel = _RUNS.get(run_id)
        if cancel is None:
            self._send_json(200, {"ok": False, "reason": "run not found"})
            return
        cancel.set()
        self._send_json(200, {"ok": True})

    def _handle_run(self) -> None:
        from ..config import settings

        if self._reject_cross_origin():
            return
        payload = self._read_json()
        if payload is None:
            return

        try:
            repo_url = normalize_repo_url(payload.get("repo_url"))
            goal = str(payload.get("goal") or "").strip()
            if not goal:
                raise ValueError("请填写体检目标")
            if len(goal) > 4000:
                raise ValueError("体检目标过长（最多 4000 字）")
            ref = str(payload.get("ref") or "").strip()
            if len(ref) > 200:
                raise ValueError("分支名过长")

            raw_steps = payload.get("max_steps")
            if raw_steps in (None, ""):
                max_steps = settings.max_steps
            else:
                try:
                    max_steps = int(raw_steps)
                except (TypeError, ValueError) as exc:
                    raise ValueError("最大步数必须是整数") from exc
            max_steps = max(1, min(MAX_STEPS_LIMIT, max_steps))
        except (ValueError, TypeError) as exc:
            self._send_json(400, {"error": str(exc) or "参数不合法"})
            return

        if not (settings.deepseek_api_key or "").strip():
            self._send_json(
                400,
                {
                    "error": "尚未配置 API Key",
                    "hint": "请在项目根目录的 .env 中填写 DeepSeek_API_TRAE_study_KEY=sk-...，"
                    "保存后重启本地服务。",
                },
            )
            return

        run_id = _RUN_ID.sub("", str(payload.get("run_id") or ""))[:80] or uuid.uuid4().hex
        cancel = threading.Event()
        with _RUNS_LOCK:
            _RUNS[run_id] = cancel

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True

        stream = EventStream(self)
        stream.start_heartbeat()

        def emit(event: str, data: Any) -> None:
            try:
                stream.send(event, data)
            except ClientGone:
                # The browser went away; stop before spending another model call.
                cancel.set()

        started = time.perf_counter()
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        emit(
            "meta",
            {
                "run_id": run_id,
                "repo_url": repo_url,
                "goal": goal,
                "ref": ref,
                "model": settings.model,
                "max_steps": max_steps,
                "workspace": _display_path(settings.workspace_dir),
                "started_at": started_at,
            },
        )

        try:
            from ..orchestrator import run_agent
            from ..tools import build_tools

            tools = build_tools(settings.workspace_dir)
            state = run_agent(
                goal=goal,
                repo_url=repo_url,
                workspace=settings.workspace_dir,
                tools=tools,
                on_loop=lambda number: emit("thinking", {"step": number}),
                on_step=lambda number, step: emit("step", serialize_step(number, step)),
                should_stop=cancel.is_set,
                max_steps=max_steps,
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000)

            if state.cancelled:
                status = "cancelled"
            elif state.done:
                status = "done"
            else:
                status = "max_steps"

            emit(
                "done",
                {
                    "status": status,
                    "final_answer": state.final_answer,
                    "steps": len(state.steps),
                    "elapsed_ms": elapsed_ms,
                    "cancelled": state.cancelled,
                    "facts": [_clip(fact, 500) for fact in state.facts[-20:]],
                },
            )
        except Exception as exc:  # pragma: no cover - depends on external APIs
            traceback.print_exc()
            emit(
                "error",
                {
                    "type": type(exc).__name__,
                    "message": _clip(exc, 1200),
                    "hint": "完整堆栈已输出到启动服务的终端，请检查 API Key、网络或模型配置。",
                },
            )
        finally:
            stream.stop()
            with _RUNS_LOCK:
                _RUNS.pop(run_id, None)


# ---------------------------------------------------------------------------
# server / CLI
# ---------------------------------------------------------------------------


class RepoDoctorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT, attempts: int = 20) -> RepoDoctorServer:
    last_error: OSError | None = None
    for candidate in range(port, port + attempts):
        try:
            return RepoDoctorServer((host, candidate), Handler)
        except OSError as exc:
            last_error = exc
            if exc.errno in (errno.EADDRINUSE, errno.EACCES):
                continue
            raise
    raise OSError(f"无法绑定 {host}:{port} 附近的端口：{last_error}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Repo Doctor local web UI")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("REPO_DOCTOR_PORT", DEFAULT_PORT)),
        help=f"preferred port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser")
    parser.add_argument("--open", dest="force_open", action="store_true", help="always open a browser")
    args = parser.parse_args(argv)

    root = project_root()
    if root is not None and Path.cwd().resolve() != root:
        os.chdir(root)

    server = make_server(args.host, args.port)
    host, port = server.server_address[0], server.server_address[1]
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browser_host}:{port}"

    try:
        from ..config import settings

        model = settings.model
        workspace = _display_path(settings.workspace_dir)
        has_key = bool((settings.deepseek_api_key or "").strip())
    except Exception:  # pragma: no cover - defensive only
        model, workspace, has_key = "unknown", "./workspace", False

    print("", flush=True)
    print("  Repo Doctor - local web UI", flush=True)
    print(f"  -> {url}", flush=True)
    print(f"  model: {model}   workspace: {workspace}", flush=True)
    if not has_key:
        print("  ! DeepSeek_API_TRAE_study_KEY is not set; add it to .env and restart", flush=True)
    print("  Press Ctrl+C to stop", flush=True)
    print("", flush=True)

    should_open = args.force_open or (not args.no_browser and sys.stdout.isatty())
    if should_open:
        timer = threading.Timer(0.7, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":  # pragma: no cover
    main()
