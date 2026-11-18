"""Offline tests for the local web UI and its SSE API.

The HTTP server is real, but the agent loop is replaced with a fake so these
tests never touch the network or an API key.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

import repo_doctor.config as config
import repo_doctor.orchestrator as orchestrator
from repo_doctor.state import Step, TaskState
from repo_doctor.web import server as web

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@pytest.fixture()
def live_server():
    server = web.make_server("127.0.0.1", 0, attempts=1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get(base, path):
    with OPENER.open(base + path, timeout=10) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read()


def post_json(base, path, payload):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with OPENER.open(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def parse_sse(body):
    events = []
    for chunk in body.split("\n\n"):
        if not chunk.strip() or chunk.lstrip().startswith(":"):
            continue
        event = "message"
        data = []
        for line in chunk.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip())
        if data:
            events.append((event, json.loads("\n".join(data))))
    return events


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


def test_normalize_repo_url_accepts_common_forms():
    assert web.normalize_repo_url("psf/requests") == "https://github.com/psf/requests"
    assert web.normalize_repo_url("github.com/psf/requests/") == "https://github.com/psf/requests"
    assert web.normalize_repo_url("https://github.com/psf/requests") == "https://github.com/psf/requests"
    assert web.normalize_repo_url("git@github.com:psf/requests.git") == "https://github.com/psf/requests"
    # ".git" used to be stripped with rstrip(), which also ate trailing name chars.
    assert web.normalize_repo_url("git@github.com:owner/testing.git") == "https://github.com/owner/testing"


def test_normalize_repo_url_rejects_garbage():
    for value in ("", "   ", "not a repo", "ftp://example.com/x"):
        with pytest.raises(ValueError):
            web.normalize_repo_url(value)


def test_serialize_step_trims_file_content():
    step = Step(
        thought="read a big file",
        tool="read_file",
        args={"path": "workspace/a.py"},
        result={
            "ok": True,
            "data": {
                "path": "workspace/a.py",
                "start": 1,
                "total_lines": 900,
                "content": "x" * 20_000,
            },
        },
        duration_ms=12,
    )

    payload = web.serialize_step(1, step)

    assert payload["step"] == 1
    assert payload["tool"] == "read_file"
    assert payload["ok"] is True
    assert len(payload["data"]["content"]) == 16_000
    assert payload["data"]["truncated"] is True


def test_serialize_step_keeps_list_files_compact():
    step = Step(
        thought="list the repo layout",
        tool="list_files",
        args={"path": "workspace/requests", "max_depth": 2},
        result={
            "ok": True,
            "data": {
                "path": "workspace/requests",
                "entries": [f"module_{i}.py" for i in range(250)],
                "count": 250,
                "truncated": True,
            },
        },
    )

    payload = web.serialize_step(1, step)

    assert payload["tool"] == "list_files"
    assert payload["data"]["count"] == 250
    assert len(payload["data"]["entries"]) == 200
    assert payload["data"]["truncated"] is True


def test_orchestrator_stops_before_calling_the_model(monkeypatch):
    monkeypatch.setattr(orchestrator.settings, "max_steps", 3)
    calls = []

    def fake_llm(*args, **kwargs):  # pragma: no cover - must not be called
        calls.append(1)
        raise AssertionError("call_llm should not run after cancellation")

    monkeypatch.setattr(orchestrator, "call_llm", fake_llm)

    state = orchestrator.run_agent(
        goal="find a bug",
        repo_url="https://github.com/psf/requests",
        workspace="./workspace",
        tools={},
        should_stop=lambda: True,
    )

    assert state.cancelled is True
    assert state.final_answer is None
    assert calls == []


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


def test_index_and_static_assets_are_served(live_server):
    status, content_type, body = get(live_server, "/")
    assert status == 200
    assert "text/html" in content_type
    assert b"Repo Doctor" in body

    status, content_type, body = get(live_server, "/static/styles.css")
    assert status == 200
    assert "text/css" in content_type
    assert b"--accent" in body


def test_static_path_traversal_is_blocked(live_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(live_server, "/static/%2e%2e/server.py")
    assert exc.value.code == 404


def test_info_endpoint_returns_ui_config(live_server):
    status, content_type, body = get(live_server, "/api/info")
    payload = json.loads(body)

    assert status == 200
    assert "application/json" in content_type
    assert payload["model"]
    assert payload["max_steps"] >= 1
    assert payload["samples"]
    assert "has_key" in payload


def test_run_streams_meta_step_and_done(live_server, monkeypatch):
    monkeypatch.setattr(config.settings, "deepseek_api_key", "test-key")

    def fake_run_agent(
        goal,
        repo_url,
        workspace,
        tools,
        on_loop=None,
        on_step=None,
        should_stop=None,
        max_steps=None,
    ):
        state = TaskState(goal=goal, repo_url=repo_url, workspace=workspace)
        if on_loop:
            on_loop(1)
        step = Step(
            thought="search for the raise site",
            tool="search_code",
            args={"pattern": "HTTPError", "glob": "*.py"},
            result={
                "ok": True,
                "data": {
                    "count": 1,
                    "hits": [
                        {
                            "path": f"{workspace}/requests/models.py",
                            "line": 4,
                            "text": "raise HTTPError()",
                        }
                    ],
                },
            },
            duration_ms=7,
        )
        state.steps.append(step)
        if on_step:
            on_step(1, step)
        state.done = True
        state.final_answer = (
            "FINDING: HTTPError is raised in models.py\n"
            "LOCATION: workspace/requests/models.py:4\n"
            "QUOTE:\n```python\nraise HTTPError()\n```"
        )
        return state

    monkeypatch.setattr(orchestrator, "run_agent", fake_run_agent)

    status, body = post_json(
        live_server,
        "/api/run",
        {"repo_url": "psf/requests", "goal": "find the raise site", "max_steps": 5},
    )

    assert status == 200
    events = parse_sse(body)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert "thinking" in names
    assert "step" in names
    assert names[-1] == "done"

    meta = dict(events)["meta"]
    assert meta["repo_url"] == "https://github.com/psf/requests"
    assert meta["max_steps"] == 5

    step_payload = dict(events)["step"]
    assert step_payload["tool"] == "search_code"
    assert step_payload["data"]["hits"][0]["line"] == 4

    done = dict(events)["done"]
    assert done["status"] == "done"
    assert "HTTPError" in done["final_answer"]
    assert done["steps"] == 1


def test_run_without_api_key_returns_actionable_error(live_server, monkeypatch):
    monkeypatch.setattr(config.settings, "deepseek_api_key", "")

    status, body = post_json(
        live_server,
        "/api/run",
        {"repo_url": "psf/requests", "goal": "find a bug"},
    )
    payload = json.loads(body)

    assert status == 400
    assert "API Key" in payload["error"]
    assert "DeepSeek_API_TRAE_study_KEY" in payload["hint"]


def test_cancel_unknown_run_is_idempotent(live_server):
    status, body = post_json(live_server, "/api/cancel", {"run_id": "does-not-exist"})
    payload = json.loads(body)

    assert status == 200
    assert payload["ok"] is False


def test_cross_origin_post_is_rejected(live_server):
    request = urllib.request.Request(
        live_server + "/api/cancel",
        data=json.dumps({"run_id": "x"}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        OPENER.open(request, timeout=10)

    assert exc.value.code == 403
