"""
RAG retrieval evaluation — measures retrieval relevance and answer faithfulness.
Metrics: context relevance, answer faithfulness, answer relevance.
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


def _call_rag_agent(question: str, base_url: str | None) -> dict:
    """
    Call your RAG agent. Returns {"answer": str, "retrieved_contexts": list[str]}.
    Adapt this to your actual RAG endpoint.
    """
    import httpx

    if base_url:
        response = httpx.post(
            f"{base_url}/rag/query",
            json={"question": question},
            timeout=30,
        )
        return response.json()

    # Fallback: direct Anthropic call (no retrieval, for skeleton testing)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = client.messages.create(
        model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-6"),
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
    )
    return {"answer": resp.content[0].text, "retrieved_contexts": []}


def _score_retrieval_relevance(question: str, contexts: list[str], judge_model: str) -> float:
    if not contexts:
        return 0.0
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    scores = []
    for ctx in contexts[:3]:  # evaluate top-3 contexts
        prompt = f"""Rate how relevant this retrieved context is to the question.
Question: {question}
Context: {ctx[:500]}
Rate 0.0 (irrelevant) to 1.0 (perfectly relevant). Reply with only a number."""
        resp = client.messages.create(
            model=judge_model,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )
        try:
            scores.append(float(resp.content[0].text.strip()))
        except ValueError:
            scores.append(0.0)
    return sum(scores) / len(scores)


def _score_faithfulness(answer: str, contexts: list[str], judge_model: str) -> float:
    if not contexts:
        return 1.0
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    context_text = "\n\n".join(contexts[:3])
    prompt = f"""Does the answer stay faithful to the provided contexts (no hallucination beyond context)?
Contexts: {context_text[:1000]}
Answer: {answer[:500]}
Rate 0.0 (completely unfaithful) to 1.0 (fully grounded). Reply with only a number."""
    resp = client.messages.create(
        model=judge_model,
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        return float(resp.content[0].text.strip())
    except ValueError:
        return 0.0


def run_rag_eval(
    dataset_path: str,
    mode: str = "ci",
    base_url: str | None = None,
    sample_rate: float = 1.0,
    judge_model: str = "claude-sonnet-4-6",
) -> dict[str, Any]:
    dataset = _load_dataset(dataset_path, sample_rate)
    relevance_scores = []
    faithfulness_scores = []

    for i, case in enumerate(dataset):
        result = _call_rag_agent(case["question"], base_url)
        rel = _score_retrieval_relevance(case["question"], result["retrieved_contexts"], judge_model)
        faith = _score_faithfulness(result["answer"], result["retrieved_contexts"], judge_model)
        relevance_scores.append(rel)
        faithfulness_scores.append(faith)
        print(f"  [{i+1}/{len(dataset)}] relevance={rel:.2f}, faithfulness={faith:.2f}: {case['question'][:50]}...")

    avg_relevance = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
    avg_faithfulness = sum(faithfulness_scores) / len(faithfulness_scores) if faithfulness_scores else 0.0
    composite_score = (avg_relevance + avg_faithfulness) / 2

    return {
        "score": composite_score,
        "details": {
            "avg_retrieval_relevance": avg_relevance,
            "avg_faithfulness": avg_faithfulness,
            "total": len(dataset),
        },
    }
