"""Test fixer — the highest-risk category. Fixes the SOURCE code implicated
by a failing test, never the test file itself.

A model asked to "make this test pass" will sometimes take the shortcut of
weakening the assertion instead of fixing the real bug — that's the classic
failure mode of naive self-healing tooling, and it's worse than doing
nothing because it creates false confidence. This fixer never receives the
test file as an editable input (only pytest's own failure output, which
already shows the relevant assertion/traceback as read-only context), and
main.py independently double-checks the proposed paths as defense in depth.
"""

from .. import llm

PROTECTED_PATH_MARKERS = ("tests/", "test_")


def fix(log_output: str, files: dict[str, str]) -> dict[str, str]:
    instructions = (
        "The Python source code below has a bug that causes a test to fail — "
        "the failing test's pytest output (including the assertion and "
        "traceback) is shown below for context. Fix the BUG IN THE SOURCE "
        "CODE so the test passes because the behavior is now genuinely "
        "correct. You do not have access to modify the test file and must "
        "not propose changes to it.\n\n"
        f"pytest output:\n{log_output}"
    )
    result = llm.propose_fix(instructions, files)
    fixed_files = result["files"]

    for path in fixed_files:
        if any(marker in path for marker in PROTECTED_PATH_MARKERS):
            raise ValueError(
                f"Test fixer proposed changing a protected test path ({path}) — "
                "refusing to apply. This should never happen; flagging for review "
                "instead of silently dropping it."
            )
    return fixed_files
