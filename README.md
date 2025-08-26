# S4U JitBit Tickets — Export and LLM Processing

This repository contains two Python programs that work together to extract closed Jitbit tickets via API and transform them into concise, RAG‑friendly summaries using an LLM (Together.ai).

Programs:
- ticket_relevante_felder.py — Extracts closed tickets from Jitbit via API, cleans text fields, and writes a consolidated JSON file.
- process_tickets_with_llm.py — Sends each ticket to an LLM to classify relevance and summarize problem/solution, writing compact outputs for downstream use (now includes original Subject in the output summaries).

------------------------------------------------------------
## 1) Export closed Jitbit tickets (ticket_relevante_felder.py)

Purpose:
- Connect to your Jitbit instance, paginate through tickets, resolve real TicketIDs, and export closed tickets in selected categories to JitBit_relevante_Tickets.json with all relevant fields, including the entire conversation (kommentare) and attachments.

Configuration:
- Create a .env file and set:
  - JITBIT_API_TOKEN=your_jitbit_bearer_token
- In ticket_relevante_felder.py adjust:
  - jitbit_url — Base URL to your Jitbit installation (e.g., https://support.example.com)
  - ERLAUBTE_KATEGORIEN — Allowed categories list, e.g.: ["Allgemeine Frage", "Fehlermeldung", "Sonstiges"]

Security:
- Do not commit real tokens. Store JITBIT_API_TOKEN only in your local .env and ensure .gitignore excludes it. Never commit .env.

API Endpoints used:
- GET /helpdesk/api/Tickets?count={batch_size}&offset={offset}
  - Used for pagination through issues (returns IssueID).
- GET /helpdesk/api/Ticket/{issue_id}
  - Used to resolve the real TicketID from IssueID.
- GET /helpdesk/api/Comments/{ticket_id} (fallbacks supported: /Comments?ticketId=..., case variants)
  - Loads full conversation history (comments).
- GET /helpdesk/api/Attachments/{ticket_id} (fallbacks attempted: /Attachments?ticketId=..., /Attachments?commentId=..., case variants)
  - Note: Some Jitbit instances return 404 for Attachments endpoints. The exporter therefore also extracts attachment links from HTML in the ticket Body and each comment (href/src), normalizes relative URLs, and deduplicates. Comment-level attachments may be discovered this way even when the API does not expose them.

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
- The script prints stats and error diagnostics (HTTP errors, excluded categories, not-closed statuses). It also offers debug options in the interactive menu to inspect attachment API responses and extracted links for a specific ticket (e.g., ticket 23480 or a custom ID).

Non-interactive CLI (headless runs):
```
# Export all (closed + allowed categories) without prompts
python3 ticket_relevante_felder.py --all --yes

# Export only the first N tickets checked (closed + allowed categories)
python3 ticket_relevante_felder.py --first 100 --yes

# Start from a specific TicketID
python3 ticket_relevante_felder.py --start-id 23000 --yes
```

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
- Aggregate image URLs (from ticket-level and comment-level attachments/HTML) into image_urls for downstream use. The LLM does not handle URLs.

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
  - ticket_id, date, subject, problem, solution, image_urls
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
- The model is explicitly instructed NOT to include URLs; the processor aggregates image URLs into image_urls.

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

CLI reference and examples:

Parameters:
- --input PATH
  - Path to the input JSON produced by the exporter. Supports either an object with top-level "tickets": [...] or a top-level array of ticket objects. Default: JitBit_relevante_Tickets.json
- --output PATH
  - Path to write relevant summaries as a JSON array. Default: Ticket_Data.JSON
- --not-relevant-out PATH
  - Path to write raw “not relevant” tickets as an object: {"tickets": [ ... ]}. Default: not relevant.json
- --limit N
  - Collect only N relevant tickets. The loop continues until N relevant are gathered or input ends; non-relevant are skipped and do not count towards the limit. Default: unlimited
- --max-calls N
  - Safety cap on total LLM calls. Useful for quick tests/cost control. Default: unlimited
- --max-tokens N
  - max_tokens for the LLM response. Default: 3000
- --temperature FLOAT
  - Sampling temperature for the LLM. Default: 0.2
- --start-index K
  - Skip the first K tickets in the chosen order (streaming or newest-first). Default: 0
- --append
  - Append to existing outputs if they exist instead of overwriting. The relevant list will be extended, and not relevant will be merged. Default: off
- --only-ticket-id ID
  - Process a single ticket (by ticket_id) for debugging. Often combine with --limit 1 --max-calls 1
- --newest-first
  - Load the entire file into memory and process tickets in descending ticket_id order. Faster prioritization of new tickets but requires enough RAM

Environment:
- TOGETHER_API_KEY (required) — from .env or your shell env
- LLM_MODEL (preferred) or TOGETHER_MODEL — model id string; defaults to meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo

Basic runs:
- Default input/output paths:
```
python3 process_tickets_with_llm.py
```

- Quick sanity check (limit output volume and cost):
```
python3 process_tickets_with_llm.py --limit 10 --max-calls 20
```

Newest-first and offsets:
- Prioritize newest tickets and collect 200 relevant:
```
python3 process_tickets_with_llm.py --newest-first --limit 200
```

- Resume on newest-first after skipping first 100 newest, then collect 50 relevant:
```
python3 process_tickets_with_llm.py --newest-first --start-index 100 --limit 50
```

Append mode (incremental processing):
- Add 25 more relevant summaries to existing outputs:
```
python3 process_tickets_with_llm.py --append --limit 25
```

Work on specific tickets / diagnostics:
- Process only one ticket by ID:
```
python3 process_tickets_with_llm.py --only-ticket-id 23480 --limit 1 --max-calls 1
```

- Use explicit paths (if you keep inputs/outputs separate):
```
python3 process_tickets_with_llm.py \
  --input JitBit_relevante_Tickets.json \
  --output Ticket_Data.JSON \
  --not-relevant-out "not relevant.json" \
  --limit 50 --max-calls 200
```

Recipes:
- Process the latest N relevant tickets quickly:
```
python3 process_tickets_with_llm.py --newest-first --limit 100 --max-calls 200
```

- Memory-constrained large file (prefer streaming, no newest-first):
```
python3 process_tickets_with_llm.py --limit 300 --max-calls 600
```

- Debug LLM parsing failures (check llm_parse_errors/ for details):
```
python3 process_tickets_with_llm.py --only-ticket-id 12345 --limit 1 --max-calls 1
```

Notes:
- The model is instructed not to output URLs; the processor aggregates image URLs into image_urls automatically from ticket-level and comment-level attachments/HTML.
- If your export is very large, install ijson (pip3 install -U ijson) to enable streaming; avoid --newest-first in that case.
- Schema note (2025-08-24): Ticket_Data.JSON now includes the original "subject" field. When using --append with older files, previous entries might not contain "subject"; regenerate or post-process if uniform schema is required.

Output schemas:

1) Relevant summaries (Ticket_Data.JSON):
```
[
  {
    "ticket_id": 49,
    "date": "2018-11-27T08:15:55.367Z",
    "subject": "Kurzes Betreff-Beispiel",
    "problem": "Markdown summary...",
    "solution": "Markdown summary...",
    "image_urls": ["https://...", "https://..."]
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

------------------------------------------------------------
## 3) Render Jitbit Knowledgebase JSON to a single PDF (kb_to_pdf.py)

Purpose:
- Convert a Jitbit Knowledgebase export (JSON) into a single, nicely formatted PDF (one article per page) with:
  - Subject as title
  - Category and TagString as subheader
  - Converted Body HTML (paragraphs, lists, code/pre, simple tables, inline images)
  - Attachment images rendered after the body
  - Relative URLs resolved via export_info.api_base_url

Dependencies:
```
pip3 install -U reportlab beautifulsoup4 requests pillow
```

Basic usage:
```
# Unauthenticated (public images only)
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o Knowledgebase.pdf
```

Authentication for protected images (recommended for Jitbit):
Many Jitbit instances require authentication to fetch /helpdesk/File/Get/... images (both inline Body & Attachments).
Pass either a cookie header or a cookies file and an appropriate Referer.

Option A: Use browser cookies as a single header
1) Log into your Jitbit in the browser.
2) Open DevTools → Application/Storage → Cookies for your Jitbit domain.
3) Copy relevant cookies (e.g., ASP.NET_SessionId, .ASPXAUTH, jitbitkb).
4) Run:
```
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o Knowledgebase.pdf \
  --cookie "ASP.NET_SessionId=...; .ASPXAUTH=...; jitbitkb=..." \
  --header "Referer: https://support.example.com/"
