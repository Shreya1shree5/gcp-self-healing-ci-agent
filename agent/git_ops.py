"""Branch/commit/push via plain git subprocess calls. The agent already runs
inside a real checkout on the Actions runner (with GITHUB_TOKEN wired for
push access via actions/checkout's default credential persistence), so this
is simpler and more reliable than reimplementing commits over the Contents API.
"""

import subprocess


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def create_branch(name: str) -> None:
    run("git", "checkout", "-b", name)


def commit_all(message: str) -> bool:
    """Returns False if there was nothing to commit (fix produced no diff)."""
    run("git", "add", "-A")
    status = run("git", "status", "--porcelain")
    if not status.strip():
        return False
    run("git", "-c", "user.name=self-healing-ci-bot", "-c", "user.email=bot@example.com", "commit", "-m", message)
    return True


def push(branch: str) -> None:
    run("git", "push", "origin", branch)


def discard_changes(path: str = ".") -> None:
    """Used between retry attempts — discard a failed fix attempt cleanly
    (both tracked-file edits and newly-created untracked files) before
    trying again, rather than layering attempts on top of each other.
    """
    run("git", "checkout", "--", path)
    run("git", "clean", "-fd", path)
