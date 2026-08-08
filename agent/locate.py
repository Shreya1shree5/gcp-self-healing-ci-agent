"""Locates which file(s) a check's failure output actually implicates, by
parsing the tool's own output — no hardcoded knowledge of any specific
repo's file layout. This is what makes the agent generalize to a real repo
it's never seen, instead of only working on this demo's four pre-known bugs.

Each check tool already prints the file it's unhappy about, in its own
format; deliberately deterministic regex parsing here, not an LLM guess —
the information is already structured in the tool's own output, so parsing
it directly is both more reliable and cheaper than asking a model to read
the log and name a file.
"""

import os
import re

TARGET_REPO = "target-repo"


def _normalize(path: str) -> str:
    path = path.replace("\\", "/").strip()
    if not path.startswith(f"{TARGET_REPO}/"):
        path = f"{TARGET_REPO}/{path}"
    return path


def locate_from_ruff(log_output: str) -> list[str]:
    # ruff prints "  --> path/to/file.py:LINE:COL" under each finding
    matches = re.findall(r"-->\s+([^\s:]+):\d+:\d+", log_output)
    return sorted({_normalize(m) for m in matches})


def locate_from_mypy(log_output: str) -> list[str]:
    # mypy prints "path/to/file.py:LINE: error: ..." at the start of each line
    matches = re.findall(r"^([^\s:]+\.py):\d+:", log_output, re.MULTILINE)
    return sorted({_normalize(m) for m in matches})


def locate_from_build(log_output: str) -> list[str]:
    """Import/build failures need two things: the file containing the bad
    import (from the traceback), and — for a genuinely missing module —
    the expected path of the file that needs to be *created*, which by
    definition can't appear in any traceback since it doesn't exist yet.
    """
    files: set[str] = set()

    # Deepest real (non-stdlib, non-"<string>") frame in the traceback is
    # the file that actually contains the bad import statement.
    for path in re.findall(r'File "([^"]+)", line \d+', log_output):
        if path == "<string>" or "site-packages" in path or "lib/python" in path:
            continue
        # Runner paths are absolute; keep just the target-repo-relative tail.
        if TARGET_REPO in path:
            tail = path.split(TARGET_REPO, 1)[1].lstrip("/\\").replace("\\", "/")
            files.add(_normalize(tail))

    # ModuleNotFoundError names the missing module dotted-path; convert
    # straight to the file that would need to exist.
    missing = re.search(r"No module named '([^']+)'", log_output)
    if missing:
        missing_path = missing.group(1).replace(".", "/") + ".py"
        files.add(_normalize(missing_path))

    return sorted(files)


def locate_from_pytest(log_output: str) -> list[str]:
    """No exception traceback into source for a plain assertion mismatch
    (pytest just shows the computed values), so infer the implicated
    source file by extracting function names called in the failing
    assertion, then searching the source tree (excluding tests/) for
    where each is actually defined.

    A heuristic, not a guarantee — genuinely ambiguous cases (the bug is
    in a function neither called directly in the assertion nor easily
    greppable) would need a smarter approach. Good enough for the common
    case of "the function under test has a bug in its own body."
    """
    called_functions = set(re.findall(r"assert\s+(?:\w+\()?(\w+)\(", log_output))
    # Drop common false positives that aren't user functions.
    called_functions -= {"assert", "str", "int", "float", "list", "dict", "len"}

    files: set[str] = set()
    for root, dirs, filenames in os.walk(TARGET_REPO):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__")]
        if os.path.basename(root) == "tests":
            continue
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            full_path = os.path.join(root, filename)
            try:
                with open(full_path, encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue
            for fn_name in called_functions:
                if re.search(rf"^def {re.escape(fn_name)}\(", content, re.MULTILINE):
                    files.add(_normalize(os.path.relpath(full_path, ".")))

    return sorted(files)


LOCATORS = {
    "lint": locate_from_ruff,
    "typecheck": locate_from_mypy,
    "test": locate_from_pytest,
    "build": locate_from_build,
}
