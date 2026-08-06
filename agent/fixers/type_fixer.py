"""Type-check fixer — feeds the mypy error plus the implicated file's
current content to the model, asks for a corrected version.
"""

from .. import llm


def fix(log_output: str, files: dict[str, str]) -> dict[str, str]:
    instructions = (
        "The following Python code fails a mypy strict type check. Fix ONLY "
        "the type error(s) shown below — correct annotations or logic as "
        "needed, but don't change unrelated behavior.\n\n"
        f"mypy output:\n{log_output}"
    )
    return llm.propose_fix(instructions, files)["files"]
