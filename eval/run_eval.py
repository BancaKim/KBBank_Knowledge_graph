"""DSPy-style evaluation runner for banking chatbot.

Runs golden set questions against the live chatbot API and scores responses.
Usage: python -m eval.run_eval [--api-url URL] [--output FILE]
"""
from __future__ import annotations

import json
import os
import time
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

API_URL = os.environ.get("EVAL_API_URL", "https://kb-kg.duckdns.org/api/chat")
GOLDEN_SET = Path(__file__).parent / "golden_set.json"


import re as _re

# Patterns that signal numeric/rate data is present in an answer
_NUMERIC_PATTERNS = [
    _re.compile(r"\d+[\.,]?\d*\s*%"),          # 2.4%, 0.5 %
    _re.compile(r"\d+\s*천만\s*원"),             # 5천만원
    _re.compile(r"\d+\s*억\s*원"),               # 1억원
    _re.compile(r"\d+\s*(년|개월|일)\b"),        # 30년, 12개월
    _re.compile(r"연\s+\d"),                     # 연 2.4
    _re.compile(r"\d+\s*만\s*원"),               # 300만원
]

# Element keywords that indicate the element is about numeric/rate data
_NUMERIC_ELEM_KEYWORDS = {"수치", "금리", "이율", "금액", "한도", "기간", "만기", "비율"}


def _elem_in_answer(elem: str, answer: str, answer_nospace: str) -> bool:
    """Check if a required/forbidden element appears in the answer.

    Strategy for Korean text:
    1. Exact match (case-insensitive) after lowercasing.
    2. Space-stripped match: compare elem with spaces removed against answer
       with spaces removed — catches "예금자보호" vs "예금자 보호".
    3. Per-token match: check each whitespace-delimited token (length >= 2)
       directly — this covers 2-char Korean words like "금리" that the original
       code excluded with `len(kw) > 2`.
    4. Numeric proxy: if the element is about numeric/rate data and the answer
       contains numeric patterns (percentages, amounts, durations), treat as
       found — e.g. "금리 수치" matched by "연 2.4% ~ 2.9%".
    """
    elem_lower = elem.lower()
    answer_lower = answer.lower()

    # 1. Exact substring
    if elem_lower in answer_lower:
        return True

    # 2. Space-stripped comparison
    elem_nospace = elem_lower.replace(" ", "")
    if len(elem_nospace) >= 2 and elem_nospace in answer_nospace:
        return True

    # 3. Per-token match (include 2-char tokens, fixing the original > 2 bug)
    for token in elem_lower.split():
        if len(token) >= 2 and token in answer_lower:
            return True

    # 4. Numeric proxy — if elem contains a numeric/rate keyword and the answer
    #    has numeric data, consider it found
    elem_tokens = set(elem_lower.split())
    if elem_tokens & _NUMERIC_ELEM_KEYWORDS:
        for pat in _NUMERIC_PATTERNS:
            if pat.search(answer_lower):
                return True

    return False


def score_response(answer: str, test_case: dict) -> dict:
    """Score a response against required/forbidden elements."""
    answer_lower = answer.lower() if answer else ""
    answer_nospace = answer_lower.replace(" ", "")

    # Required elements check
    required = test_case.get("required_elements", [])
    found = []
    missing = []
    for elem in required:
        if _elem_in_answer(elem, answer_lower, answer_nospace):
            found.append(elem)
        else:
            missing.append(elem)

    # Forbidden elements check
    forbidden = test_case.get("forbidden_elements", [])
    violations = []
    for elem in forbidden:
        if _elem_in_answer(elem, answer_lower, answer_nospace):
            violations.append(elem)

    required_score = len(found) / len(required) if required else 1.0
    forbidden_penalty = len(violations) / len(forbidden) if forbidden else 0.0

    # Quality checks
    is_error = "오류" in answer or "죄송합니다" in answer[:50]
    is_too_short = len(answer) < 100
    is_hallucinating = "KB국민은행" in answer  # Should say 큽 not KB
    # Detect numeric data from tool calls: percentages, Korean monetary amounts,
    # duration patterns (개월/년/일), and explicit rate markers.
    import re
    has_tool_data = bool(
        any(kw in answer for kw in ["연 ", "%", "만원", "개월", "억원", "천만원"]) or
        re.search(r"\d+[\.,]?\d*\s*%", answer) or          # e.g. 2.4%, 0.5 %
        re.search(r"\d+\s*천만\s*원", answer) or            # e.g. 5천만원
        re.search(r"\d+\s*억\s*원", answer) or              # e.g. 1억원
        re.search(r"\d+\s*(년|개월|일)\s*(이상|이내|만기)?", answer)  # 30년, 12개월
    )

    quality_score = 1.0
    if is_error:
        quality_score -= 0.5
    if is_too_short and test_case["difficulty"] != "easy":
        quality_score -= 0.2
    if is_hallucinating:
        quality_score -= 0.1
    if not has_tool_data and test_case.get("tool_expected"):
        quality_score -= 0.3

    final_score = (required_score * 0.5 + max(0, quality_score) * 0.3 + (1 - forbidden_penalty) * 0.2)

    return {
        "score": round(final_score, 3),
        "required_found": found,
        "required_missing": missing,
        "forbidden_violations": violations,
        "is_error": is_error,
        "is_too_short": is_too_short,
        "answer_length": len(answer),
        "has_tool_data": has_tool_data,
    }


