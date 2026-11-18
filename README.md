# Repo Doctor

[![CI](https://github.com/NewDadada/RepoDoctor/actions/workflows/ci.yml/badge.svg)](https://github.com/NewDadada/RepoDoctor/actions/workflows/ci.yml)

用大模型自动"体检"仓库的轻量 Agent：给定一个 GitHub 仓库，它会克隆代码、检索与阅读文件，
最终定位一个具体问题（bug / TODO / 过期接口），并给出带代码引用的结论。

- 版本：**1.0.0**
- 仓库：<https://github.com/NewDadada/RepoDoctor.git>

## 工作方式

一个带工具调用（function calling）的循环：

```
clone_repo → search_code / read_file → ... → final_answer
```

1. `orchestrator.run_agent` 把目标、已知事实和最近 5 步的观察拼成 messages；
2. 调用模型（默认 DeepSeek，OpenAI 兼容协议），模型要么继续调用工具，要么给出最终答案；
3. 每次工具结果都会写回状态，失败会记成 fact 提醒模型换路子；重复调用同一工具+参数会被拦截；
4. 步数上限由 `MAX_STEPS` 控制，超限时返回兜底答案。

## 目录结构

```
.
├── pyproject.toml              # 项目元数据，版本 1.0.0
├── src/repo_doctor/
│   ├── __init__.py             # __version__ = "1.0.0"
│   ├── config.py               # pydantic-settings 读取 .env
│   ├── llm.py                  # OpenAI 兼容客户端
│   ├── orchestrator.py         # 核心 agent 循环
│   ├── context.py              # 拼装对话消息
│   ├── state.py                # TaskState / Step 数据类
│   ├── trace.py                # 可选的 Langfuse 上报
│   ├── prompts/system.md       # 系统提示词
│   └── tools/                  # clone_repo / read_file / search_code
├── scripts/
│   ├── run.py                  # 单次演示
│   └── eval.py                 # 评测入口
├── tests/
│   ├── eval_cases/             # 评测用例（JSON）
│   ├── test_config.py          # 配置加载（离线）
│   ├── test_tools.py           # 工具层（离线）
│   └── test_version.py         # 版本 / 许可证元数据
├── .github/workflows/ci.yml    # CI：Python 3.10 ~ 3.13
├── LICENSE                     # MIT
└── eval_results/               # 评测结果（本地生成，不入库）
```

## 环境要求

- Python ≥ 3.10
- git 可执行文件在 PATH 中

## 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
```

## 配置

复制 `.env.example` 为 `.env`，填入密钥：

| 变量 | 说明 |
| --- | --- |
| `DeepSeek_API_TRAE_study_KEY` | DeepSeek API Key（`pyproject` 中 `openai` 客户端使用） |
| `OPENAI_API_KEY` | 备用 OpenAI Key |
| `MODEL` | 模型名，默认 `deepseek-chat` |
| `MAX_STEPS` | 单次任务最大步数，默认 15 |
| `WORKSPACE_DIR` | 克隆仓库的落地目录，默认 `./workspace` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | 可选，开启链路追踪 |

> `context.py` 以相对路径读取 `src/repo_doctor/prompts/system.md`，
> 因此请在项目根目录下运行脚本。

## 使用

单次演示：

```bash
python scripts/run.py
```

评测全部用例：

```bash
python scripts/eval.py
```

只跑指定用例、或打印每步详情：

```bash
python scripts/eval.py case_01 case_02
python scripts/eval.py --verbose
```

评测结果会写入 `eval_results/<时间戳>.json`，并在终端打印成功率、平均步数、平均耗时。

## 工具集

| 工具 | 作用 |
| --- | --- |
| `clone_repo` | 浅克隆仓库到 workspace，命中缓存时不重复拉取 |
| `read_file` | 按行切片读取文件（单次最多 500 行） |
| `search_code` | 正则搜索，返回 `file:line`，最多 50 条命中 |

## 测试

```bash
pip install -e ".[dev]"
python -m pytest
```

测试全部离线运行，不需要 API Key：`test_tools.py` 在临时目录上验证 `read_file` / `search_code`，
`test_version.py` 校验包版本、`pyproject.toml` 与 LICENSE 是否一致。
GitHub Actions 在每次 push / PR 时用 Python 3.10 ~ 3.13 各跑一遍（见 `.github/workflows/ci.yml`）。

## 版本

当前发布版本为 **1.0.0**，对应 git tag `v1.0.0`。
版本号在两处维护：`pyproject.toml` 的 `[project].version` 与
`src/repo_doctor/__init__.py` 的 `__version__`。

## 许可证

本项目基于 [MIT License](LICENSE) 发布，版权所有 (c) 2026 NewDadada。
