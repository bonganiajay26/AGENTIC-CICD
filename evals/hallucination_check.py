"""
Hallucination detection — uses a judge model to flag factual claims not grounded
in context or verifiable knowledge.
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


def _detect_hallucination(
    prompt: str,
    response: str,
    ground_truth: str,
    judge_model: str,
) -> bool:
    """Returns True if hallucination is detected."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    judge_prompt = f"""You are a factual accuracy evaluator. Determine if the response contains any hallucinated (fabricated or incorrect) factual claims not supported by the ground truth.

Question: {prompt}
Ground truth: {ground_truth}
Response to evaluate: {response}

Does the response contain hallucinated claims? Reply ONLY with "YES" (contains hallucination) or "NO" (no hallucination)."""

    resp = client.messages.create(
        model=judge_model,
        max_tokens=10,
        messages=[{"role": "user", "content": judge_prompt}],
    )
    return resp.content[0].text.strip().upper() == "YES"


def run_hallucination_check(
    dataset_path: str,
    judge_model: str = "claude-sonnet-4-6",
    mode: str = "ci",
    base_url: str | None = None,
    sample_rate: float = 1.0,
) -> dict[str, Any]:
    dataset = _load_dataset(dataset_path, sample_rate)
    hallucinated = 0
    hallucinated_cases = []

    for i, case in enumerate(dataset):
        response = _call_agent(case["prompt"], base_url)
        ground_truth = case.get("ground_truth", case.get("expected_answer", ""))
        is_hallucination = _detect_hallucination(case["prompt"], response, ground_truth, judge_model)
        if is_hallucination:
            hallucinated += 1
            hallucinated_cases.append({
                "prompt": case["prompt"],
                "response": response[:200],
                "ground_truth": ground_truth[:200],
            })
        print(f"  [{i+1}/{len(dataset)}] {'HALLUCINATION' if is_hallucination else 'OK'}: {case['prompt'][:60]}...")

    rate = hallucinated / len(dataset) if dataset else 0.0
    return {
        "hallucination_rate": rate,
        "hallucinated": hallucinated,
        "total": len(dataset),
        "details": {"hallucinated_cases": hallucinated_cases[:5]},
    }
