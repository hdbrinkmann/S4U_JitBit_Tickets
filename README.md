# S4U JitBit Tickets — Export and LLM Processing

This repository contains Python programs that work together to extract Jitbit tickets and knowledge base articles via API, transform them into concise summaries using an LLM (Together.ai), and render them as PDF/DOCX documents.

## Main Programs:
- **ticket_relevante_felder.py** — Extracts closed tickets from Jitbit via API, cleans text fields, and writes a consolidated JSON file.
- **process_tickets_with_llm.py** — Sends each ticket to an LLM to classify relevance and summarize problem/solution, writing compact outputs for downstream use (includes original Subject in the output summaries).
- **kb_export_json.py** — Exports Jitbit Knowledge Base articles as JSON with BBCode to Markdown conversion and attachment extraction.
- **kb_to_docx.py** — Renders Knowledge Base JSON to DOCX format with images and formatting.
- **tickets_to_docx.py** — Converts ticket summaries to DOCX format.

## Utility Scripts:
- **scripts/jitbit_fetch_attachment.py** — Standalone utility to fetch individual Jitbit attachments via API.
- **scripts/test_llm_parse_errors.py** — Test script for debugging LLM parsing issues.

## Reference Files:
- **sample_ticket_data.json** — Example ticket data format for testing.
- **Process_with_LLM.md** — Design document describing the LLM processing approach.

## Installation

Install the required dependencies:

```bash
pip3 install -U reportlab beautifulsoup4 requests pillow python-dotenv python-docx ijson
```

Or use the provided requirements file:

```bash
pip3 install -r requirements.txt
# Note: You may also want to install ijson for large file streaming support:
pip3 install -U ijson
```

## Environment Setup

Create a `.env` file in the repository root:

```bash
# Required for ticket/KB export and API operations
JITBIT_API_TOKEN=your_jitbit_bearer_token_here
JITBIT_BASE_URL=https://support.example.com

# Required for LLM processing 
TOGETHER_API_KEY=your_together_api_key_here

# Optional LLM model override (defaults to Meta-Llama-3.1-70B-Instruct-Turbo)
LLM_MODEL=meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo
```

**Security Note**: Never commit the `.env` file to version control. Ensure `.env` is included in your `.gitignore`.

------------------------------------------------------------
## 0) Export Jitbit Knowledge Base (kb_export_json.py)

Purpose:
- Export Jitbit Knowledge Base articles as JSON with comprehensive BBCode to Markdown conversion.
- Extract attachments from both API endpoints and embedded HTML/BBCode content.
- Support category filtering and incremental exports.
- Convert BBCode formatting to Markdown while preserving text readability.

Features:
- **BBCode Processing**: Converts common BBCode tags ([b], [i], [code], [img], [url], etc.) to Markdown equivalents.
- **Attachment Extraction**: Discovers attachments from API and embedded content (href/src attributes, plain URLs).
- **Category Support**: Export all articles or filter by specific KB categories.
- **Rate Limiting**: Built-in retry logic and gentle rate limiting to avoid API throttling.
- **Robust URL Normalization**: Converts relative URLs to absolute using the Jitbit base URL.

Configuration:
- Set `JITBIT_API_TOKEN` and optionally `JITBIT_BASE_URL` in your `.env` file.
- The script defaults to `https://support.4plan.de` but can be overridden via environment variables.

Basic usage:

```bash
# Export all KB articles
python3 kb_export_json.py --out JitBit_Knowledgebase.json --yes

# Export specific category only  
python3 kb_export_json.py --category-id 5 --out Category_5_KB.json --yes

# Test run with first 10 articles
python3 kb_export_json.py --first 10 --out KB_Sample.json --yes
```

Interactive mode:
```bash
python3 kb_export_json.py
```

CLI Options:
- `--category-id N`: Export only articles from KB category N
- `--first N`: Limit export to first N articles (for testing)
- `--out PATH`: Output JSON file path (default: JitBit_Knowledgebase.json)
- `--yes`: Skip confirmation prompts (useful for automated runs)

