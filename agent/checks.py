"""Runs each check locally against the sandboxed checkout. Used twice:
once (implicitly, via CI) to detect the original failure, and again here
after a proposed fix is applied — the same command, so "does this actually
pass now" is answered by the exact same tool that reported the failure,
not a different/looser check.
"""

import subprocess

TARGET_REPO = "target-repo"


def _run(cmd: list[str]) -> tuple[bool, str]:
    result = subprocess.run(cmd, cwd=TARGET_REPO, capture_output=True, text=True)
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def run_lint() -> tuple[bool, str]:
    return _run(["ruff", "check", "."])


def run_typecheck() -> tuple[bool, str]:
    return _run(["mypy", "mathutils"])


def run_tests() -> tuple[bool, str]:
    return _run(["pytest", "tests/", "-v"])


def run_build() -> tuple[bool, str]:
    return _run(["python", "-c", "import cli.report"])


CHECKS = {
    "lint": run_lint,
    "typecheck": run_typecheck,
    "test": run_tests,
    "build": run_build,
}


def run_all() -> dict[str, tuple[bool, str]]:
    """Full regression sweep — run after every fix attempt, not just the
    check being fixed, so a fix that resolves one failure but breaks
    something else gets caught before it ever reaches a PR.
    """
    return {name: fn() for name, fn in CHECKS.items()}
