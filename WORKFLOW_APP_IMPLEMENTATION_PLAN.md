# Workflow App — Implementation Plan (CLI + Web UI)

Important constraint: The web UI must not bind to port 8000. The app will default to 127.0.0.1:8787 and allow a configurable port.

---

## 1) Objectives and Scope

- Provide a single application (CLI and a simple modern Web UI) that orchestrates the full end‑to‑end workflows:
  - Jitbit flow
    1) Ask for relevant parameters (at least start TicketID)
    2) Export closed tickets (≥ start TicketID) to JSON
    3) Export Jitbit Knowledge Base to JSON (always)
    4) Process tickets with LLM to generate Ticket_Data JSON
    5) Generate DOCX for tickets
    6) Generate DOCX for knowledge base
  - Jira flow
    1) Ask for relevant parameters (project SUP|TMS and resolved-after date, optional resolved-before)
    2) Export resolved tickets to JSON
    3) Process tickets with LLM to generate Ticket_Data JSON
    4) De-duplicate Ticket_Data JSON
    5) Generate DOCX for tickets
- The Q&A generation workflow is explicitly out of scope for this app (per requirements).
- A modern, easy-to-use UI with:
  - Environment validation checklist (tokens, base URLs, LLM credentials)
  - Forms for both flows
  - Start/stop run controls, live log view, artifact links
  - Idempotent behavior: skip/overwrite toggles, safe re-runs
- Everything runs locally; external calls are to APIs (Jitbit/Jira) and LLM provider (Scaleway), as the current scripts already do.

---

## 2) Existing Scripts and Contracts (Ground Truth)

These scripts are already present and define IO schema and CLI options:

- Jitbit tickets exporter: `ticket_relevante_felder.py`
  - Interactive and non-interactive modes
  - Writes: `JitBit_relevante_Tickets.json` (object with tickets[])
- Jitbit KB exporter: `kb_export_json.py`
  - `--out JitBit_Knowledgebase.json --yes`
- Jira exporter: `jira_relevant_tickets.py`
  - Requires either `--limit` or `--resolved-after`
  - Prefer explicit `--export JIRA_relevante_Tickets.json`
  - Use JQL: `project=SUP|TMS order by resolutiondate DESC`
- LLM processing: `process_tickets_with_llm.py`
  - Inputs: Jitbit or Jira export (object with tickets[] or a top-level array)
  - Defaults: `Ticket_Data.JSON` and `not relevant.json` (we’ll override names)
- Deduplication: `scripts/dedupe_tickets.py`
  - Inputs: Ticket_Data JSON (with subject/problem/solution)
  - Outputs: `tickets_dedup.json`, `duplicate_groups.json`, `needs_review.csv`
- DOCX generation:
  - Tickets: `tickets_to_docx.py` → DOCX files in a directory, 50 tickets per DOCX by default
  - Knowledge base: `kb_to_docx.py` → single `Knowledgebase.docx`

---

## 3) Naming Conventions and Output Paths

To avoid collisions and keep artifacts separated per source, the orchestrator will use explicit filenames:

- Jitbit flow:
  - Export tickets: `JitBit_relevante_Tickets.json`
  - LLM outputs:
    - Relevant summaries: `Ticket_Data_Jitbit.json`
    - Not-relevant: `Not_Relevant_Jitbit.json`
  - DOCX (tickets): `documents/jitbit/` (batch files)
  - KB JSON: `JitBit_Knowledgebase.json`
  - KB DOCX: `documents/jitbit/Knowledgebase.docx`

- Jira flow:
  - Export tickets: `JIRA_relevante_Tickets.json`
  - LLM outputs:
    - Relevant summaries: `Ticket_Data_Jira.json`
    - Not-relevant: `Not_Relevant_Jira.json`
  - Deduplication:
    - Canonical: `tickets_dedup_Jira.json`
    - Clusters: `duplicate_groups_Jira.json`
    - Gray-zone review: `needs_review_Jira.csv`
  - DOCX (tickets): `documents/jira/` (batch files)

Note: We will pass explicit `--input/--output` arguments to the scripts, never relying on defaults that may overlap.

---

## 4) Application Architecture

Language: Python 3.x

