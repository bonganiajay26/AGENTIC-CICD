"""
Eval orchestrator — runs all AI gate checks and produces a unified report.
Exit code 0 = all gates passed, 1 = one or more failed.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from evals.hallucination_check import run_hallucination_check
from evals.latency_cost_gate import run_latency_cost_gate
from evals.prompt_regression import run_prompt_regression
from evals.rag_eval import run_rag_eval
from evals.safety_check import run_safety_check
from evals.tool_validation import run_tool_validation


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def run_all_evals(config: dict, mode: str, base_url: str | None, sample_rate: float) -> dict:
    thresholds = config["thresholds"]
    datasets = config["datasets"]
    judge_model = config.get("judge_model", "claude-sonnet-4-6")

    checks = []

    print("\n=== Prompt Regression ===")
    pr = run_prompt_regression(
        dataset_path=datasets["prompt_regression"],
        mode=mode,
        base_url=base_url,
        sample_rate=sample_rate,
    )
    checks.append({
        "name": "Prompt Regression",
        "score": pr["score"],
        "threshold": thresholds["prompt_regression"]["min_score"],
        "passed": pr["score"] >= thresholds["prompt_regression"]["min_score"],
        "details": pr.get("details", {}),
    })

    print("\n=== Tool Call Validation ===")
    tv = run_tool_validation(
        dataset_path=datasets["tool_calls"],
        mode=mode,
        base_url=base_url,
        sample_rate=sample_rate,
    )
    checks.append({
        "name": "Tool Call Validation",
        "score": tv["score"],
        "threshold": thresholds["tool_call_validation"]["min_score"],
        "passed": tv["score"] >= thresholds["tool_call_validation"]["min_score"],
        "details": tv.get("details", {}),
    })

    print("\n=== RAG Retrieval Evaluation ===")
    rag = run_rag_eval(
        dataset_path=datasets["rag"],
        mode=mode,
        base_url=base_url,
        sample_rate=sample_rate,
    )
    checks.append({
        "name": "RAG Retrieval",
        "score": rag["score"],
        "threshold": thresholds["rag_retrieval"]["min_score"],
        "passed": rag["score"] >= thresholds["rag_retrieval"]["min_score"],
        "details": rag.get("details", {}),
    })

    print("\n=== Hallucination Check ===")
    hall = run_hallucination_check(
        dataset_path=datasets["prompt_regression"],
        judge_model=judge_model,
        mode=mode,
        base_url=base_url,
        sample_rate=sample_rate,
    )
    hall_rate = hall["hallucination_rate"]
    checks.append({
        "name": "Hallucination Check",
        "score": 1.0 - hall_rate,
        "threshold": 1.0 - thresholds["hallucination"]["max_rate"],
        "passed": hall_rate <= thresholds["hallucination"]["max_rate"],
        "details": hall.get("details", {}),
    })

    print("\n=== Safety Check ===")
    safety = run_safety_check(
        dataset_path=datasets["safety"],
        judge_model=judge_model,
        mode=mode,
        base_url=base_url,
        sample_rate=sample_rate,
    )
    checks.append({
        "name": "Safety Check",
        "score": safety["score"],
        "threshold": thresholds["safety"]["min_score"],
        "passed": safety["score"] >= thresholds["safety"]["min_score"],
        "details": safety.get("details", {}),
    })

    print("\n=== Latency & Token Cost Gate ===")
    lat = run_latency_cost_gate(
        thresholds=thresholds,
        mode=mode,
        base_url=base_url,
        sample_rate=sample_rate,
    )
    checks.append({
        "name": "Latency Gate (P95)",
        "score": lat["p95_ms"],
        "threshold": thresholds["latency"]["p95_ms"],
        "passed": lat["p95_ms"] <= thresholds["latency"]["p95_ms"],
        "details": lat,
    })
    checks.append({
        "name": "Token Cost Gate",
        "score": lat["avg_tokens"],
        "threshold": thresholds["token_cost"]["max_avg_tokens"],
        "passed": lat["avg_tokens"] <= thresholds["token_cost"]["max_avg_tokens"],
        "details": lat,
    })

    overall_passed = all(c["passed"] for c in checks)

    return {
        "overall_passed": overall_passed,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description="Run all AI eval gates")
    parser.add_argument("--config", default="evals/thresholds.yaml")
    parser.add_argument("--output", default="reports/eval-results.json")
    parser.add_argument("--mode", choices=["ci", "staging", "production-canary"], default="ci")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--sample-rate", type=float, default=1.0)
    parser.add_argument("--fail-fast", type=lambda x: x.lower() == "true", default=True)
    args = parser.parse_args()

    config = load_config(args.config)
    results = run_all_evals(config, args.mode, args.base_url, args.sample_rate)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*50}")
    print(f"EVAL RESULT: {'✅ ALL GATES PASSED' if results['overall_passed'] else '❌ GATES FAILED'}")
    print(f"{'='*50}")
    for check in results["checks"]:
        status = "✅" if check["passed"] else "❌"
        print(f"  {status} {check['name']}: {check['score']} (threshold: {check['threshold']})")

    if not results["overall_passed"] and args.fail_fast:
        sys.exit(1)


if __name__ == "__main__":
    main()
