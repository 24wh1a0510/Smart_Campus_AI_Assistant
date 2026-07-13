"""DeepEval automated evaluation — with built-in fallback.

Two modes:
  1. Native mode  — uses the `deepeval` package if installed (pip install deepeval)
  2. Built-in mode — works with zero extra dependencies, uses the existing
     ChatClient to score hallucination, relevancy, and contextual precision
     via a structured LLM judge prompt (same pattern as the existing judge.py).

Built-in metrics:
  - Hallucination  : is the answer strictly grounded in the retrieved context?
  - Answer Relevancy : does the answer actually address the question asked?
  - Contextual Precision : are the retrieved chunks relevant to the question?
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

REPORT_PATH = Path("evaluation/results/deepeval_report.json")

SAMPLE_QUESTIONS = [
    "What B.Tech branches does BVRIT offer?",
    "What is the tuition fee for CSE at BVRIT?",
    "Who is the HOD of the CSE department?",
    "What is the highest placement package at BVRIT?",
    "Does BVRIT have hostel facilities?",
    "What scholarships are available at BVRIT?",
    "Is BVRIT accredited by NAAC?",
    "What is the total B.Tech intake at BVRIT?",
    "How do I contact the BVRIT admissions office?",
    "What is the EAMCET cutoff for CSE at BVRIT?",
]

# Built-in judge prompt for DeepEval-style metrics
_DEEPEVAL_JUDGE_PROMPT = """You are a strict evaluator for a RAG chatbot. Evaluate the following:

Question: {question}
Retrieved Context: {context}
Bot Answer: {answer}

Score each metric from 0.0 to 1.0:
- hallucination: 1.0 = fully grounded in context, 0.0 = contains fabricated facts not in context
- answer_relevancy: 1.0 = directly answers the question, 0.0 = off-topic or evasive
- contextual_precision: 1.0 = retrieved context is highly relevant to question, 0.0 = irrelevant chunks

Thresholds: hallucination >= 0.5, answer_relevancy >= 0.7, contextual_precision >= 0.6

