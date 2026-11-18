"""
Repo Doctor Eval Runner

用法:
    python scripts/eval.py                          # 跑所有 case
    python scripts/eval.py case_01 case_02          # 只跑指定 case
    python scripts/eval.py --verbose                # 打印每步详情
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

# 把 src 加进 path，否则 import repo_doctor 会失败
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from repo_doctor.config import settings
from repo_doctor.tools import build_tools
from repo_doctor.orchestrator import run_agent


# ========== 第 1 段：加载 case ==========

def load_cases(case_ids: list[str] | None = None) -> list[dict]:
    """从 tests/eval_cases/ 读所有 JSON，可按 id 过滤。"""
    case_dir = Path(__file__).parent.parent / "tests" / "eval_cases"
    if not case_dir.exists():
        raise FileNotFoundError(f"case 目录不存在: {case_dir}")

    cases = []
    for f in sorted(case_dir.glob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        if case_ids and case["id"] not in case_ids:
            continue
        cases.append(case)

    if not cases:
        raise ValueError(f"没找到任何 case，检查 {case_dir}")
    return cases


# ========== 第 2 段：判定成功 ==========

def judge_success(state, criteria: dict) -> tuple[bool, str]:
    """
    返回 (是否成功, 失败原因)。
    成功 = 所有判据都满足。
    """
    # 判据 1：步数范围
    n_steps = len(state.steps)
    min_steps = criteria.get("min_steps", 1)
    max_steps = criteria.get("max_steps", settings.max_steps)

    if n_steps < min_steps:
        return False, f"步数太少 ({n_steps} < {min_steps})，可能没探索直接答"
    if n_steps > max_steps:
        return False, f"步数太多 ({n_steps} > {max_steps})，可能陷入循环"

    # 判据 2：最终答案存在
    if not state.final_answer:
        return False, "没有 final_answer（可能 max_steps 耗尽）"

    # 判据 3：关键词必须全部包含
    answer_lower = state.final_answer.lower()
    keywords = criteria.get("final_answer_contains", [])
    missing = [kw for kw in keywords if kw.lower() not in answer_lower]
    if missing:
        return False, f"final_answer 缺少关键词: {missing}"

    return True, ""


# ========== 第 3 段：跑单个 case ==========

def run_case(case: dict, verbose: bool = False) -> dict:
    """跑一个 case，返回结构化结果。"""
    case_id = case["id"]
    print(f"\n{'='*60}")
    print(f"[{case_id}] {case['goal'][:80]}")
    print(f"{'='*60}")

    tools = build_tools(settings.workspace_dir)

    t0 = time.time()
    try:
        state = run_agent(
            goal=case["goal"],
            repo_url=case["repo_url"],
            workspace=settings.workspace_dir,
            tools=tools,
        )
        elapsed = time.time() - t0
        success, reason = judge_success(state, case.get("success_criteria", {}))
    except Exception as e:
        elapsed = time.time() - t0
        state = None
        success, reason = False, f"异常: {type(e).__name__}: {e}"

    # 打印结果
    status = "PASS" if success else "FAIL"
    print(f"\n{status}", end="")
    if state:
        print(f" | steps={len(state.steps)} | time={elapsed:.1f}s")
    else:
        print(f" | time={elapsed:.1f}s")

    if not success:
        print(f"   原因: {reason}")

    # verbose：打印每一步
    if verbose and state:
        for i, step in enumerate(state.steps, 1):
            print(f"\n  [{i}] tool={step.tool}")
            print(f"      thought: {step.thought[:100]}")
            if step.args:
                print(f"      args: {str(step.args)[:150]}")
            if step.result:
                ok = step.result.get("ok")
                print(f"      result.ok: {ok}")
        print(f"\n  final_answer: {(state.final_answer or '')[:300]}")

    return {
        "id": case_id,
        "success": success,
        "reason": reason,
        "steps": len(state.steps) if state else 0,
        "elapsed_sec": round(elapsed, 1),
        "final_answer": (state.final_answer if state else None),
    }


# ========== 第 4 段：汇总 + 存盘 ==========

def summarize(results: list[dict]) -> dict:
    """算成功率、平均步数、平均耗时。"""
    total = len(results)
    passed = sum(r["success"] for r in results)
    return {
        "total": total,
        "passed": passed,
        "success_rate": round(passed / total, 3) if total else 0,
        "avg_steps": round(sum(r["steps"] for r in results) / total, 1) if total else 0,
        "avg_time_sec": round(sum(r["elapsed_sec"] for r in results) / total, 1) if total else 0,
    }


def save_results(results: list[dict], summary: dict):
    """存到 eval_results/时间戳.json，方便对比历史。"""
    out_dir = Path(__file__).parent.parent / "eval_results"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_file = out_dir / f"{ts}.json"

    payload = {
        "timestamp": ts,
        "model": settings.model,
        "summary": summary,
        "results": results,
    }
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n结果已存: {out_file}")


# ========== 第 5 段：主入口 ==========

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case_ids", nargs="*", help="只跑指定 case id")
    parser.add_argument("--verbose", "-v", action="store_true", help="打印每步详情")
    args = parser.parse_args()

    cases = load_cases(args.case_ids or None)
    print(f"加载 {len(cases)} 个 case，模型: {settings.model}")

    results = []
    for case in cases:
        results.append(run_case(case, verbose=args.verbose))

    summary = summarize(results)
    print(f"\n{'='*60}")
    print("汇总")
    print(f"{'='*60}")
    print(f"成功率:    {summary['passed']}/{summary['total']} ({summary['success_rate']*100:.0f}%)")
    print(f"平均步数:  {summary['avg_steps']}")
    print(f"平均耗时:  {summary['avg_time_sec']}s")

    # 失败列表
    failed = [r for r in results if not r["success"]]
    if failed:
        print(f"\n失败 case:")
        for r in failed:
            print(f"  - {r['id']}: {r['reason']}")

    save_results(results, summary)


if __name__ == "__main__":
    main()