def run_eval(api_url: str = API_URL, output_file: str | None = None) -> dict:
    """Run full evaluation."""
    golden = json.loads(GOLDEN_SET.read_text())
    results = []
    total_score = 0

    print(f"Running {len(golden)} test cases against {api_url}\n")
    print(f"{'ID':<5} {'Domain':<8} {'Diff':<8} {'Score':>6} {'Time':>6}  Question")
    print("-" * 90)

    for tc in golden:
        start = time.time()
        try:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            resp = requests.post(
                api_url,
                json={"message": tc["question"], "history": []},
                headers={"X-OpenAI-Key": api_key},
                timeout=60,
            )
            data = resp.json()
            answer = data.get("answer", data.get("response", ""))
        except Exception as e:
            answer = f"ERROR: {e}"

        elapsed = time.time() - start
        scoring = score_response(answer, tc)

        result = {
            **tc,
            "answer": answer[:500],
            "elapsed_sec": round(elapsed, 1),
            **scoring,
        }
        results.append(result)
        total_score += scoring["score"]

        status = "✓" if scoring["score"] >= 0.7 else "✗" if scoring["score"] < 0.4 else "△"
        print(f"{tc['id']:<5} {tc['domain']:<8} {tc['difficulty']:<8} {scoring['score']:>5.2f}  {elapsed:>5.1f}s {status} {tc['question'][:40]}")

    # Summary
    avg_score = total_score / len(golden)
    by_domain = {}
    by_difficulty = {}
    for r in results:
        d = r["domain"]
        diff = r["difficulty"]
        by_domain.setdefault(d, []).append(r["score"])
        by_difficulty.setdefault(diff, []).append(r["score"])

    summary = {
        "total_questions": len(golden),
        "avg_score": round(avg_score, 3),
        "by_domain": {k: round(sum(v)/len(v), 3) for k, v in by_domain.items()},
        "by_difficulty": {k: round(sum(v)/len(v), 3) for k, v in by_difficulty.items()},
        "pass_rate": round(sum(1 for r in results if r["score"] >= 0.7) / len(results), 3),
        "error_rate": round(sum(1 for r in results if r["is_error"]) / len(results), 3),
    }

    print("\n" + "=" * 90)
    print(f"Average Score: {avg_score:.3f}")
    print(f"Pass Rate (≥0.7): {summary['pass_rate']*100:.0f}%")
    print(f"Error Rate: {summary['error_rate']*100:.0f}%")
    print(f"By Domain: {summary['by_domain']}")
    print(f"By Difficulty: {summary['by_difficulty']}")

    output = {"summary": summary, "results": results}

    out_path = Path(output_file) if output_file else Path(__file__).parent / "baseline_results.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"\nResults saved to {out_path}")

    return output


if __name__ == "__main__":
    url = API_URL
    out = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--api-url" and i < len(sys.argv) - 1:
            url = sys.argv[i + 1]
        elif arg == "--output" and i < len(sys.argv) - 1:
            out = sys.argv[i + 1]
    run_eval(url, out)
