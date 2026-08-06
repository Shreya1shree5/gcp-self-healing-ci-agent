# Self-Healing CI Agent

When CI fails, this agent diagnoses **which kind** of failure it is (lint, type-check, test,
or build/import), dispatches to a category-specific fix strategy, validates the fix by
re-running the actual tools that reported the original failure (plus a full regression sweep),
and only then opens a PR — never auto-merges, never trusts its own output without proof.

## Why this project, and what's different from the earlier ones

Every previous project in this series ended in **text** — an answer, a summary, a comment.
This one ends in a **validated code change and a real PR**. The interesting engineering isn't
"call an LLM to write a fix" (that's a few lines) — it's the safety architecture around it:
category-specific dispatch, a hard rule that test fixes can never touch test files, a full
regression sweep before committing anything, and bounded retries with graceful failure
instead of infinite loops or a silently broken PR.

## Architecture

```
CI workflow fails (one or more of: lint / typecheck / test / build)
                    │
                    ▼ (workflow_run trigger)
Self-heal workflow starts, authenticates to GCP via WIF
                    │
                    ▼
For each failed check, in order (build → lint → typecheck → test):
  1. Fetch that job's actual log via the GitHub API
  2. Dispatch to the category's fixer (lint tries ruff --fix first,
     others go straight to a Gemini-proposed full-file rewrite)
  3. Re-run THAT SPECIFIC check tool against the fix
  4. Pass → keep it. Fail → feed the new error back, retry (max 2)
                    │
                    ▼
Full regression sweep — re-run ALL FOUR checks, not just the ones
that were broken, catching a fix that breaks something else
                    │
        ┌───────────┴───────────┐
   everything green         still broken
        │                         │
  commit + push +            leave a diagnosis
  open a PR for review       comment, no PR
```

## The four failure categories, and why each is handled differently

| Check | Fix strategy | Risk level |
|---|---|---|
| **lint** | Try `ruff --fix` first (deterministic, no AI) — only fall back to a model-proposed fix for violations ruff can't auto-fix | Low |
| **typecheck** | Feed the mypy error + file to Gemini, request a corrected version | Low-medium |
| **build** | Feed the traceback to Gemini — either fixes a bad import or creates a missing module with a minimal implementation | Medium |
| **test** | Feed the pytest failure to Gemini, but **the test file is never an editable input** — only the implicated source file is | High |

The `test` category gets special treatment because it's the one place a model has an obvious
shortcut available: weaken the assertion instead of fixing the real bug. `agent/fixers/test_fixer.py`
structurally cannot propose changes to the test file (it's never given as an editable target),
and `agent/main.py`/the fixer itself double-check the returned file paths as defense in depth —
if the model somehow still tried, the fixer raises and the fix is refused outright rather than
silently applied.

## The target repo (`target-repo/`)

A small, deliberately-broken Python package with **one independent bug per category** — kept
separate so fixing one never masks or depends on another:
- `mathutils/calculator.py` has an unused import (lint), a wrong type annotation on `divide`
  (typecheck), and a real bug in `multiply` (test failure)
- `cli/report.py` imports a module that doesn't exist (build failure)

## One-time setup

Reuses the same GCP project and Workload Identity Federation **pool** as the IaC Review Agent
project, with a new provider scoped to this repo and a new, narrowly-scoped service account.

```bash
export PROJECT_ID="YOUR_PROJECT_ID"
export PROJECT_NUMBER="$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')"
export REPO="your-org/gcp-self-healing-ci-agent"

# New provider under the EXISTING github-pool, scoped to this repo specifically
gcloud iam workload-identity-pools providers create-oidc "github-provider-ci-healer" \
  --project="$PROJECT_ID" --location="global" --workload-identity-pool="github-pool" \
  --display-name="CI Healer provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# New service account — only needs Vertex AI access, nothing else
gcloud iam service-accounts create ci-healer \
  --project="$PROJECT_ID" --display-name="Self-Healing CI Agent SA"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:ci-healer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud iam service-accounts add-iam-policy-binding \
  "ci-healer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"
```

Push this repo to GitHub, then under `Settings > Secrets and variables > Actions`, add these
**Variables**:
- `GCP_PROJECT_ID` — your project ID
- `GCP_WORKLOAD_IDENTITY_PROVIDER` — `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider-ci-healer`
- `GCP_HEALER_SA` — `ci-healer@YOUR_PROJECT_ID.iam.gserviceaccount.com`

No Cloud secrets needed beyond that — `GITHUB_TOKEN` is automatic.

## Test it

Push to any branch — `ci.yml` will fail (all four checks are seeded to fail on the initial
commit), which triggers `self-heal.yml` automatically. Watch the Actions tab; within a couple
minutes you should see a new PR titled `Self-heal: fix build, lint, typecheck, test` with a
body listing what was fixed and confirming full validation.

## Known rough edges

- **File targeting is hardcoded** to this demo repo's known structure (`FIXERS` dict in
  `agent/main.py` hardcodes which file each category should look at). A general-purpose version
  would need to parse tracebacks/lint output to locate implicated files dynamically instead.
- **No handling for multi-file bugs** — each fixer currently only reads/writes the one file it's
  told about; a bug spanning multiple files would need a fixer redesign.
- **Retry budget is small (2)** — tuned for a demo; a real deployment might want more retries
  with a cost/time ceiling instead of a fixed count.
