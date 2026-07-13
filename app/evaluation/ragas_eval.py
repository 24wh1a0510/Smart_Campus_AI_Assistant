"""RAGAS metrics: faithfulness, answer relevancy, context precision, context recall.

Runs the RAG pipeline for each test case to build a RAGAS-compatible dataset,
then scores it. Uses the same OpenRouter/GPT-4o-mini + OpenAI-embeddings
setup as the rest of the app via LangChain adapters.
"""
from __future__ import annotations

import numpy as np
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

from app.config.settings import settings
from app.evaluation.test_generator import TestCase
from app.rag.generator import RAGGenerator


def run_ragas_eval(cases: list[TestCase], generator: RAGGenerator | None = None) -> dict:
    generator = generator or RAGGenerator()

    questions, answers, contexts, ground_truths = [], [], [], []
    for case in cases:
        if case.category != "functional":
            continue  # RAGAS needs answerable, KB-grounded cases
        resp = generator.answer(question=case.question, history=[])
        questions.append(case.question)
        answers.append(resp.answer)
        contexts.append([c.text for c in resp.retrieved_chunks] or [""])
        ground_truths.append(case.expected_answer)

    if not questions:
        return {"available": False, "reason": "No functional test cases to score."}

    dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )

    judge_llm = ChatOpenAI(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0,
    )
    ragas_embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
        embeddings=ragas_embeddings,
    )

    df = result.to_pandas()

    def _to_native(value):
        """Recursively convert numpy/pandas scalar & array types to plain
        Python types so the result is always JSON-serializable."""
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return None if np.isnan(value) else float(value)
        if isinstance(value, (np.bool_,)):
            return bool(value)
        if isinstance(value, dict):
            return {k: _to_native(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_to_native(v) for v in value]
        return value

    per_case = [
        {k: _to_native(v) for k, v in record.items()}
        for record in df.to_dict(orient="records")
    ]

    def _safe_mean(col: str):
        """np.nanmean over a metric column; returns None if every row is NaN
        (e.g. RAGAS couldn't score any case) instead of silently returning NaN,
        which would otherwise render as a blank dash in the UI."""
        values = df[col].to_numpy(dtype=float)
        if np.all(np.isnan(values)):
            return None
        return round(float(np.nanmean(values)), 3)

    summary = {
        "available": True,
        "n_cases": len(df),
        "faithfulness": _safe_mean("faithfulness"),
        "answer_relevancy": _safe_mean("answer_relevancy"),
        "context_precision": _safe_mean("context_precision"),
        "context_recall": _safe_mean("context_recall"),
        "per_case": per_case,
    }
    return summary

def run_ragas_eval_on_logged(entries: list[dict]) -> dict:
    """Ground-truth-free RAGAS scoring for real chat turns already answered
    and logged by chat_logger.py. Only faithfulness and answer_relevancy are
    computed since those don't require a reference/ground-truth answer;
    context_precision/recall need a ground truth and are marked unavailable
    here (they're still scored normally in the synthetic test suite)."""
    # Refused answers have no real grounded content to score against — RAGAS
    # would either error or return NaN for them, which is why the previous
    # version showed a blank "-" whenever a refusal was mixed into the batch.
    usable = [e for e in entries if e.get("retrieved_chunks") and not e.get("refused")]
    if not usable:
        return {
            "available": False,
            "reason": "No non-refused real chat turns with retrieved context yet. "
                      "RAGAS needs at least one answered (non-refusal) question.",
        }

    questions = [e["question"] for e in usable]
    answers = [e["answer"] for e in usable]
    contexts = [[c["text"] for c in e["retrieved_chunks"]] or [""] for e in usable]

    dataset = Dataset.from_dict({"question": questions, "answer": answers, "contexts": contexts})

    judge_llm = ChatOpenAI(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0,
    )
    ragas_embeddings = OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=judge_llm,
        embeddings=ragas_embeddings,
    )
    df = result.to_pandas()

    def _safe_mean(col: str):
        values = df[col].to_numpy(dtype=float)
        if np.all(np.isnan(values)):
            return None
        return round(float(np.nanmean(values)), 3)

    faithfulness_val = _safe_mean("faithfulness")
    relevancy_val = _safe_mean("answer_relevancy")

    return {
        "available": faithfulness_val is not None or relevancy_val is not None,
        "n_cases": len(df),
        "faithfulness": faithfulness_val,
        "answer_relevancy": relevancy_val,
        "context_precision": None,
        "context_recall": None,
        "note": "Context precision/recall require a reference answer and are only available in the synthetic test suite.",
        "reason": "RAGAS could not score any of the logged turns (too few cases or scoring errors)." if faithfulness_val is None and relevancy_val is None else None,
    }