- Orchestrator package: `workflow_app/`
  - `config.py` — constants, file names, defaults, port configuration (default 8787), and environment variable names
  - `envcheck.py` — environment validation functions (presence of required tokens/URLs)
  - `steps.py` — thin wrappers that call the existing scripts using `subprocess`, stream stdout/stderr to log
    - Includes helpers for “skip existing” and “overwrite” logic
  - `flows.py` — high-level flow orchestration
    - `run_jitbit_flow(params, run_dir, options)`
    - `run_jira_flow(params, run_dir, options)`
  - `logging.py` — unify per-run logging (write to run-scoped log files)
  - `util.py` — run directory creation (`runs/YYYYMMDD-HHMMSS-...`), artifact linking/copying, log tailing, JSON validation
- CLI: `cli.py` using Typer
  - Commands:
    - `workflow env-check`
    - `workflow run-jitbit --start-id 23000 [options]`
    - `workflow run-jira --project SUP --resolved-after 2025-01-01 [options]`
- Web UI: FastAPI + Jinja2 + HTMX + Tailwind (CDN for dev)
  - Endpoints:
    - `GET /` → landing page (env status + flow cards)
    - `GET /jitbit` → form
    - `POST /jitbit/start` → starts background job, redirect to `/runs/{id}`
    - `GET /jira` → form
    - `POST /jira/start` → starts background job, redirect to `/runs/{id}`
    - `GET /runs/{id}` → run dashboard (step states, artifacts, tail of log)
    - `GET /runs/{id}/log?offset=` → incremental log tail (polled via HTMX)
  - Background jobs: `ThreadPoolExecutor` (one thread per run), state persisted to `runs/{id}/status.json`

Port and binding policy:
- Default bind: `127.0.0.1:8787` (never 8000)
- Configurable via:
  - ENV var: `WORKFLOW_APP_PORT` (e.g., 8787)
  - CLI flag (web): `--port 8787`
- On startup, if desired, check availability and optionally increment to the next free port in `[8787, 8788, 8789]` when `--auto-port` is enabled.

---

## 5) Web UI (UX) Details

- Landing page: Shows environment check results:
  - Jitbit: `JITBIT_API_TOKEN`, `JITBIT_BASE_URL`
  - Jira: `JIRA_EMAIL`, `JIRA_API_TOKEN`
  - LLM: `SCW_SECRET_KEY`|`SCW_API_KEY`, `SCW_OPENAI_BASE_URL`, `LLM_MODEL` (optional)
- Flow forms:
  - Jitbit:
    - Start TicketID: integer (required)
    - Advanced (collapsed):
      - LLM `--limit`, `--max-calls`, `--newest-first`, `--save-interval`
      - Flags: Skip existing outputs (default ON), Overwrite (off), Append (off)
  - Jira:
    - Project: radio SUP (default) or TMS
    - Resolved-after (YYYY-MM-DD): required
    - Resolved-before: optional
    - Advanced:
      - Exporter: `--limit`, `--append`, `--progress`
      - LLM: `--limit`, `--max-calls`
      - Dedup: thresholds (0.84 / 0.78 defaults)
      - Flags: Skip existing outputs, Overwrite
- Run dashboard:
  - Timeline of steps with current state (pending/running/success/fail, timestamps, durations)
  - Live log tail (HTMX polling)
  - Artifact panel with links (open folder, or show list of emitted files)
  - Retry failed step (if we provide step granularity) or Re-run
- Styling:
  - Tailwind CSS (CDN link sufficient for internal use)
  - Minimal JS: HTMX for form posts and log polling

---

## 6) Detailed Step Mapping

Jitbit Flow
1. Validate environment for Jitbit and LLM
2. Export tickets:
   ```
   python3 ticket_relevante_felder.py --start-id {START_ID} --yes
   # writes: JitBit_relevante_Tickets.json
   ```
3. Export KB (always):
   ```
   python3 kb_export_json.py --out JitBit_Knowledgebase.json --yes
   ```
4. Process with LLM:
   ```
   python3 process_tickets_with_llm.py \
     --input JitBit_relevante_Tickets.json \
     --output Ticket_Data_Jitbit.json \
     --not-relevant-out Not_Relevant_Jitbit.json \
     [--limit N] [--max-calls M] [--append] [--newest-first] [--save-interval 50]
   ```
5. Tickets → DOCX:
   ```
   python3 tickets_to_docx.py \
     --input Ticket_Data_Jitbit.json \
     --output-dir documents/jitbit \
     --verbose true
   ```
