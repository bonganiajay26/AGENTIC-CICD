"""
Prompt regression testing — compares current agent output against golden baseline answers.
"""
import json
import os
import random
from typing import Any

import anthropic


def _load_dataset(path: str, sample_rate: float) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    if sample_rate < 1.0:
        data = random.sample(data, max(1, int(len(data) * sample_rate)))
    return data


def _call_agent(prompt: str, base_url: str | None) -> str:
    """Call the agent under test. Swap this for your actual agent invocation."""
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=base_url,
    )
    response = client.messages.create(
        model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _judge_response(prompt: str, expected: str, actual: str, judge_model: str) -> bool:
    """Use a judge model to evaluate semantic correctness."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    judge_prompt = f"""You are an evaluator. Given a question and two answers, decide if the actual answer is semantically equivalent to the expected answer.

Question: {prompt}
Expected answer: {expected}
Actual answer: {actual}

Reply with only "PASS" if the actual answer is correct/equivalent, or "FAIL" if it is wrong or missing key information."""

    response = client.messages.create(
        model=judge_model,
        max_tokens=10,
        messages=[{"role": "user", "content": judge_prompt}],
    )
    return response.content[0].text.strip().upper() == "PASS"


def run_prompt_regression(
    dataset_path: str,
    mode: str = "ci",
    base_url: str | None = None,
    sample_rate: float = 1.0,
    judge_model: str = "claude-sonnet-4-6",
) -> dict[str, Any]:
    dataset = _load_dataset(dataset_path, sample_rate)
    passed = 0
    failed_cases = []

    for i, case in enumerate(dataset):
        prompt = case["prompt"]
        expected = case["expected_answer"]
        actual = _call_agent(prompt, base_url)
        ok = _judge_response(prompt, expected, actual, judge_model)
        if ok:
            passed += 1
        else:
            failed_cases.append({"prompt": prompt, "expected": expected, "actual": actual})
        print(f"  [{i+1}/{len(dataset)}] {'PASS' if ok else 'FAIL'}: {prompt[:60]}...")

    score = passed / len(dataset) if dataset else 1.0
    return {
        "score": score,
        "passed": passed,
        "total": len(dataset),
        "details": {"failed_cases": failed_cases[:5]},  # first 5 failures for report
    }