Output Structure:
```json
{
  "export_info": {
    "timestamp": "2024-01-15 14:30:00",
    "total_articles": 150,
    "total_attachments": 75,
    "api_base_url": "https://support.4plan.de",
    "category_filter": null,
    "limited_to_first_n": null,
    "export_duration_seconds": 45.2
  },
  "articles": [
    {
      "ArticleId": 123,
      "Subject": "How to configure XYZ",
      "Body": "Cleaned plaintext content...",
      "BodyMarkdown": "Markdown version with **formatting**...",
      "ForTechsOnly": false,
      "CategoryID": 5,
      "CategoryName": "Configuration",
      "TagString": "config, setup",
      "Tags": ["config", "setup"],
      "UrlId": "how-to-configure-xyz",
      "DateCreated": "2023-12-01T10:00:00",
      "LastUpdated": "2024-01-10T15:30:00", 
      "Url": "https://support.4plan.de/kb/article/123",
      "Attachments": [
        {
          "FileName": "screenshot.png",
          "Url": "https://support.4plan.de/helpdesk/File/Get/456",
          "Size": 125000
        }
      ]
    }
  ]
}
```

BBCode Support:
- `[b]bold[/b]` → `**bold**`
- `[i]italic[/i]` → `_italic_`  
- `[code]...[/code]` → ` ```...``` `
- `[img]url[/img]` → `![](url)`
- `[url]link[/url]` → `<link>`
- `[url=link]text[/url]` → `[text](link)`
- `[quote]...[/quote]` → blockquote format
- List items `[*]` → `- ` (bullet points)

API Endpoints Used:
- `GET /helpdesk/api/Articles[?categoryId=N]` — Article overview
- `GET /helpdesk/api/Article/{id}` — Detailed article data
- `GET /helpdesk/api/categories` — Category enumeration

Notes:
- The export includes both cleaned plaintext (`Body`) and formatted Markdown (`BodyMarkdown`) versions.
- Attachment discovery includes API attachments plus content extracted from HTML/BBCode in article bodies.
- Articles are processed with a small delay (0.12s) to be respectful to the API.
- Large exports may take several minutes depending on article count and attachment discovery.

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
- Build an LLM prompt from each ticket's subject, body, and comments.
- Ask the LLM to decide if the ticket has a real technical problem and a concrete solution (not trivial requests).
- For relevant tickets, generate a concise problem and solution summary.
- Aggregate image URLs (from ticket-level and comment-level attachments/HTML) into image_urls for downstream use. The LLM does not handle URLs.
- **Automatically prefix all ticket IDs with "S4U_"** in the output format (e.g., ticket ID 98 becomes "S4U_98").

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
  - ticket_id (with S4U_ prefix), date, subject, problem, solution, image_urls
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
- **Note**: The processor automatically adds "S4U_" prefix to ticket_id in the final output, so LLM returns numeric IDs but output contains strings like "S4U_98".

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
    "ticket_id": "S4U_49",
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

------------------------------------------------------------
## 4) Render Ticket summaries to DOCX (tickets_to_docx.py)

Purpose:
- Convert Ticket_Data.JSON into DOCX files with configurable tickets per file:
  - Groups tickets into batches (default: 50 tickets per DOCX file)
  - Each ticket rendered with one page per ticket:
    - Subject as heading
    - Meta line with Ticket-ID and date
    - "Problem" and "Lösung" sections
    - Optional inline images from image_urls (API-first for Jitbit-protected attachments)

Dependencies:
- Added: python-docx (already listed in requirements.txt)

Basic usage:
```bash
# Default: 50 tickets per DOCX file
python3 tickets_to_docx.py --input Ticket_Data.JSON

# Custom: 25 tickets per DOCX file
python3 tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 25

# Original behavior: one ticket per file
python3 tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 1
```

