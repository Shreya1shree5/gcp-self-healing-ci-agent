"""Shared Gemini call used by every fixer. Always asks for COMPLETE file
contents back (never a diff) — a model-produced unified diff is much more
likely to fail to apply cleanly than a full-file replacement is to be wrong,
and a full-file replacement is trivial to write straight to disk.
"""

import json
import os
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
LOCATION = os.environ.get("GCP_LOCATION", "global")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# Same Vertex AI requests-per-minute quota wall hit twice already in this
# project series (RAG ingestion, then the live RAG service) — new/low-usage
# GCP projects get a restrictive default. This is a batch CI job (not a
# live request a human is waiting on), so a longer backoff than the RAG
# service used is fine here.
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 20

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def propose_fix(instructions: str, files: dict[str, str]) -> dict:
    files_block = "\n\n".join(
        f"--- CURRENT CONTENT OF {path} ---\n{content}" for path, content in files.items()
    )
    prompt = f"""{instructions}

{files_block}

Respond with JSON only, in exactly this shape:
{{"files": {{"path/to/file.py": "complete new file content"}}, "explanation": "one sentence on what changed and why"}}

Rules:
- Only include files that actually need to change.
- Return the COMPLETE new content of each changed file, never a diff or partial snippet.
- If you need to create a new file, use the same path prefix style shown above
  (e.g. if inputs are shown as "target-repo/cli/report.py", a new file should be
  "target-repo/cli/formatter.py", not "cli/formatter.py").
"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            return json.loads(response.text)
        except genai_errors.ClientError as e:
            is_quota_error = "RESOURCE_EXHAUSTED" in str(e)
            if not is_quota_error or attempt == MAX_RETRIES:
                raise
            wait = BACKOFF_BASE_SECONDS * attempt
            print(f"  quota hit (attempt {attempt}/{MAX_RETRIES}), backing off {wait}s...")
            time.sleep(wait)
    raise RuntimeError("unreachable")
