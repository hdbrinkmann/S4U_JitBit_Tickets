# S4U JitBit Tickets — Export and LLM Processing

This repository contains two Python programs that work together to extract closed Jitbit tickets via API and transform them into concise, RAG‑friendly summaries using an LLM (Together.ai).

Programs:
- ticket_relevante_felder.py — Extracts closed tickets from Jitbit via API, cleans text fields, and writes a consolidated JSON file.
- process_tickets_with_llm.py — Sends each ticket to an LLM to classify relevance and summarize problem/solution, writing compact outputs for downstream use.

------------------------------------------------------------
## 1) Export closed Jitbit tickets (ticket_relevante_felder.py)

Purpose:
- Connect to your Jitbit instance, paginate through tickets, resolve real TicketIDs, and export closed tickets in selected categories to JitBit_relevante_Tickets.json with all relevant fields, including the entire conversation (kommentare) and attachments.

Configuration:
- Open ticket_relevante_felder.py and adjust:
  - api_token — Your Jitbit API token (Bearer token)
  - jitbit_url — Base URL to your Jitbit installation (e.g., https://support.example.com)
  - ERLAUBTE_KATEGORIEN — Allowed categories list, e.g.: ["Allgemeine Frage", "Fehlermeldung", "Sonstiges"]

Security:
- Do not commit real tokens. Keep ticket_relevante_felder.py private or refactor to load from .env. Ensure .gitignore prevents secrets from being committed.

API Endpoints used:
- GET /helpdesk/api/Tickets?count={batch_size}&offset={offset}
  - Used for pagination through issues (returns IssueID).
- GET /helpdesk/api/Ticket/{issue_id}
  - Used to resolve the real TicketID from IssueID.
- GET /helpdesk/api/Comments/{ticket_id}
  - Loads full conversation history (comments).
- GET /helpdesk/api/Attachments/{ticket_id}
  - Loads all ticket-level attachments.

Filtering logic:
- Only tickets with Status == "Geschlossen".
- Only tickets where CategoryName is in ERLAUBTE_KATEGORIEN.

HTML cleanup:
- Strips common HTML tags, <br>, <div>, <p>, and decodes HTML entities so Body and comments are readable.

Rate limiting:
- Built-in pause and retry handling. Pagination uses batches of 300 and observes rate limits.

Interactive run:
```
python3 ticket_relevante_felder.py
```
- You will be prompted to:
  - Fetch all tickets and filter closed ones
  - Process a subset, the first 10, or start from a given TicketID
- Output file: JitBit_relevante_Tickets.json
- The script prints stats and error diagnostics (HTTP errors, excluded categories, not-closed statuses).

Test single ticket:
```
# Example IDs in the script
python3 ticket_relevante_felder.py
# Choose test option and enter the given example ID or your own
```

Output structure (JitBit_relevante_Tickets.json):
- Either a top-level object with "tickets": [...] (default of the exporter), or potentially a top-level array if you post-process later. The processor supports both.

Ticket item schema:
```
{
  "ticket_id": int,
  "CategoryName": str,
  "IssueDate": str,       // ISO string from Jitbit
  "Subject": str,
  "Body": str,            // cleaned from HTML
  "Status": "Geschlossen",
  "Url": str,             // link to the ticket
  "Attachments": [
    { "FileName": str, "Url": str, "Size": int }
  ],
  "kommentare": [
    {
      "CommentDate": str,
      "Body": str,        // cleaned from HTML
      "UserName": str,
      "Attachments": [
        { "FileName": str, "Url": str, "Size": int }
      ]
    }
  ]
}
```

------------------------------------------------------------
## 2) Analyze tickets with LLM (process_tickets_with_llm.py)

Purpose:
- Build an LLM prompt from each ticket’s subject, body, and comments.
- Ask the LLM to decide if the ticket has a real technical problem and a concrete solution (not trivial requests).
- For relevant tickets, generate a concise problem and solution summary.
- Aggregate all attachment URLs found (ticket-level and comment-level) into attachment_urls for downstream use.

Environment:
- Create a .env file in the repo root:
```
TOGETHER_API_KEY=your_together_api_key_here
# Optional (defaults to meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo if unset)
LLM_MODEL=meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo
# Optional fallback:
# TOGETHER_MODEL=...
```
- Ensure .gitignore excludes .env.

Dependencies:
```
pip3 install -U requests python-dotenv ijson
```
- ijson enables streaming of very large input JSON files.

Input:
- By default reads JitBit_relevante_Tickets.json produced by the exporter.
- Accepts either:
  - An object with top-level "tickets": [...]
  - A raw top-level array [...] of ticket objects with the same schema.

Outputs:
- Ticket_Data.JSON — Array with compact summaries of relevant tickets:
  - ticket_id, date, problem, solution, attachment_urls
- not relevant.json — An object with "tickets": [ ...raw ticket objects... ] for manual review later.

LLM Output Schema (enforced in prompt):
- The LLM must output only this JSON object per call:
```
{
  "ticket_id": <int>,
  "date": "<iso-or-original-date>",
  "problem": "<string, markdown allowed>",
  "solution": "<string, markdown allowed>"
}
```
- The model is explicitly instructed NOT to include URLs; the script aggregates URLs into attachment_urls.

Robust JSON parsing:
- Removes Markdown code fences (``` / ```json).
- Extracts the first top-level JSON object with string-aware brace matching.
- Cleans control characters and trailing commas.
- On parse failure, writes diagnostics to llm_parse_errors/ticket_<id>_idx_<n>.txt (includes raw LLM output and prompt tail).

Key Flags:
- --newest-first
  - Loads the entire input into memory and processes tickets in descending ticket_id order (prioritizes newest tickets).
- --limit N
  - Collect only N relevant tickets (limit counts relevant tickets only).
- --max-calls N
  - Safety cap on total LLM calls.
- --start-index K
  - Skip the first K tickets in the chosen order (streaming mode or sorted mode).
- --append
  - Append to existing outputs instead of overwriting.
- --only-ticket-id ID
  - Process only a single ticket for debugging.

Common runs:
- Basic (default input/output paths):
```
python3 process_tickets_with_llm.py
```

- Process newest tickets first and collect 200 relevant summaries:
```
python3 process_tickets_with_llm.py --newest-first --limit 200
```

- Quick test: limit relevant outputs and cap API calls:
```
python3 process_tickets_with_llm.py --limit 10 --max-calls 20
```

- Resume from an offset in newest-first order (skip first 100 newest, then collect 50 relevant):
```
python3 process_tickets_with_llm.py --newest-first --start-index 100 --limit 50
```

- Append to existing outputs:
```
python3 process_tickets_with_llm.py --append --limit 25
```

- Explicit paths:
```
python3 process_tickets_with_llm.py \
  --input JitBit_relevante_Tickets.json \
  --output Ticket_Data.JSON \
  --not-relevant-out "not relevant.json" \
  --limit 50 --max-calls 200
```

- Process only one ticket by ID (diagnostics):
```
python3 process_tickets_with_llm.py --only-ticket-id 49 --limit 1 --max-calls 1
```

Output schemas:

1) Relevant summaries (Ticket_Data.JSON):
```
[
  {
    "ticket_id": 49,
    "date": "2018-11-27T08:15:55.367Z",
    "problem": "Markdown summary...",
    "solution": "Markdown summary...",
    "attachment_urls": ["https://...", "https://..."]
  },
  ...
]
```

2) Not relevant tickets (not relevant.json):
```
{
  "tickets": [
    { ...raw ticket object... },
    ...
  ]
}
```

Performance notes:
- Streaming mode:
  - If --newest-first is NOT used, the script attempts streaming via ijson (install recommended).
  - Falls back to json.load if ijson is unavailable (loads fully into memory).
- Sorted newest-first:
  - --newest-first loads all tickets into memory and sorts by ticket_id desc. Ensure adequate RAM for very large datasets.

Troubleshooting:
- Missing Together API key:
  - Ensure .env contains TOGETHER_API_KEY.
- LLM parse errors:
  - Inspect files under llm_parse_errors/.
  - Re-run with --only-ticket-id to isolate.
- Slow or rate-limited:
  - Lower --limit during tests, and set --max-calls.
- Memory:
  - Avoid --newest-first and install ijson to enable streaming.

Repository outputs:
- JitBit_relevante_Tickets.json — Produced by ticket_relevante_felder.py (exporter).
- Ticket_Data.JSON — Produced by process_tickets_with_llm.py (relevant summaries).
- not relevant.json — Produced by process_tickets_with_llm.py (raw not-relevant tickets).