```

Option B: Use a cookies.txt file (Netscape/Mozilla format)
- Export cookies (for the Jitbit domain) as a standard cookies.txt. Several browser extensions can do this (e.g., “Export cookies.txt”).
- Then:
```
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o Knowledgebase.pdf \
  --cookies-file cookies.txt \
  --header "Referer: https://support.4plan.de/"
```

Flags and behavior:
- --include-body-images true|false
  - Include inline <img> from Body HTML. Default: true
- --include-attachments true|false
  - Include images listed in the Attachments array. Default: true
- --attachments-header true|false
  - Print a small “Anhänge” heading before attachment images. Default: false
- --timeout SECONDS
  - HTTP timeout per image. Default: 12.0
- --require-image-content-type true|false
  - Skip any download whose Content-Type is not image/* (avoids embedding bad responses). Default: false
- --image-placeholder true|false
  - Insert a textual placeholder with a link when an image fails to load. Default: true
- --cookie "name=value; ...", --header "Name: Value", --headers-file headers.json
  - Additional auth/headers to pass to requests.
- --cookies-file PATH
  - Load cookies from a Netscape cookies.txt file (merges into the session).
- --verbose true|false
  - Log each image request and decisions to stderr. Helpful for diagnosing auth issues. Default: false

Auth/Referer details:
- The script automatically sets the HTTP Referer per article to the article’s Url (art["Url"]) while processing that article. Many Jitbit setups require a consistent Referer for /helpdesk/File/Get/… endpoints.
- If you still get HTML login pages for image URLs, provide cookies as shown above.

Duplicate suppression:
- Attachment images are deduplicated per article by normalized URL.
- Body and Attachments may still contain the same image — this will render twice if included in both; typically attachments are images referenced in the body, so consider --include-attachments false if you prefer only inline rendering.

Placeholders and warnings:
- When an image fails to load or the server returns an HTML login page, the script:
  - Emits a warning to stderr (run with --verbose for more detail).
  - Inserts a placeholder Paragraph with a clickable link to the image.
  - Example warning:
    “[WARN] HTML page returned for https://support.example.com/helpdesk/File/Get/26355. If this endpoint is protected, pass --cookie/--cookies-file and a proper Referer.”

Examples:
- Minimal (might show placeholders for protected images):
```
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o Knowledgebase.pdf
```

- With cookie header and explicit Referer:
```
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o Knowledgebase.pdf \
  --cookie "ASP.NET_SessionId=...; .ASPXAUTH=...; jitbitkb=..." \
  --header "Referer: https://support.4plan.de/" \
  --attachments-header true --verbose true
```

- With cookies.txt and stricter content-type check:
```
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o Knowledgebase.pdf \
  --cookies-file cookies.txt \
  --header "Referer: https://support.4plan.de/" \
  --require-image-content-type true \
  --attachments-header true --verbose true
```

Notes & troubleshooting:
- Relative image URLs in Body (e.g., /helpdesk/File/Get/26355) are automatically resolved via export_info.api_base_url in the JSON.
- If placeholders appear for protected images:
  - Make sure you passed valid cookies for the same domain.
  - Verify the Referer is correct (default per article; can be overridden with --header).
  - Use --verbose to inspect Content-Type and warnings.
- The script retries once on transient download errors.
- For authenticated sites with aggressive CSRF or dynamic tokens, consider exporting a cookies.txt immediately after logging-in and re-running quickly.