6. KB → DOCX:
   ```
   python3 kb_to_docx.py \
     --input JitBit_Knowledgebase.json \
     --output documents/jitbit/Knowledgebase.docx
   ```

Jira Flow
1. Validate environment for Jira and LLM
2. Export Jira (project + from-date; SUP default):
   ```
   JQL="project={PROJECT} order by resolutiondate DESC"
   python3 jira_relevant_tickets.py \
     --jql "$JQL" \
     --resolved-only \
     --resolved-after {YYYY-MM-DD} \
     [--resolved-before YYYY-MM-DD] \
     [--limit N] [--append] [--progress] \
     --export JIRA_relevante_Tickets.json
   ```
3. Process with LLM:
   ```
   python3 process_tickets_with_llm.py \
     --input JIRA_relevante_Tickets.json \
     --output Ticket_Data_Jira.json \
     --not-relevant-out Not_Relevant_Jira.json \
     [--limit N] [--max-calls M] [--append]
   ```
4. Deduplicate (recommended):
   ```
   python3 scripts/dedupe_tickets.py \
     --input Ticket_Data_Jira.json \
     --out tickets_dedup_Jira.json \
     --groups-out duplicate_groups_Jira.json \
     --review-out needs_review_Jira.csv \
     --threshold 0.84 \
     --threshold-low 0.78
   ```
5. Tickets → DOCX (use deduped file by default):
   ```
   python3 tickets_to_docx.py \
     --input tickets_dedup_Jira.json \
     --output-dir documents/jira \
     --verbose true
   ```

Skip/Overwrite behavior:
- If “Skip existing” is enabled, a step is skipped when its expected output exists and passes a quick validation (non-empty file, and JSON where applicable).
- If “Overwrite” is enabled, the step runs regardless of existing output.
- Jira exporter additionally supports `--append` to extend an export.

---

## 7) Configuration and Environment