Options:
- `--input PATH, -i PATH`: Path to JSON file with ticket array (default: Ticket_Data.JSON)
- `--output-dir PATH, -o PATH`: Output directory for DOCX files (default: documents)
- `--tickets-per-file N, -t N`: Number of tickets per DOCX file (default: 50)
- `--page-size {A4,LETTER}`: Page size (default: A4)
- `--margin POINTS`: Margins in points (default: 36 ≈ 0.5")
- `--include-images true|false`: Include images from image_urls[] (default: true)
- `--image-placeholder true|false`: Insert placeholder when image fails (default: true)
- `--timeout SECONDS`: HTTP timeout for image downloads (default: 15.0)
- `--base-url URL`: Override JITBIT_BASE_URL from environment
- `--token TOKEN`: Override JITBIT_API_TOKEN from environment
- `--verbose true|false`: Enable detailed logging

File naming:
- **Multiple tickets per file**: `tickets_0001-0050_batch_001.docx`, `tickets_0051-0100_batch_002.docx`, etc.
- **Single ticket per file** (--tickets-per-file 1): `ticket_{id}_{safe_subject}.docx`

Authentication for protected images:
- Set JITBIT_API_TOKEN in .env and JITBIT_BASE_URL to your instance base (e.g., https://support.example.com/helpdesk).
- The script resolves relative URLs and fetches attachments via /helpdesk/api/attachment?id=... (falls back to /api/attachment?id=...).

Formatting notes:
- Supports simple inline bold using **bold** or <b>bold</b> in Problem/Solution text.
- Simple lists are supported when lines start with -, *, • or 1., 2).

Examples:
```bash
# Process with default settings (50 tickets per file)
python3 tickets_to_docx.py --input Ticket_Data.JSON --verbose true

# Create smaller files with 10 tickets each
python3 tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 10 --output-dir output/

# Maintain original behavior (one file per ticket)
python3 tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 1

# Custom output directory with authentication
python3 tickets_to_docx.py \
  --input Ticket_Data.JSON \
  --output-dir documents/tickets/ \
  --tickets-per-file 25 \
  --include-images true \
  --verbose true
```

------------------------------------------------------------
## 5) Render Jitbit Knowledgebase JSON to a single DOCX (kb_to_docx.py)

Purpose:
- Convert a Jitbit Knowledgebase export (JSON) into a single, nicely formatted DOCX (one article per page) with:
  - Subject as title
  - Category and TagString as subheader
  - Converted Body HTML (paragraphs, lists, code/pre, simple tables, inline images)
  - Attachment images rendered after the body
  - Relative URLs resolved via export_info.api_base_url or JITBIT_BASE_URL

Dependencies:
```
pip3 install -U python-docx beautifulsoup4 requests pillow python-dotenv
```

Basic usage:
```
python3 kb_to_docx.py -i JitBit_Knowledgebase.json -o Knowledgebase.docx
```

Authentication for protected images (API token):
- Set JITBIT_API_TOKEN in .env and optionally JITBIT_BASE_URL to your instance base (e.g., https://support.example.com/helpdesk).
- The script resolves relative URLs and fetches attachments via /helpdesk/api/attachment?id=... (falls back to /api/attachment?id=...).
- Cookie/Referer-based fetching is not used in this DOCX script.

Flags and behavior:
- --include-body-images true|false
  - Include inline <img> from Body HTML. Default: true
- --include-attachments true|false
  - Include images listed in the Attachments array. Default: true
- --attachments-header true|false
  - Print a small “Anhänge” heading before attachment images. Default: false
- --timeout SECONDS
  - HTTP timeout per image. Default: 15.0
- --image-placeholder true|false
  - Insert a textual placeholder with a link when an image fails to load. Default: true
- --verbose true|false
  - Log image requests and decisions to stderr.

Notes & troubleshooting:
- If placeholders appear for protected images:
  - Ensure JITBIT_API_TOKEN and JITBIT_BASE_URL are set correctly.
  - Run with --verbose to inspect fetch attempts and decisions.
- Duplicate suppression for attachments is per article by normalized URL.

------------------------------------------------------------
## Utility Scripts

### scripts/jitbit_fetch_attachment.py

Purpose:
- Standalone utility to fetch individual Jitbit attachment files via API using Bearer token authentication.
- Useful for testing API access, downloading specific attachments, or troubleshooting attachment retrieval issues.
- Supports automatic file extension detection based on Content-Type headers.

Dependencies:
- Requires: `requests`, `python-dotenv`
- Optional: `pillow` (for image validation)

Basic usage:
```bash
# Fetch attachment by FileID
python3 scripts/jitbit_fetch_attachment.py 26355

# Specify output filename
python3 scripts/jitbit_fetch_attachment.py 26355 --out screenshot.png

# Use custom base URL
python3 scripts/jitbit_fetch_attachment.py 26355 --base-url https://support.example.com --verbose
```

Configuration:
- Set `JITBIT_API_TOKEN` in `.env` file
- Optionally set `JITBIT_BASE_URL` (defaults to https://support.4plan.de)

CLI Options:
- `file_id`: Required - Attachment FileID from Jitbit (e.g., 26355)
- `--base-url URL`: Override base URL (default from JITBIT_BASE_URL env var)
- `--out FILENAME`: Output filename (auto-detected from content-type if not provided)
- `--verbose`: Enable detailed logging of requests and responses

API Endpoints Tried (in order):
1. `{base_url}/helpdesk/api/attachment?id={file_id}` (most common)
2. `{base_url}/api/attachment?id={file_id}` (fallback)

Features:
- **Auto File Extension**: Detects .png, .jpg, .gif, .pdf based on Content-Type header
- **Image Validation**: Optional PIL-based validation for downloaded images
- **Error Reporting**: Clear error messages with HTTP status and response snippets
- **Bearer Authentication**: Uses JITBIT_API_TOKEN for secure API access

Example Output:
```
[OK] Downloaded attachment id=26355 from https://support.4plan.de/helpdesk/api/attachment?id=26355
[OK] Content-Type: image/png
[OK] Saved to: attachment_26355.png
[OK] Image validated by PIL. Format=PNG
```

### scripts/test_llm_parse_errors.py

Purpose:
- Test script for debugging LLM JSON parsing errors from `process_tickets_with_llm.py`.
- Helps isolate and fix issues when LLM responses can't be parsed as valid JSON.

------------------------------------------------------------
## Project Workflow

Here's the typical workflow for processing Jitbit data:

### 1. Initial Setup
```bash
# Clone and install dependencies
git clone <repository-url>
cd S4U_JitBit_Tickets
pip3 install -r requirements.txt

# Create environment file
cp .env.example .env  # Edit with your API keys
```

### 2. Export Data from Jitbit
```bash
# Export tickets (interactive mode)
python3 ticket_relevante_felder.py

# Export knowledge base
python3 kb_export_json.py --yes
```

### 3. Process with LLM (Optional)
```bash
# Process tickets for RAG-friendly summaries
python3 process_tickets_with_llm.py --limit 50 --max-calls 100

# Check for any parsing errors
ls -la llm_parse_errors/
```

### 4. Generate Documents
```bash
# Create PDF from knowledge base
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o KB.pdf

# Create DOCX from ticket summaries
python3 tickets_to_docx.py -i Ticket_Data.JSON -o Tickets.docx
```

## Output Files

The repository generates several output files during processing:

| File | Created By | Content |
|------|------------|---------|
| `JitBit_relevante_Tickets.json` | ticket_relevante_felder.py | Raw ticket data with comments and attachments |
| `JitBit_Knowledgebase.json` | kb_export_json.py | Knowledge base articles with BBCode conversion |
| `Ticket_Data.JSON` | process_tickets_with_llm.py | LLM-processed ticket summaries (relevant only) |
| `not relevant.json` | process_tickets_with_llm.py | Raw tickets marked as not relevant by LLM |
| `llm_parse_errors/*.txt` | process_tickets_with_llm.py | Debug files for LLM parsing failures |
| `*.pdf` | kb_to_pdf.py | Formatted PDF documents |
| `*.docx` | tickets_to_docx.py | Formatted Word documents |

## Troubleshooting

### API Authentication Issues
- Verify `JITBIT_API_TOKEN` is correct and has sufficient permissions
- Test with `scripts/jitbit_fetch_attachment.py` using a known attachment ID
- Check if your Jitbit instance uses `/helpdesk/api/` or `/api/` endpoints

### LLM Processing Issues  
- Check `llm_parse_errors/` directory for parsing failures
- Verify `TOGETHER_API_KEY` is valid and has sufficient credits
- Use `--only-ticket-id` flag to debug specific tickets
- Reduce `--max-tokens` if hitting model limits

### Memory Issues with Large Datasets
- Install `ijson` for streaming: `pip3 install -U ijson` 
- Avoid `--newest-first` flag for very large exports
- Process in smaller batches using `--limit` and `--start-index`

### Image/Attachment Issues
- For protected images, ensure proper authentication (cookies or API tokens)
- Use `--verbose` flag to debug image download failures  
- Check Content-Type headers for non-image content
- Verify URLs are accessible from your network
