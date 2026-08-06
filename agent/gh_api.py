"""Thin GitHub REST API wrapper — fetching failed-job info and opening the
final PR. Branch/commit/push themselves are done via plain git subprocess
calls (see git_ops.py) since the agent already runs inside a real checkout;
reimplementing that over the Contents API would just be more surface area
for no benefit.
"""

import os

import requests

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]  # "owner/repo", set automatically by Actions

API_ROOT = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


def get_failed_jobs(run_id: str) -> list[dict]:
    """Returns [{"name": "lint", "id": 123, "conclusion": "failure"}, ...]
    for every job in the run that didn't pass — deterministic classification
    by job name, not an LLM guess, since the CI workflow already names each
    check job exactly what it is.
    """
    resp = requests.get(
        f"{API_ROOT}/repos/{REPO}/actions/runs/{run_id}/jobs", headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    jobs = resp.json()["jobs"]
    return [j for j in jobs if j["conclusion"] == "failure"]


def get_job_log(job_id: str) -> str:
    resp = requests.get(
        f"{API_ROOT}/repos/{REPO}/actions/jobs/{job_id}/logs",
        headers=HEADERS,
        timeout=30,
        allow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def create_pull_request(branch: str, base: str, title: str, body: str) -> str:
    resp = requests.post(
        f"{API_ROOT}/repos/{REPO}/pulls",
        headers=HEADERS,
        json={"title": title, "head": branch, "base": base, "body": body},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["html_url"]


def comment_on_commit(sha: str, body: str) -> None:
    """Fallback when no fix could be validated — leave a diagnosis instead
    of silently doing nothing.
    """
    resp = requests.post(
        f"{API_ROOT}/repos/{REPO}/commits/{sha}/comments",
        headers=HEADERS,
        json={"body": body},
        timeout=30,
    )
    resp.raise_for_status()
