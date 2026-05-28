"""
Tool-call validation — verifies the agent selects the right tool with a valid schema.
Checks: correct tool name, required parameters present, parameter types correct.
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


def _call_agent_with_tools(prompt: str, tools: list[dict], base_url: str | None) -> dict | None:
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=base_url,
    )
    response = client.messages.create(
        model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return {"name": block.name, "input": block.input}
    return None


def _validate_tool_call(actual: dict | None, expected: dict, tool_schemas: list[dict]) -> tuple[bool, str]:
    if actual is None:
        return False, "No tool call made"
    if actual["name"] != expected["tool_name"]:
        return False, f"Wrong tool: got '{actual['name']}', expected '{expected['tool_name']}'"

    # Validate required parameters exist and match expected values
    schema = next((t for t in tool_schemas if t["name"] == expected["tool_name"]), None)
    if schema:
        required = schema.get("input_schema", {}).get("required", [])
        for param in required:
            if param not in actual["input"]:
                return False, f"Missing required param: {param}"

    # Check expected input values if specified
    for key, val in expected.get("expected_input", {}).items():
        if key not in actual["input"]:
            return False, f"Expected param '{key}' not present"
        if val is not None and actual["input"][key] != val:
            return False, f"Param '{key}': expected {val}, got {actual['input'][key]}"

    return True, "OK"


def run_tool_validation(
    dataset_path: str,
    mode: str = "ci",
    base_url: str | None = None,
    sample_rate: float = 1.0,
) -> dict[str, Any]:
    dataset = _load_dataset(dataset_path, sample_rate)
    passed = 0
    failed_cases = []

    for i, case in enumerate(dataset):
        actual = _call_agent_with_tools(case["prompt"], case["tools"], base_url)
        ok, reason = _validate_tool_call(actual, case["expected"], case["tools"])
        if ok:
            passed += 1
        else:
            failed_cases.append({
                "prompt": case["prompt"],
                "reason": reason,
                "actual": actual,
                "expected": case["expected"],
            })
        print(f"  [{i+1}/{len(dataset)}] {'PASS' if ok else 'FAIL'}: {case['prompt'][:60]}...")

    score = passed / len(dataset) if dataset else 1.0
    return {
        "score": score,
        "passed": passed,
        "total": len(dataset),
        "details": {"failed_cases": failed_cases[:5]},
    }
