# Running on macOS: setup, smoke test, live run

Verified in a clean environment with Python 3.12.3 and 3.13 (Linux). macOS uses the same pinned
packages from PyPI. You need Python 3.11+ and `make` (included with the Xcode Command Line Tools).

## 1. Install

Run each line on its own. Do not paste comments: interactive zsh does not treat `#` as a comment.
If conda's `(base)` environment is active, run `conda deactivate` first.

```bash
unzip market-evidence-investigator.zip
cd market-evidence-investigator
make setup PY=python3.12
make test
```

`make setup` creates `.venv`, installs `requirements.lock`, and installs the project code with a
regular (non-editable) install (about 1 minute). `make test` should report all tests passed; it needs
no network or key.

**After any code update**, re-copy the code into `.venv` with `make install`. The install is regular
rather than editable because on one macOS setup the editable link file was ignored and `mei` could
not be imported.

## 2. Configure the API key (local only)

```bash
cp .env.example .env
open -e .env
```

In the editor, set `ANTHROPIC_API_KEY=sk-ant-...` and save.

`.env` is git-ignored and is read only by the application. The key is never printed: the smoke test
shows only its first 7 and last 4 characters, and where it came from.

**If you have also exported `ANTHROPIC_API_KEY` in your shell profile, that value wins** and the smoke
test warns you. Run `unset ANTHROPIC_API_KEY` to use the `.env` value instead.

Optional settings in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `MEI_MODEL_MAIN` / `MEI_MODEL_SMALL` | `claude-sonnet-5-5` / `claude-haiku-5-5` | models for the agent roles / claim auditor |
| `MEI_MAX_COST_USD` | `3.00` | hard spending cap per run; a call is refused if its worst case could exceed it |
| `MEI_MAX_LLM_CALLS` | `60` | call cap per run |
| `MEI_SMOKE_MAX_COST_USD` | `0.50` | cap for the smoke test |
| `MEI_EFFORT_MAIN` / `MEI_EFFORT_SMALL` | `medium` / `low` | thinking effort (affects cost) |

## 3. Smoke test (a few cents)

```bash
.venv/bin/mei smoke
```

Seven checks, each printed as PASS or FAIL:

1. `.env` found and loaded; key source reported
2. both models available to your key (Models API, no token cost)
3. one tiny call per model; tokens and cost recorded
4. structured output on both models
5. a real tool call, executed, with the result sent back (thinking blocks intact)
6. the real LangGraph workflow, up to the planner, which then stops
7. error handling: an invalid model name gives a clear error; the spending cap refuses a call; retries are set

Results are written to `runs/smoke/smoke_report.json`; it contains no key. **If any step fails, stop
and send me that file.**

## 4. Estimate, then the full live investigation

```bash
.venv/bin/mei estimate
make demo-live
```

`mei estimate` makes no API calls and prints a low / central / high cost estimate. `make demo-live`
runs the full investigation with a live terminal view.

At list prices on 2026-11-20 (Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per million tokens) the estimate
is **about $0.63, range $0.29–$1.55**. It is capped at $3.00 by default. The final panel shows the
actual calls, tokens and cost.

Outputs are in `runs/demo_live/`: `report.html`, `ledger.json`, `trace.jsonl`, `state.json`,
`checks.json`, `run_meta.json` and `llm_cache.jsonl`, the recording used for replay.

`make demo-live` refuses to start if `runs/demo_live/` already holds a recording, so a live run never
reuses earlier answers. Move the old folder aside first if you want to record again.

## 5. Verify the replay (no API calls, no cost)

```bash
make verify-replay RUN=runs/demo_live
```

Each output is printed as PASS or FAIL. It replays the recording in a new process and requires state,
ledger, validation checks, trace, both reports and the call and token counts to be identical, then
re-executes every ledger entry from its recorded inputs.

## 6. Send back for review

```bash
cd runs
zip -r demo_live.zip demo_live
cd ..
```

Attach `runs/demo_live.zip`. It contains only synthetic data and model outputs, no key.
`python scripts/check_publishable.py` verifies this before anything is published.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ANTHROPIC_API_KEY is not set` | `.env` missing or the key line is empty; run commands from the repository folder |
| `Model ... not found (404)` | set `MEI_MODEL_MAIN` / `MEI_MODEL_SMALL` to models your account can use |
| `Anthropic rejected the API key (401)` | wrong or revoked key, or no credits on the account |
| `spending cap ... would be exceeded` | raise `MEI_MAX_COST_USD`, or rerun; nothing was sent |
| `RateLimitError after 3 automatic retries` | wait a minute and rerun |
| `ModuleNotFoundError: No module named 'mei'` | run `make install` (re-copies the code into `.venv`) |
| `... already holds a recording` | the output folder has an earlier run; move it aside (`mv runs/demo_live runs/demo_live_old`) |
| `cd: too many arguments` or `command not found: #` | a comment was pasted; run each command alone |
