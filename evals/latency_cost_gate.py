"""
Latency and token-cost gate — measures P95/P99 latency and average token usage
across a sample of representative prompts.
"""
import json
import os
import statistics
import time
from typing import Any

import anthropic

SAMPLE_PROMPTS = [
    "What is the capital of France?",
    "Summarize the key steps in a CI/CD pipeline for AI agents.",
    "Write a Python function that reverses a list.",
    "Explain the difference between RAG and fine-tuning.",
    "What are the OWASP Top 10 security risks?",
    "How does canary deployment work?",
    "Give me three tips for prompt engineering.",
    "What is the purpose of an HPA in Kubernetes?",
    "Explain how ArgoCD implements GitOps.",
    "What metrics should I monitor for an LLM in production?",
]


def _call_agent_timed(prompt: str, base_url: str | None) -> tuple[float, int]:
    """Returns (latency_ms, total_tokens)."""
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=base_url,
    )
    start = time.monotonic()
    response = client.messages.create(
        model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    elapsed_ms = (time.monotonic() - start) * 1000
    total_tokens = response.usage.input_tokens + response.usage.output_tokens
    return elapsed_ms, total_tokens


def run_latency_cost_gate(
    thresholds: dict,
    mode: str = "ci",
    base_url: str | None = None,
    sample_rate: float = 1.0,
    n_samples: int = 10,
) -> dict[str, Any]:
    samples = SAMPLE_PROMPTS[:max(1, int(n_samples * sample_rate))]
    latencies = []
    token_counts = []

    for i, prompt in enumerate(samples):
        latency_ms, tokens = _call_agent_timed(prompt, base_url)
        latencies.append(latency_ms)
        token_counts.append(tokens)
        print(f"  [{i+1}/{len(samples)}] {latency_ms:.0f}ms, {tokens} tokens: {prompt[:50]}...")

    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)
    p95 = latencies_sorted[int(n * 0.95)] if n >= 20 else max(latencies_sorted)
    p99 = latencies_sorted[int(n * 0.99)] if n >= 100 else max(latencies_sorted)
    avg_latency = statistics.mean(latencies)
    avg_tokens = statistics.mean(token_counts)

    lat_thresh = thresholds["latency"]
    cost_thresh = thresholds["token_cost"]

    return {
        "p95_ms": p95,
        "p99_ms": p99,
        "avg_latency_ms": avg_latency,
        "avg_tokens": avg_tokens,
        "max_latency_ms": max(latencies),
        "latency_gate_passed": p95 <= lat_thresh["p95_ms"] and p99 <= lat_thresh["p99_ms"],
        "cost_gate_passed": avg_tokens <= cost_thresh["max_avg_tokens"],
        "samples": len(samples),
    }
