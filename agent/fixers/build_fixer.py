"""Build/import fixer — the traceback names the missing module or bad
import; this fixer either corrects the import or creates the missing file
with a minimal implementation satisfying how it's used.
"""

from .. import llm


def fix(log_output: str, files: dict[str, str]) -> dict[str, str]:
    instructions = (
        "The following Python code fails to import, with the traceback shown "
        "below. Fix it — either by correcting a wrong import path, or by "
        "creating the missing module with a reasonable, minimal implementation "
        "that satisfies how it's being used in the importing file.\n\n"
        f"Traceback:\n{log_output}"
    )
    return llm.propose_fix(instructions, files)["files"]