Required ENV keys (read from `.env` in repo root):
- Jitbit:
  - `JITBIT_API_TOKEN`
  - `JITBIT_BASE_URL` (e.g., https://support.example.com/helpdesk)
- Jira:
  - `JIRA_EMAIL`
  - `JIRA_API_TOKEN`
- LLM (Scaleway):
  - `SCW_SECRET_KEY` or `SCW_API_KEY`
  - `SCW_OPENAI_BASE_URL` (e.g., https://api.scaleway.ai/v1/chat/completions)
  - Optional: `LLM_MODEL` (fallback: Meta-Llama-3.1-70B-Instruct-Turbo per script)
- Tickets → DOCX (Jira images):
  - Optional: `JIRA_EMAIL`, `JIRA_API_TOKEN` (already above, reused)
- App (Web UI):
  - `WORKFLOW_APP_PORT` (default 8787, not 8000)
  - `WORKFLOW_APP_HOST` (default 127.0.0.1)
  - Optionally `WORKFLOW_APP_AUTO_PORT=1` to try 8787→8788→8789

---

## 8) Dependencies

Additions to existing requirements:
- CLI: `typer`
- Web: `fastapi`, `uvicorn`, `jinja2`, `python-multipart` (form posts)
- UI: Tailwind CSS via CDN (no build chain needed for v1)
- Orchestrator: standard lib `subprocess`, `concurrent.futures`, `json`, `pathlib`, `datetime`

Install example:
```
pip3 install -U fastapi uvicorn typer jinja2 python-multipart
```

---

## 9) Logging, Observability, Robustness

- Per run directory: `runs/YYYYMMDD-HHMMSS-{flow}-{project?}/`
  - `params.json` — captured input parameters
  - `status.json` — step-by-step state with timestamps/durations
  - `flow.log` — combined stdout/stderr from all subprocess calls
  - `artifacts/` — links/copies to generated files
- Redact secrets in logs (no tokens or Authorization headers)
- Heartbeats and progress lines from exporters are included verbatim
- Quick integrity checks:
  - JSON outputs parsed to verify shape where practical
  - Non-empty file checks for DOCX
- Error handling:
  - On step failure: mark status, preserve partial artifacts, surface last N lines of log in UI

---

## 10) Security and Privacy

- `.env` remains local and is git-ignored (already in repo)
- No credentials printed or stored in run params (only booleans/paths)
- External traffic is limited to APIs already used by the scripts and Scaleway LLM/embeddings endpoints

---

## 11) Implementation Phases

Phase 1 (MVP):
- `workflow_app` package:
  - `envcheck.py`, `config.py`, `steps.py`, `flows.py`, `logging.py`, `util.py`
- CLI `cli.py`:
  - `env-check`, `run-jitbit`, `run-jira`
- Web UI minimal:
  - FastAPI app with routes, HTMX-based forms
  - Run dashboard with log tailing
- Default port 8787 with `--port` and `WORKFLOW_APP_PORT` support

Phase 2:
- Run history page and artifacts explorer
- Per-step re-run from failure point
- Advanced options surfaced in UI (thresholds, append, overwrite)
- Optional: automatic port fallback when busy (8787→8788→8789)

Phase 3:
- Optional in-UI `.env` editor (masked inputs) with “Test connection”
- SSE/WebSocket for live logs (replace polling)
- Export a “bundle.zip” of artifacts per run
- Project dropdown for Jira with small cached list (if desired)

---

## 12) Acceptance Criteria

- Jitbit flow:
  - Given a start TicketID, produces:
    - `JitBit_relevante_Tickets.json`
    - `JitBit_Knowledgebase.json`
    - `Ticket_Data_Jitbit.json`
    - DOCX files under `documents/jitbit/` including `Knowledgebase.docx`
  - Progress and logs visible in web UI; runs successfully with default settings
- Jira flow:
  - Given project (SUP/TMS) and resolved-after date, produces:
    - `JIRA_relevante_Tickets.json`
    - `Ticket_Data_Jira.json`
    - `tickets_dedup_Jira.json`
    - DOCX files under `documents/jira/`
  - Progress and logs visible; thresholds configurable
- Web UI never binds to port 8000; default is 8787
- CLI parity with web forms

---

## 13) Risks and Mitigations

- Long-running exports / rate limiting:
  - Rely on scripts’ built-in retries/backoffs; show heartbeat/progress
- Large JSON files:
  - Scripts support streaming where applicable; UI encourages limits during tests
- Protected images:
  - UI clearly warns when tokens are missing; DOCX may render placeholders
- Schema drift:
  - We fix our own output names to avoid any default conflicts; validation checks for expected shapes

---

## 14) Testing Strategy

- Unit-ish: validate `steps.py` command construction and skip/overwrite logic (dry-run mode)
- Integration: run small flows with limits (e.g., `--limit` on Jira exporter; `--limit` and `--max-calls` on LLM)
- Negative tests:
  - Missing env vars → env check fails and blocks run
  - Busy port → demonstrate configurable port; document `--port` usage
- Artifacts validation:
  - JSON parsing of all generated JSONs
  - Existence and non-empty DOCX files
- Manual verification:
  - Visual check of generated DOCX structure/images for both Jitbit and Jira

---

## 15) Developer Notes and Conventions

- No modifications to existing scripts unless defects are discovered; the orchestrator treats them as black boxes
- All paths relative to repository root; orchestrator runs from that CWD
- Explicit command flags over defaults to reduce ambiguity
- Consistent casing for filenames as listed in this plan
- Port policy: never 8000; default 8787; allow `--port` and ENV override

---

## 16) Example CLI Usage (No execution performed here)

- Env check:
  ```
  python3 cli.py env-check
  ```
- Run Jitbit flow:
  ```
  python3 cli.py run-jitbit --start-id 23000 --skip-existing true --overwrite false
  ```
- Run Jira flow (SUP since a date):
  ```
  python3 cli.py run-jira --project SUP --resolved-after 2025-01-01 --skip-existing true
  ```
- Web UI on 8787:
  ```
  uvicorn web.main:app --host 127.0.0.1 --port 8787
  ```

---

## 17) Next Steps

- Confirm this plan (architecture, filenames, UX, port policy)
- After approval:
  1) Scaffold `workflow_app` package and CLI skeleton (no business logic yet)
  2) Implement `envcheck.py` and `config.py`
  3) Implement `steps.py` subprocess wrappers and minimal `flows.py`
  4) Add FastAPI app with two forms and run dashboard (bind to 8787 by default)
  5) Smoke test end-to-end with small limits; validate outputs and logs
  6) Iterate on UI usability (skip/overwrite toggles, thresholds, append)
