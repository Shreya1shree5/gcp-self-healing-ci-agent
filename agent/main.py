"""Orchestrator: diagnose which checks failed on a CI run, dispatch each to
the right category-specific fixer, validate with a full regression sweep
(not just the check being fixed), retry a bounded number of times, and only
open a PR once everything actually passes. Never auto-merges. Never trusts
a proposed fix without re-running the exact tool that reported the original
failure.

Usage: python -m agent.main <failed_run_id>
"""

import os
import sys

from . import checks, gh_api, git_ops
from .fixers import build_fixer, lint_fixer, test_fixer, type_fixer

MAX_RETRIES = 2
# Explicitly passed by the workflow as the triggering run's head branch —
# GITHUB_REF_NAME can't be trusted here since workflow_run always executes
# using the workflow file from the default branch, which isn't necessarily
# the branch that actually failed.
BASE_BRANCH = os.environ["BASE_BRANCH"]

FIXERS = {
    "lint": (lint_fixer, ["target-repo/mathutils/calculator.py"]),
    "typecheck": (type_fixer, ["target-repo/mathutils/calculator.py"]),
    "test": (test_fixer, ["target-repo/mathutils/calculator.py"]),
    "build": (build_fixer, ["target-repo/cli/report.py"]),
}

# Fix build/import errors first — a broken import can mask what the other
# checks would otherwise report cleanly on their own.
FIX_ORDER = ["build", "lint", "typecheck", "test"]


def read_files(paths: list[str]) -> dict[str, str]:
    result = {}
    for p in paths:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                result[p] = f.read()
    return result


def write_files(files: dict[str, str]) -> None:
    for path, content in files.items():
        full_path = path if path.startswith("target-repo/") else f"target-repo/{path}"
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)


def attempt_fix(check_name: str, log_output: str) -> bool:
    fixer_module, relevant_paths = FIXERS[check_name]
    files = read_files(relevant_paths)

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  [{check_name}] attempt {attempt}/{MAX_RETRIES}")
        try:
            fixed = fixer_module.fix(log_output, files)
        except ValueError as e:
            print(f"  [{check_name}] fixer refused: {e}")
            return False

        if fixed:
            write_files(fixed)

        passed, output = checks.CHECKS[check_name]()
        if passed:
            print(f"  [{check_name}] fix validated — check now passes.")
            return True

        print(f"  [{check_name}] fix did not resolve the issue:\n{output[:500]}")
        log_output = output  # feed the new failure back in for the retry
        git_ops.discard_changes("target-repo")

    return False


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m agent.main <failed_run_id>", file=sys.stderr)
        sys.exit(1)

    run_id = sys.argv[1]
    failed_jobs = gh_api.get_failed_jobs(run_id)
    if not failed_jobs:
        print("No failed jobs found for this run — nothing to do.")
        return

    check_names = [j["name"] for j in failed_jobs if j["name"] in FIXERS]
    print(f"Failed checks: {check_names}")

    branch = f"self-heal/run-{run_id}"
    git_ops.create_branch(branch)

    fixed_checks: list[str] = []
    unfixed_checks: list[str] = []

    for check_name in FIX_ORDER:
        if check_name not in check_names:
            continue
        job = next(j for j in failed_jobs if j["name"] == check_name)
        log_output = gh_api.get_job_log(job["id"])

        if attempt_fix(check_name, log_output):
            fixed_checks.append(check_name)
        else:
            unfixed_checks.append(check_name)

    if not fixed_checks:
        print("Could not auto-fix anything. Leaving a diagnosis comment instead of a PR.")
        sha = git_ops.run("git", "rev-parse", "HEAD").strip()
        gh_api.comment_on_commit(
            sha,
            f"Self-healing agent attempted fixes for: {', '.join(check_names)}.\n"
            f"Could not validate a working fix for any of them — needs human attention.",
        )
        return

    # Full regression sweep before committing anything — catches a fix for
    # one check subtly breaking another that wasn't in the original failure set.
    all_results = checks.run_all()
    regressions = [name for name, (passed, _) in all_results.items() if not passed]
    if regressions:
        print(f"Regression detected after fixes: {regressions}. Aborting — not opening a PR.")
        return

    commit_message = f"Self-heal: fix {', '.join(fixed_checks)}"
    if unfixed_checks:
        commit_message += f" (could not fix: {', '.join(unfixed_checks)})"

    committed = git_ops.commit_all(commit_message)
    if not committed:
        print("No file changes to commit (fixes were no-ops).")
        return

    git_ops.push(branch)

    body_lines = [
        f"Automated fix for a failing CI run on `{BASE_BRANCH}`.",
        "",
        f"**Fixed:** {', '.join(fixed_checks)}",
    ]
    if unfixed_checks:
        body_lines.append(f"**Could NOT auto-fix (needs manual attention):** {', '.join(unfixed_checks)}")
    body_lines += [
        "",
        "Validated by re-running the full check suite (lint, typecheck, test, build) "
        "after applying fixes — all green before this PR was opened. This was **not** "
        "auto-merged; please review before merging.",
    ]

    pr_url = gh_api.create_pull_request(
        branch=branch,
        base=BASE_BRANCH,
        title=commit_message,
        body="\n".join(body_lines),
    )
    print(f"Opened PR: {pr_url}")


if __name__ == "__main__":
    main()
