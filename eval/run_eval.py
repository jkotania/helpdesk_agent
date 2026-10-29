"""python -m eval.run_eval  (writes eval/results.md)"""

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from helpdesk.agent import Agent, OpenAICompatibleModel
from helpdesk.tools import STAFF_CONTACT

EVAL_DIR = Path(__file__).resolve().parent
REFUSAL_MARKERS = ["help@citywheels.example", "000 000 000"]


def check(case: dict, answer_text: str, called_tools: list[str]) -> list[str]:
    # Returns the reasons a case failed, empty means it passed.
    # gpt-oss likes non-breaking hyphens and curly apostrophes ("CW‑7777", "couldn’t")
    text = answer_text.lower().replace("‑", "-").replace("’", "'")
    problems = []
    for tool in case.get("expect_tools", []):
        if tool not in called_tools:
            problems.append(f"did not call {tool} (called {called_tools or 'nothing'})")
    any_of = case.get("expect_any_tool", [])
    if any_of and not set(any_of) & set(called_tools):
        problems.append(f"called none of {any_of} (called {called_tools or 'nothing'})")
    for expected in case.get("must_contain", []):
        if expected.lower() not in text:
            problems.append(f"answer is missing {expected!r}")
    for forbidden in case.get("must_not_contain", []):
        if forbidden.lower() in text:
            problems.append(f"answer contains {forbidden!r}")
    if case.get("must_refuse") and not any(marker in text for marker in REFUSAL_MARKERS):
        problems.append(f"did not refer to the staff ({STAFF_CONTACT})")
    return problems


def main() -> None:
    load_dotenv()
    model = OpenAICompatibleModel()
    cases = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))

    rows, details = [], []
    for case in cases:
        # fresh agent per case so history from one question cannot help the next
        try:
            answer = Agent(model).ask(case["question"])
            text, tools = answer.text, [call["name"] for call in answer.tool_calls]
            problems = check(case, text, tools)
        except Exception as error:  # noqa: BLE001  one broken case should not kill the whole run
            text, tools, problems = "", [], [f"crashed: {error}"]
        status = "PASS" if not problems else "FAIL"
        print(f"{status} {case['id']}" + "".join(f"\n  - {p}" for p in problems))
        rows.append(f"| {case['id']} | {status} | {', '.join(tools) or '-'} |")
        details.append(
            f"### {case['id']}: {status}\n\n**Q:** {case['question']}\n\n**A:** {text.strip() or '(no answer)'}\n"
            + "".join(f"\n- {p}" for p in problems)
        )

    passed = sum("| PASS |" in row for row in rows)
    report = "\n".join(
        [
            "# Evaluation results",
            "",
            f"Model: `{model.model}`. Run at {datetime.now():%Y-%m-%d %H:%M}.",
            "",
            f"**{passed} of {len(rows)} passed.**",
            "",
            "| Case | Result | Tools called |",
            "| --- | --- | --- |",
            *rows,
            "",
            "## Answers",
            "",
            "\n\n".join(details),
            "",
        ]
    )
    (EVAL_DIR / "results.md").write_text(report, encoding="utf-8")
    print(f"\n{passed}/{len(rows)} passed, written to eval/results.md")


if __name__ == "__main__":
    main()
