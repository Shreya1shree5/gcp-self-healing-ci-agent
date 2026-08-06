"""Shared Gemini call used by every fixer. Always asks for COMPLETE file
contents back (never a diff) — a model-produced unified diff is much more
likely to fail to apply cleanly than a full-file replacement is to be wrong,
and a full-file replacement is trivial to write straight to disk.
"""

import json
import os

from google import genai
from google.genai import types

PROJECT_ID = os.environ["GCP_PROJECT_ID"]
LOCATION = os.environ.get("GCP_LOCATION", "global")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

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
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)