Respond ONLY with JSON (no markdown fences, no extra text):
{{"hallucination": 0.0-1.0, "answer_relevancy": 0.0-1.0, "contextual_precision": 0.0-1.0, "passed": true/false, "reasoning": "one sentence"}}"""


def _parse_judge_response(raw: str) -> dict:
    """
    Robustly parse a JSON response from the LLM judge.

    Handles multiple common patterns:
      - Pure JSON: {"key": ...}
      - Markdown fenced: ```json\n{...}\n```
      - Markdown fenced without language: ```\n{...}\n```
      - JSON with surrounding text: "Sure! Here is the result: {...}"
    """
    text = raw.strip()

    # 1. Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        # 2. If no fences, try to extract the first {...} block from the text
        brace_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0).strip()

    # 3. Attempt direct JSON parse
    return json.loads(text)


def _run_builtin_eval(n_cases: int = 10, save_report: bool = True) -> dict:
    """Built-in DeepEval-style evaluation — zero extra dependencies. Runs sequentially with retry."""
    import time as _time
    from app.rag.generator import RAGGenerator
    from app.rag.llm_client import ChatClient

    generator = RAGGenerator()
    client = ChatClient()
    questions = SAMPLE_QUESTIONS[:n_cases]
    results = []
    passed = 0
    skipped = 0

    # Brief pause so any recent chat calls have settled
    _time.sleep(2)

    for question in questions:
        entry = None
        # Retry up to 2 times on rate-limit errors
        for attempt in range(3):
            try:
                resp = generator.answer(question=question, history=[])
                context_text = "\n".join(c.text[:300] for c in resp.retrieved_chunks) or "(none)"

                judge_result = client.complete(
                    messages=[{
                        "role": "user",
                        "content": _DEEPEVAL_JUDGE_PROMPT.format(
                            question=question,
                            context=context_text[:2000],
                            answer=resp.answer[:800],
                        )
                    }],
                    temperature=0.0,
                    max_tokens=200,
                    call_type="eval",
                )

                raw = judge_result["text"]
                scores = _parse_judge_response(raw)

                entry = {
                    "question": question,
                    "answer_snippet": resp.answer[:150],
                    "hallucination": float(scores.get("hallucination", 0.0)),
                    "answer_relevancy": float(scores.get("answer_relevancy", 0.0)),
                    "contextual_precision": float(scores.get("contextual_precision", 0.0)),
                    "passed": bool(scores.get("passed", False)),
                    "reasoning": str(scores.get("reasoning", "")),
                }
                if entry["passed"]:
                    passed += 1
                break  # success

            except json.JSONDecodeError as e:
                # Log the parse failure but don't retry — it's a format issue, not rate limit
                entry = {
                    "question": question,
                    "answer_snippet": "",
                    "hallucination": 0.0,
                    "answer_relevancy": 0.0,
                    "contextual_precision": 0.0,
                    "passed": False,
                    "reasoning": f"JSON parse error: {str(e)[:100]}",
                }
                break

            except Exception as e:
                err_str = str(e)
                is_rate_limit = (
                    "429" in err_str or "rate" in err_str.lower()
                    or "RetryError" in err_str or "APIStatus" in err_str
                )
                if is_rate_limit and attempt < 2:
                    _time.sleep(4 * (attempt + 1))
                    continue
                elif is_rate_limit:
                    skipped += 1
                    entry = None
                    break
                else:
                    entry = {
                        "question": question,
                        "answer_snippet": "",
                        "hallucination": 0.0,
                        "answer_relevancy": 0.0,
                        "contextual_precision": 0.0,
                        "passed": False,
                        "reasoning": f"Evaluation error: {err_str[:100]}",
                    }
                    break

        if entry is not None:
            results.append(entry)

        # 1.5s between calls to stay under rate limit
        _time.sleep(1.5)

    def _avg(key: str) -> float:
        vals = [r[key] for r in results if isinstance(r.get(key), (int, float))]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    run = len(results)
    skip_note = f" ({skipped} skipped due to rate limiting)" if skipped else ""
    report = {
        "available": True,
        "mode": "built-in",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_cases": run,
        "passed": passed,
        "skipped": skipped,
        "averages": {
            "hallucination": _avg("hallucination"),
            "answer_relevancy": _avg("answer_relevancy"),
            "contextual_precision": _avg("contextual_precision"),
        },
        "results": results,
        "summary": f"{passed}/{run} test cases passed all thresholds{skip_note}.",
        "error": None,
        "note": "Running in built-in mode (no deepeval package needed). Install `deepeval` for richer metric computation.",
    }

    if save_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return report


def run_deepeval(n_cases: int = 10, save_report: bool = True) -> dict:
    """Run DeepEval — uses native deepeval if installed, built-in fallback otherwise."""
    try:
        import deepeval  # noqa: F401
    except ImportError:
        return _run_builtin_eval(n_cases=n_cases, save_report=save_report)

    # Native DeepEval path
    try:
        from deepeval import evaluate
        from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric
        from deepeval.test_case import LLMTestCase
        from app.rag.generator import RAGGenerator

        generator = RAGGenerator()
        metrics = [HallucinationMetric(threshold=0.5), AnswerRelevancyMetric(threshold=0.7)]
        test_cases = []

        for q in SAMPLE_QUESTIONS[:n_cases]:
            try:
                resp = generator.answer(question=q, history=[])
                context = [c.text for c in resp.retrieved_chunks]
                test_cases.append(LLMTestCase(input=q, actual_output=resp.answer, retrieval_context=context))
            except Exception:
                continue

        if not test_cases:
            return _run_builtin_eval(n_cases=n_cases, save_report=save_report)

        eval_results = evaluate(test_cases, metrics)
        results = []
        passed = 0
        for tc, res in zip(test_cases, getattr(eval_results, "test_results", [])):
            entry = {
                "question": tc.input,
                "passed": getattr(res, "success", False),
                "scores": {m.name: round(getattr(m, "score", 0.0) or 0.0, 3)
                           for m in getattr(res, "metrics_data", [])},
            }
            if entry["passed"]:
                passed += 1
            results.append(entry)

        report = {
            "available": True,
            "mode": "deepeval-native",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_cases": len(results),
            "passed": passed,
            "results": results,
            "summary": f"{passed}/{len(results)} test cases passed DeepEval metrics.",
            "error": None,
        }

        if save_report:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

        return report

    except Exception as e:
        # Native path failed — fall back to built-in
        return _run_builtin_eval(n_cases=n_cases, save_report=save_report)


def load_deepeval_report() -> dict | None:
    if REPORT_PATH.exists():
        try:
            return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None
