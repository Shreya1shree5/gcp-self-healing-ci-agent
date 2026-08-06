"""Lint fixer — tries the deterministic auto-formatter first. No AI call
needed for the mechanical case (unused imports, formatting); only falls
back to a model-proposed fix for violations ruff can't auto-fix itself.
"""

import subprocess

from .. import llm

TARGET_REPO = "target-repo"


def _try_autofix() -> bool:
    subprocess.run(["ruff", "check", "--fix", "."], cwd=TARGET_REPO)
    subprocess.run(["ruff", "format", "."], cwd=TARGET_REPO)
    result = subprocess.run(["ruff", "check", "."], cwd=TARGET_REPO, capture_output=True)
    return result.returncode == 0


def fix(log_output: str, files: dict[str, str]) -> dict[str, str]:
    if _try_autofix():
        return {}  # ruff already rewrote the file(s) on disk; nothing else to write

    instructions = (
        "The following Python code fails a ruff lint check that ruff's own "
        "--fix could not resolve automatically. Fix ONLY the specific "
        "violation(s) shown in the lint output below — make the minimal "
        "change needed, don't restyle unrelated code.\n\n"
        f"Lint output:\n{log_output}"
    )
    return llm.propose_fix(instructions, files)["files"]
