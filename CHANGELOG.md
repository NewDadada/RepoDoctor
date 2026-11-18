# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-11-18

### Added

- 本地 Web UI（`repo-doctor-ui` 或 `python scripts/serve.py`）：基于 `http.server` + SSE，
  不引入任何额外运行时依赖；实时展示克隆、浏览、搜索、读取的每一步，支持中途停止、
  深色模式、复制报告与展开代码详情。
- Web API：`GET /api/info`、`GET /api/health`、`POST /api/run`（SSE 流）、`POST /api/cancel`。
- 新增 `list_files` 工具：按层数浏览目录（默认 2 层），自动忽略 `.git`、`__pycache__`、
  虚拟环境、`node_modules` 等噪音目录，最多返回 300 条。
- `tests/test_web.py`：覆盖仓库地址归一化、静态资源、路径穿越防护、SSE 事件流、
  API Key 缺失提示与跨站请求拦截。

### Changed

- `orchestrator.run_agent` 新增 `on_loop` / `on_step` / `should_stop` / `max_steps` 参数，
  CLI、评测脚本与 Web UI 复用同一个循环；`Step` 增加 `duration_ms`。
- `llm.call_llm` 的 OpenAI 客户端改为懒加载，没有 API Key 时也能导入包、启动 Web UI。
- 系统提示词改为「先用 `list_files` 看结构，再用 `search_code` / `read_file`」。

### Fixed

- `read_file` 的失败提示会推荐 `list_files`，但当时并不存在这个工具。
- `clone_repo` 的 `ref` 在 JSON Schema 中被标记为必填，导致模型无法省略分支；现在可选。
- 跨站 POST 被 403 拒绝时没有读取请求体，连接会被重置；现在会读完请求体并主动关闭连接。

## [1.0.0] - 2026-11-18

### Added

- 初始版本：`clone_repo` / `read_file` / `search_code` 工具、带步数上限与重复调用守卫的
  agent 循环、离线评测脚本、MIT 许可证与 GitHub Actions CI（Python 3.10 ~ 3.13）。
