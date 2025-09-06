# Timegrip JitBit and Jira Tickets — Export and LLM Processing

This repository contains Python programs that work together to extract Jitbit and Jira tickets and the JitBit knowledge base articles via API, transform them into concise summaries using an LLM via Scaleway (OpenAI-compatible), optionally deduplicate quasi-duplicate tickets using multilingual embeddings, and render them as PDF/DOCX documents.

The App runs on the users' local machine. All data is located on this machine. AI inference provider is Scaleway, a French company, from Scaleways' Paris datacenter. All necessary documents (TOS and DPA) are in place, the legal relationship is between S4U and Scaleway. 

To run the process with the new comprehensive Web-UI: 

# Start the web server
python cli.py web --port 8787

# Open browser to: http://127.0.0.1:8787

The underlying process is as follows:

1) Download JitBit (S4U) ticket data and store them into JitBit_relevant_tickets.json with "ticket_relevante_felder.py", also download the JitBit Knowledge Base with "kb_export_json.py"
2) Download Jira (TP,TM) ticket data and store them into Jira_relevant_tickets.json with "jira_relevant_tickets.py"
3) Process this raw data with "process_tickets_with_llm.py" into separate result files for JitBit and Jira
4) Opttionally (recommeneded) De-Duplicate the files from step 3 with "/scripts/dedupe_tickets.py", create separate output files for each source (JitBit, Jira)
5) Run "tickets_to_docx" to generate DOCX files with results for both (deduped) result-JSONs
6) Generate DOCX for JitBit Knowledge Base Data with "kb_to_docx.py"
7) Use the DOCX files in TG Buddy within knowledge fields, update the vector-database in TG Buddy
8) Copy the (deduped) JSON results into the TG Buddy docker container root directory

## Main Programs:
- **ticket_relevante_felder.py** — Extracts closed tickets from Jitbit via API, cleans text fields, and writes a consolidated JSON file.
- **jira_relevant_tickets.py** — Exports resolved Jira issues in the same JSON schema as the Jitbit exporter, including problem, support comments (non-customer), resolution date, and attachments, with filters for resolved-only and resolved-after date, plus optional progress output (`--progress`, `--detailed-log`) and a minimal heartbeat every ~10s even without `--progress`.
- **process_tickets_with_llm.py** — Sends each ticket to an LLM to classify relevance and summarize problem/solution, writing compact outputs for downstream use (includes original Subject in the output summaries).
- **kb_export_json.py** — Exports Jitbit Knowledge Base articles as JSON with BBCode to Markdown conversion and attachment extraction.
- **kb_to_docx.py** — Renders Knowledge Base JSON to DOCX format with images and formatting.
- **tickets_to_docx.py** — Converts ticket summaries to DOCX format.

## Utility Scripts:
- **scripts/dedupe_tickets.py** — Semantic de-duplication of tickets (quasi-duplicates) using multilingual embeddings via Scaleway (OpenAI-compatible). Produces canonical ticket set plus audit files.
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

# Required for Jira export (Jira Cloud)
JIRA_EMAIL=your_atlassian_email@example.com
JIRA_API_TOKEN=your_jira_api_token

# Required for LLM processing (Scaleway AI Gateway, OpenAI-compatible)
SCW_SECRET_KEY=your_scaleway_api_key_here
SCW_OPENAI_BASE_URL=https://api.scaleway.ai/v1/chat/completions

# Optional defaults and extras
LLM_MODEL="gpt-oss-120b"
SCW_DEFAULT_PROJECT_ID=your_project_id           # optional but recommended
SCW_DEFAULT_ORGANIZATION_ID=your_org_id          # optional
SCW_REGION=fr-par                                 # optional (not required for the fixed endpoint)

# Optional for embeddings (dedupe)
SCW_API_KEY=your_scaleway_api_key_here           # alias for SCW_SECRET_KEY
SCW_EMBEDDING_MODEL=bge-multilingual-gemma2      # default if unset

# Optional for Jira image downloads in tickets_to_docx.py
# Note: Can reuse JIRA_API_TOKEN if it has appropriate permissions
# JIRA_API_TOKEN=your_jira_api_token             # already defined above
```

**Security Note**: Never commit the `.env` file to version control. Ensure `.env` is included in your `.gitignore`.

------------------------------------------------------------

## 🚀 NEW: Workflow App - Web UI & CLI for Complete Workflow Automation

**We've added a powerful new workflow orchestration system that provides both a beautiful web interface and CLI automation for running complete end-to-end ticket processing workflows!**

### ✨ Quick Start

#### Web Interface (Recommended)
```bash
# Install additional dependencies
pip install typer fastapi uvicorn jinja2 python-multipart

# Start the web server
python cli.py web --port 8787

# Open browser to: http://127.0.0.1:8787
```

#### CLI Interface (For Automation)
```bash
# Check environment configuration
python cli.py env-check

# Run complete Jitbit workflow
python cli.py run-jitbit --start-id 23000

# Run complete Jira workflow  
python cli.py run-jira --project SUP --resolved-after 2024-12-01
```

### 🎯 What the Workflow App Does

Instead of running individual scripts manually, the Workflow App orchestrates **complete end-to-end workflows** with:

#### **Jitbit Workflow (6 automated steps)**:
1. **Environment Validation** — Verify all API tokens and URLs
2. **Export Tickets** — Run `ticket_relevante_felder.py` with your parameters  
3. **Export Knowledge Base** — Run `kb_export_json.py` automatically
4. **LLM Processing** — Run `process_tickets_with_llm.py` with configurable limits
5. **Generate Ticket DOCX** — Run `tickets_to_docx.py` to create documents
6. **Generate KB DOCX** — Run `kb_to_docx.py` for knowledge base document

#### **Jira Workflow (5 automated steps)**:
1. **Environment Validation** — Verify Jira and LLM credentials
2. **Export Tickets** — Run `jira_relevant_tickets.py` with project and date filters
3. **LLM Processing** — Process tickets with configurable parameters
4. **Deduplication** — Run `scripts/dedupe_tickets.py` with similarity analysis
5. **Generate DOCX** — Create final documents from deduplicated data

### 🌟 Web Interface Features

#### **Beautiful Dashboard**
- **Environment Status Cards**: Visual indicators showing 7/7 configuration checks
- **Workflow Cards**: Click-to-start interfaces for both Jitbit and Jira workflows
- **Recent Runs**: Quick access to your latest workflow executions

#### **Interactive Forms with Full Parameter Control**

**Jitbit Workflow Form**:
- **Basic Parameters**:
  - `Start Ticket ID` (required) — Starting ticket ID for export (e.g., 23000)
- **LLM Options**:
  - `LLM Limit` (optional) — Limit number of tickets for LLM processing
  - `Max API Calls` (optional) — Maximum LLM API calls to prevent runaway costs
  - `Save Interval` (default: 50) — Save progress every N tickets during LLM processing
  - `Process newest tickets first` — Process in reverse chronological order
- **Run Options**:
  - ✅ `Skip existing outputs` (default: ON) — Skip steps when output files already exist
  - ❌ `Overwrite existing files` (default: OFF) — Force re-run all steps even if outputs exist
  - ❌ `Append mode` (default: OFF) — Append to existing exports where supported

**Jira Workflow Form**:
- **Basic Parameters**:
  - `Project` — Radio buttons for SUP (Danish support) or TMS (Timemap support)
  - `Resolved After` (required) — Date in YYYY-MM-DD format for ticket filtering
  - `Resolved Before` (optional) — End date for date range filtering
- **Advanced Export Options**:
  - `Jira Limit` (optional) — Limit number of tickets to export from Jira
  - `Show detailed progress` — Enable verbose progress output during Jira export
- **LLM Options**:
  - `LLM Limit` (optional) — Limit tickets for LLM processing
  - `Max API Calls` (optional) — Cap total LLM API calls
- **Deduplication Settings**:
  - `Similarity Threshold` (default: 0.84) — High threshold for automatic merging
  - `Low Threshold` (default: 0.78) — Low threshold for manual review flagging
  - `Skip deduplication` — Bypass the deduplication step entirely
- **Run Options**: Same skip/overwrite/append controls as Jitbit

#### **Real-Time Progress Dashboard**
When you submit a workflow, you're immediately redirected to a beautiful progress tracking page:

**Visual Timeline**:
- 🔄 **Running Steps**: Blue spinning indicators with live status
- ✅ **Completed Steps**: Green checkmarks with duration timing
- ⏭️ **Skipped Steps**: Yellow clock icons for existing outputs
- ❌ **Failed Steps**: Red X marks with error details
- ⏳ **Pending Steps**: Gray circles waiting for execution

**Live Execution Log**:
- **Terminal-style display** with auto-scrolling to latest output
- **Real-time script output** showing exactly what you see when running scripts manually:
  ```
  [2025-09-06 14:45:02] === JITBIT GESCHLOSSENE TICKETS - RELEVANTE FELDER EXPORT ===
  [2025-09-06 14:45:03] Sammle alle verfügbaren Ticket-IDs mit Pagination...
  [2025-09-06 14:45:04] Lade Batch 1 (Tickets 1-300)...
  [2025-09-06 14:45:05] → 300 Tickets geladen (Gesamt: 300)
  [2025-09-06 14:45:10] Fortschritt: 2.3% - 100/4332 - ETA: 35min
  [2025-09-06 14:45:15] Fortschritt: 4.6% - 200/4332 - ETA: 30min
  ```
- **Auto-scrolling**: Latest updates automatically scroll into view
- **Live refresh**: Updates every 2 seconds during active runs

**Generated Artifacts Panel**:
- Direct links to all generated files (JSON, DOCX)
- File sizes and creation timestamps  
- Click to open files directly from the browser

#### **Run History & Management**
- **Browse all runs**: Complete history with status indicators
- **Run details**: Click any run to see full execution details
- **Persistent logging**: All runs saved in timestamped directories
- **Artifact preservation**: Generated files automatically copied and tracked

### 🔧 Advanced Configuration Options

#### **Port Configuration** (Never uses port 8000)
- **Default**: `127.0.0.1:8787`
- **Environment**: Set `WORKFLOW_APP_PORT=8787` in `.env`
- **CLI**: `python cli.py web --port 8787`
- **Auto-fallback**: `--auto-port` tries 8787→8788→8789 if busy

#### **Skip/Overwrite Logic**
- **Skip Existing** (default: ✅): Intelligently skip steps when output files already exist and are valid
- **Overwrite** (default: ❌): Force re-run all steps even if outputs exist
- **Append** (default: ❌): Append to existing exports where scripts support it

*Example*: If you have existing `JitBit_relevante_Tickets.json` and `JitBit_Knowledgebase.json`:
- **Skip ON, Overwrite OFF**: Skips exports, runs LLM processing and DOCX generation only
- **Skip OFF, Overwrite ON**: Re-runs all steps from scratch
- **Skip ON, Append ON**: Skips exports but appends new data to existing LLM outputs

#### **LLM Processing Controls**
- **LLM Limit**: Limit number of tickets sent to LLM (cost control for testing)
- **Max API Calls**: Hard cap on total LLM requests (prevents runaway costs)
- **Save Interval**: Auto-save progress every N tickets (default: 50)
- **Newest First**: Process tickets in reverse chronological order

#### **Jira-Specific Settings**
- **Progress Mode**: Enable detailed progress output during Jira export
- **Date Range**: Flexible filtering with resolved-after (required) and resolved-before (optional)
- **Deduplication Thresholds**: Fine-tune similarity detection (0.84/0.78 defaults)

### 🎮 User Experience Benefits

#### **Background Execution**
- **Navigate freely**: Start a workflow, then browse other parts of the app
- **Multiple workflows**: Run up to 2 workflows simultaneously  
- **Server-based**: Workflows continue even if you close your browser
- **Return anytime**: Click on any run to see current status and progress

#### **Real-Time Feedback**
- **Live progress**: See exactly what's happening at each step
- **Progress percentages**: Real ETAs from your scripts (e.g., "ETA: 25min")
- **Batch tracking**: Live updates on ticket processing ("Batch 5 loading...")
- **Error visibility**: Immediate feedback if any step fails

#### **Smart Workflow Management**
- **Environment validation**: Blocks execution if API tokens missing
- **Artifact tracking**: All generated files linked and accessible
- **Run isolation**: Each workflow gets its own timestamped directory
- **Log preservation**: Complete execution history saved permanently

#### **Form Validation & UX**
- **ENTER key prevention**: Forms only submit via button clicks (no accidental submission)
- **Smart validation**: Empty optional fields handled gracefully
- **Environmental warnings**: Visual alerts if credentials are missing
- **Parameter defaults**: Pre-filled with sensible values from configuration

### 📊 Monitoring & Debugging

#### **Run Status Tracking**
Every workflow execution creates a timestamped directory: `runs/YYYYMMDD-HHMMSS-flow-project/`
- `status.json` — Step-by-step execution status with timestamps
- `params.json` — Input parameters (secrets redacted for security)
- `flow.log` — Complete execution log with all script output
- `artifacts/` — Copies of all generated files for easy access

#### **Environment Health**
- **7-point validation**: Comprehensive checks for Jitbit, Jira, and LLM credentials
- **URL validation**: Ensures API endpoints are properly formatted  
- **Token presence**: Verifies all required authentication is available
- **Visual dashboard**: Green/red status indicators for quick assessment

#### **Error Recovery**
- **Graceful failures**: Failed steps clearly marked with error details
- **Partial artifacts**: Successfully completed steps preserved even if workflow fails
- **Re-run capability**: Can restart workflows with different parameters
- **Debug support**: Full logging and parameter tracking for troubleshooting

### 🔐 Security Features

- **Credential protection**: Sensitive data redacted from logs and saved parameters
- **Local execution**: Everything runs on your machine, data stays local
- **Environment validation**: Prevents workflows from running with missing credentials
- **Secure logging**: API tokens and keys automatically masked in all log output

### 💡 Migration from Manual Script Execution

#### **Before** (Manual Process):
```bash
python3 ticket_relevante_felder.py --start-id 23000 --yes
python3 kb_export_json.py --out JitBit_Knowledgebase.json --yes  
python3 process_tickets_with_llm.py --limit 100 --max-calls 200
python3 tickets_to_docx.py --input Ticket_Data_Jitbit.json
python3 kb_to_docx.py --input JitBit_Knowledgebase.json
```

#### **After** (One-Click Workflow):
- Open browser → Click "Start Workflow" → Fill form → Submit
- **Or via CLI**: `python cli.py run-jitbit --start-id 23000 --llm-limit 100`

#### **Benefits of the Workflow App**:
- ✅ **No script coordination**: All steps run in correct sequence automatically
- ✅ **Parameter management**: Web forms with validation vs manual command assembly
- ✅ **Progress visibility**: Live progress vs waiting blindly for completion  
- ✅ **Error handling**: Clear failure messages vs cryptic script errors
- ✅ **File management**: Automatic output naming and organization
- ✅ **Run history**: Track all executions vs losing track of what you've done
- ✅ **Multi-tasking**: Background execution vs blocking your terminal

### 🎉 Production Ready

The Workflow App is designed for daily production use:
- **Reliable**: Robust error handling and recovery
- **Scalable**: Configurable limits and batch processing  
- **Monitorable**: Complete logging and progress tracking
- **Secure**: Environment validation and credential protection
- **User-friendly**: Beautiful interface with real-time feedback

**Ready to streamline your ticket processing workflows!**

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
## 1a) Export resolved Jira tickets (jira_relevant_tickets.py)

Purpose:
- Export resolved Jira issues into the same JSON schema as the Jitbit exporter (JitBit_relevante_Tickets.json), including:
  - problem (description as text), support-only comments, resolution name/date, attachments

Configuration:
- Set `JIRA_EMAIL` and `JIRA_API_TOKEN` in your `.env` file (see Environment Setup).
- Adjust the Jira base URL in the script if needed:
  - Open `jira_relevant_tickets.py` and set `JIRA_BASE_URL` (default is `https://timeplan.atlassian.net`).

Filters:
- `--resolved-only` restricts to issues in status category Done.
- `--resolved-after YYYYMMDD` (or `YYYY-MM-DD`) includes only issues resolved on/after the given date (compares `resolutiondate`).
- `--resolved-before YYYYMMDD` (or `YYYY-MM-DD`) includes only issues resolved on/before the given date (inclusive). Combine with --resolved-after for a bounded date range.

Important: Either `--limit` or `--resolved-after` must be provided; otherwise the script exits without starting to avoid unbounded exports. Omitting `--limit` fetches ALL matching issues (use with `--resolved-after`). The --resolved-before flag is optional and does not replace this requirement.

Basic usage:
```bash
# Single issue, print details
python3 jira_relevant_tickets.py --issue SUP-41210

# Single issue, export to JSON schema compatible with the Jitbit exporter
python3 jira_relevant_tickets.py --issue SUP-41210 --export JIRA_relevante_Tickets.json

# Batch by JQL (preserves ORDER BY), only resolved after March 31, 2025
python3 jira_relevant_tickets.py \
  --jql "project=SUP order by resolutiondate DESC" \
  --resolved-only \
  --resolved-after 20221231 \
  --export JIRA_relevante_Tickets.json

# Date range (inclusive) and append to an existing file (de-duplicated)
python3 jira_relevant_tickets.py \
  --jql "project=SUP order by resolutiondate DESC" \
  --resolved-after 2025-01-01 \
  --resolved-before 2025-03-31 \
  --append \
  --export JIRA_relevante_Tickets.json
```

Progress and logging examples:
```bash
# Progress only (compact): shows search pagination and [idx/total] with rate/ETA
python3 jira_relevant_tickets.py \
  --jql "project=SUP order by resolutiondate DESC" \
  --resolved-only --resolved-after 2025-07-31 \
  --progress

# Progress + detailed logs (includes issue keys and per-ticket prints; enables comment pagination logs)
python3 jira_relevant_tickets.py \
  --jql "project=SUP order by resolutiondate DESC" \
  --resolved-only --resolved-after 2025-07-31 \
  --progress --detailed-log
```

CLI Options:
- `--issue KEY` — Specific issue key (e.g., SUP-41210)
- `--jql "..."` — JQL for listing (ORDER BY preserved)
- `--limit N` — Max results to fetch from search. If omitted, ALL matching issues are fetched (with pagination). Note: Either `--limit` or `--resolved-after` is required.
- `--export PATH` — Write JSON using Jitbit-like schema (default example: JIRA_relevante_Tickets.json)
- `--resolved-only` — Only include issues in Done status category
- `--resolved-after YYYYMMDD|YYYY-MM-DD` — Only include issues resolved on/after the date
- `--resolved-before YYYYMMDD|YYYY-MM-DD` — Only include issues resolved on/before the date (inclusive)
- `--append` — Append to existing export file, de-duplicate by ticket_id; updates export_info counters
- `--progress` — Print progress (search pagination and periodic `[idx/total]` lines with rate/ETA). Suppresses the default heartbeat lines.
- `--detailed-log` — With `--progress`, include issue keys and per-ticket details; enables comment pagination progress lines.

Output structure (JIRA_relevante_Tickets.json):
- Mirrors the Jitbit exporter:
```
{
  "export_info": {
    "timestamp": "...",
    "total_closed_tickets": <int>,
    "total_comments": <int>,
    "total_ticket_attachments": <int>,
    "total_comment_attachments": 0,
    "export_duration_seconds": <float>,
    "filter_criteria": "JQL and filters applied",
    "api_base_url": "https://your-domain.atlassian.net"
  },
  "tickets": [
    {
      "ticket_id": <int or string>,          // Jira numeric id when possible
      "CategoryName": "<issuetype.name>",
      "IssueDate": "<fields.created>",
      "Subject": "<summary>",
      "Body": "<description text>",           // rendered HTML stripped; ADF->text fallback
      "Status": "<status.name>",
      "Url": "https://.../browse/<KEY>",
      "Attachments": [
        { "FileName": "<filename>", "Url": "<content>", "Size": <int> }
      ],
      "kommentare": [
        {
          "CommentDate": "<created>",
          "Body": "<plain text body>",
          "UserName": "<author.displayName>",
          "Attachments": []
        }
      ]
    }
  ]
}
```

Notes:
- Support comments exclude end customers (filters `author.accountType == "customer"`).
- Jira attachments are issue-level; comment-level Attachments arrays are intentionally empty.
- The exporter applies filters both in the search JQL and post-fetch (safety check on `resolutiondate`).
- Progress behavior:
  - Without `--progress`: a minimal heartbeat prints about every 10 seconds during long operations (search pagination, per-issue processing, listing) showing elapsed time, approximate progress, rate, and ETA.
  - With `--progress`: explicit progress lines are printed and the heartbeat is suppressed to avoid duplicate output; add `--detailed-log` to include issue keys and per-ticket details.

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
# Scaleway AI Gateway (OpenAI-compatible)
SCW_SECRET_KEY=your_scaleway_api_key_here
SCW_OPENAI_BASE_URL=https://api.scaleway.ai/v1/chat/completions
# Model (example that works on Scaleway)
LLM_MODEL="gpt-oss-120b"
# Optional extras:
SCW_DEFAULT_PROJECT_ID=your_project_id
# SCW_DEFAULT_ORGANIZATION_ID=your_org_id
# SCW_REGION=fr-par
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
- SCW_SECRET_KEY (required) — from .env or your shell env
- SCW_OPENAI_BASE_URL (required) — must be https://api.scaleway.ai/v1/chat/completions
- LLM_MODEL (optional) — model id string; example "gpt-oss-120b" (defaults to Meta-Llama-3.1-70B-Instruct-Turbo if unset)

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
- Missing or invalid Scaleway credentials:
  - Ensure .env contains SCW_SECRET_KEY and SCW_OPENAI_BASE_URL=https://api.scaleway.ai/v1/chat/completions.
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
## 2a) Deduplicate ticket summaries (scripts/dedupe_tickets.py)

Purpose:
- Detect and merge quasi-duplicate tickets that describe the same problem/solution in different words.
- Produce a canonical set of tickets while keeping an audit trail of merged items.

How it works:
- Builds a normalized text per ticket by concatenating subject + problem + solution and removing transient tokens (URLs, NN123 codes, PERSNR, etc.) while keeping domain-relevant tokens (e.g., “Step 408”, account numbers).
- Computes multilingual sentence embeddings via Scaleway’s OpenAI-compatible embeddings endpoint using the model `bge-multilingual-gemma2` (default).
- Creates a similarity graph using cosine similarity; edges above a threshold form clusters.
- Picks a representative per cluster (most informative: longest solution; fallbacks to longest problem/subject).
- Writes:
  - `tickets_dedup.json` — canonical tickets with `duplicates: [ ... ]` and `cluster_id`
  - `duplicate_groups.json` — full cluster membership with indices and ticket IDs
  - `needs_review.csv` — borderline similar pairs for manual review (gray zone between thresholds)

Inputs:
- Expects a list of tickets containing at least `subject`, `problem`, `solution`. Works with `Ticket_Data.JSON` or test files (e.g., `Ticket_Data_TEST.JSON`).

Environment:
- Uses `.env` (same loader as process_tickets_with_llm.py)
```
SCW_SECRET_KEY=...       # or SCW_API_KEY
SCW_OPENAI_BASE_URL=https://api.scaleway.ai/v1/chat/completions
SCW_PROJECT_ID=...       # optional
SCW_REGION=fr-par        # optional; region endpoints are attempted automatically
SCW_EMBEDDING_MODEL=bge-multilingual-gemma2  # override if needed
```

Dependencies:
- `requests` (already part of base requirements)

Basic usage:
```bash
# Run on LLM summaries (recommended)
python3 scripts/dedupe_tickets.py \
  --input Ticket_Data.JSON \
  --out tickets_dedup.json \
  --groups-out duplicate_groups.json \
  --review-out needs_review.csv \
  --threshold 0.84 \
  --threshold-low 0.78
```

Examples and tuning:
```bash
# Slightly more aggressive merging
python3 scripts/dedupe_tickets.py -i Ticket_Data.JSON --threshold 0.82 --threshold-low 0.76

# Dry-run to see summary without writing files
python3 scripts/dedupe_tickets.py -i Ticket_Data.JSON --dry-run

# Batch size for embedding calls (default 64)
python3 scripts/dedupe_tickets.py -i Ticket_Data.JSON --batch-size 32
```

Outputs:
- `tickets_dedup.json` — same ticket schema as input entries plus:
  - `duplicates`: string array of ticket_ids that were merged into the canonical record
  - `cluster_id`: numeric identifier of the cluster
- `duplicate_groups.json` — array of:
  - `cluster_id`, representative index/ID, members (indices and ticket IDs), size
- `needs_review.csv` — semicolon-separated rows of:
  - `ticket_id_A;ticket_id_B;similarity;subject_A;subject_B` for pairs in gray zone (≥ threshold-low and < threshold)

Thresholds:
- `--threshold` (default 0.84): pairs at or above this cosine similarity auto-merge into the same cluster
- `--threshold-low` (default 0.78): gray-zone lower bound; pairs here are listed in needs_review.csv but not merged
- Start with defaults; lower threshold slightly if too few merges, or raise if you observe false merges

Integration into workflow:
- After generating `Ticket_Data.JSON` via the LLM step:
```bash
python3 scripts/dedupe_tickets.py -i Ticket_Data.JSON
# then pass tickets_dedup.json to document rendering or analytics
python3 tickets_to_docx.py --input tickets_dedup.json
```

Troubleshooting:
- Ensure `.env` has valid Scaleway key and base URL; the script derives an `/embeddings` endpoint from your OpenAI-compatible base.
- If you see zero merges but expect some, lower `--threshold` to 0.82 or 0.80 and re-run.
- For very small datasets, borderline pairs may be empty; this is normal.

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
    - Optional inline images from image_urls with multi-source support (JitBit, Jira, and external URLs)

**Multi-Source Image Support**
- **JitBit Images**: API-first fetching with Bearer token authentication for protected attachments
- **Jira Images**: Basic authentication with email + API token for Jira Cloud attachment URLs
- **External Images**: Standard HTTP fetch for generic image URLs

Dependencies:
```bash
pip3 install -U python-docx beautifulsoup4 requests pillow python-dotenv
```

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
- `--jira-token TOKEN`: Override JIRA_API_TOKEN from environment (for Jira attachments)
- `--verbose true|false`: Enable detailed logging

New in 2025-08: Image optimization, deduplication, and ETA

Advanced image optimization flags (enabled by default):
- --image-optimize true|false (default: true): Enable Pillow-based preprocessing before embedding.
- --image-target-dpi INT (default: 150): Derives a max pixel width from the document’s usable width. Lower for more compression, higher for quality.
- --image-max-width-px INT: Explicit pixel cap; overrides target-DPI derived width.
- --image-jpeg-quality INT (default: 75): JPEG quality when re-encoding or converting.
- --image-convert-png-to-jpeg true|false (default: true): Convert PNGs to JPEG when transparency isn’t needed.
- --image-force-jpeg true|false (default: false) or -image-force-jpeg true|false: Force JPEG for all non-JPEGs (drops transparency), even if larger.
- --image-min-recompress-bytes INT (default: 131072): Skip recompressing very small images unless resized or forced.
- --image-jpeg-optimize true|false (default: false): Extra encoder optimization (slower).
- --image-jpeg-progressive true|false (default: false): Progressive JPEGs (slower to encode).
- --image-png-compress-level 0..9 (default: 6): PNG zlib level when retaining PNGs.
- --image-workers INT (default: 0=auto up to CPU*2): Parallel image optimization workers.
- Robust handling for palette+transparency PNGs; internal normalization to RGBA and targeted warning suppression.

Per-ticket image deduplication (enabled by default):
- --image-dedupe true|false (default: true): Suppress duplicates within the same ticket only.
- --image-dedupe-mode ahash|exact (default: ahash): Perceptual average-hash vs byte-identical.
- --image-dedupe-threshold INT (default: 5): Hamming distance threshold for ahash mode.

Runtime output improvements:
- Each generated DOCX line prints elapsed time for the batch and an ETA to completion, e.g.:
  [OK] DOCX generated: documents/tickets_0001-0050_batch_001.docx (tickets 1-50, 50 tickets) | time: 12.3s | ETA: 0:04:36 (~19:45:02)

Recommended presets:
- Balanced size + speed:
  ```
  python3 tickets_to_docx.py --input Ticket_Data.JSON \
    --image-workers 8 --image-target-dpi 120 --image-jpeg-quality 70 \
    --image-min-recompress-bytes 300000
  ```
- Maximum compression (may be slower):
  ```
  python3 tickets_to_docx.py --input Ticket_Data.JSON \
    --image-target-dpi 110 --image-jpeg-quality 65 \
    --image-jpeg-optimize true --image-jpeg-progressive true
  ```
- Force JPEG for all non-JPEG inputs (drops transparency):
  ```
  python3 tickets_to_docx.py --input Ticket_Data.JSON \
    --image-force-jpeg true --image-jpeg-quality 70
  ```

File naming:
- **Multiple tickets per file**: `tickets_0001-0050_batch_001.docx`, `tickets_0051-0100_batch_002.docx`, etc.
- **Single ticket per file** (--tickets-per-file 1): `ticket_{id}_{safe_subject}.docx`

Authentication for protected images:

**JitBit Images:**
- Set `JITBIT_API_TOKEN` in .env and `JITBIT_BASE_URL` to your instance base (e.g., https://support.example.com/helpdesk).
- The script resolves relative URLs and fetches attachments via `/helpdesk/api/attachment?id=...` (falls back to `/api/attachment?id=...`).

**Jira Images:**
- Set `JIRA_API_TOKEN` and `JIRA_EMAIL` in .env for Jira Cloud Basic authentication.
- Jira URLs are detected automatically (e.g., `https://{instance}.atlassian.net/rest/api/3/attachment/content/{id}`).
- Uses Basic auth with email + token combination (preferred for Jira Cloud).

**Image Processing Logic:**
1. **Jira URLs** (priority): Automatically detected by `.atlassian.net` domain → Jira Basic auth download
2. **JitBit URLs**: `/helpdesk/File/Get/{id}` pattern → JitBit API fetching with Bearer token
3. **External URLs**: `https://example.com/image.png` → Standard HTTP fetch

Features:
- **XML-Safe Content**: Automatically removes XML control characters that cause python-docx failures
- **Bold Text Support**: Renders **bold** and `<b>bold</b>` markup in Problem/Solution text
- **List Support**: Simple lists when lines start with -, *, • or 1., 2)
- **Image Validation**: PIL-based validation ensures only valid images are embedded
- **Fallback Placeholders**: Text placeholders for failed image downloads with authentication hints

Examples:
```bash
# Process with default settings (50 tickets per file)
python3 tickets_to_docx.py --input Ticket_Data.JSON --verbose true

# Create smaller files with 10 tickets each
python3 tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 10 --output-dir output/

# Maintain original behavior (one file per ticket)
python3 tickets_to_docx.py --input Ticket_Data.JSON --tickets-per-file 1

# Mixed JitBit and Jira tickets with authentication for both sources
python3 tickets_to_docx.py \
  --input Ticket_Data.JSON \
  --output-dir documents/tickets/ \
  --tickets-per-file 25 \
  --include-images true \
  --verbose true
  # Uses JITBIT_API_TOKEN and JIRA_API_TOKEN + JIRA_EMAIL from .env

# Override tokens via command line
python3 tickets_to_docx.py \
  --input Ticket_Data.JSON \
  --token your_jitbit_token \
  --jira-token your_jira_token \
  --verbose true

# Process deduped tickets with custom batch size
python3 tickets_to_docx.py \
  --input tickets_dedup.json \
  --tickets-per-file 30 \
  --output-dir documents/canonical/ \
  --verbose true
```

Notes:
- The script automatically derives JitBit API endpoints from JITBIT_BASE_URL, trying both `/helpdesk/api` and `/api` variants
- Jira attachment URLs are identified by `.atlassian.net` domain and handled with Basic authentication
- Image dimensions are preserved using embedded DPI metadata when available (defaults to 96 DPI)
- Failed image downloads show detailed error messages with authentication hints when `--verbose` is enabled
- The script handles both raw ticket arrays and objects with `tickets` keys for input flexibility

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
  - Insert a textual placeholder when an image fails to load. Default: true
- --verbose true|false
  - Log image requests and decisions to stderr.

Notes & troubleshooting:
- If placeholders appear for protected images:
  - Ensure JITBIT_API_TOKEN and JITBIT_BASE_URL are set correctly.
  - Run with --verbose to inspect fetch attempts and decisions.
- Duplicate suppression for attachments is per article by normalized URL.

## 6) Generate Q&A from DOCX chapters (scripts/generate_qa_from_docx.py)

Purpose:
- Convert arbitrary DOCX documents into a Q&A dataset by chapter and optionally export to DOCX.
- Two-step pipeline with an intermediate JSON corpus for auditability and caching.
- Supports both size-based and coverage-driven Q&A generation modes.

Overview:
- Input directory: QA_SOURCE (place your .docx files here)
- Intermediate chapters JSON: QA_CHAPTERS/<doc_basename>.json
- Final Q&A JSON: QA_OUTPUT/<doc_basename>.json
- DOCX export: QA_DOCX/<doc_basename>.docx

How it works:
1) extract
   - Reads all .docx from QA_SOURCE
   - Splits into chapters by heading level (default Heading 1)
   - Writes per-document chapters JSON with chapter title, content, char_count, and token_estimate
   - Skips Word lock files (~$...)

2) qa
   - Reads chapters JSON from QA_CHAPTERS
   - **Size-based mode** (default): Computes a target number of Q&A pairs based on size (approx. tokens/350; clamped 1..10)
   - **Coverage mode**: Systematically extracts concepts and generates Q&A to achieve comprehensive topic coverage
   - Calls a Scaleway OpenAI-compatible chat completion model (e.g., gpt-oss-120b)
   - Writes per-document Q&A JSON to QA_OUTPUT

3) docx
   - Converts Q&A JSON to a DOCX table
   - Table columns: Question | Answer (Chapter column removed by request)
   - Adds a simple heading and optional metadata line (model, generation time)

### Coverage Mode - Advanced Q&A Generation

Coverage mode (`--coverage-mode`) is an intelligent Q&A generation strategy that ensures comprehensive topic coverage by first identifying key concepts in a chapter, then systematically generating questions to address those concepts.

**How Coverage Mode Works:**

1. **Concept Extraction Phase**: 
   - Extracts key concepts, definitions, procedures, configuration options, and important rules from chapter content
   - Each concept gets a unique ID (C1, C2, C3...), title, summary, and importance level (1=minor, 2=important, 3=critical)
   - For large chapters, content is chunked and concepts are extracted from each chunk, then merged and deduplicated

2. **Iterative Q&A Generation**:
   - Generates Q&A pairs in multiple rounds, tracking which concepts each question covers
   - Prioritizes high-importance concepts first (3 > 2 > 1)
   - Continues until coverage threshold is met (default 85% of concepts covered)
   - Each iteration logs detailed progress: `[qa][coverage] 'Chapter Title': iter=2 added=4 covered=12/20 (60%)`

3. **Adaptive Termination**:
   - Stops when coverage threshold is reached (default 85%)
   - Safety limits prevent unbounded generation (max iterations: 8, max Q&A per chapter: 60)
   - Handles diminishing returns by stopping if no new questions are generated

**Coverage Mode Parameters:**
```bash
--coverage-mode                           # Enable coverage-driven generation
--coverage-threshold 0.85                 # Target concept coverage (85%)
--concepts-max 50                         # Max concepts to extract per chapter
--max-qa-per-chapter-safety 60           # Safety cap on Q&A pairs per chapter
--max-iterations 8                        # Max generation rounds per chapter
```

**When to Use Coverage Mode:**
- **Comprehensive documentation**: When you need thorough coverage of all topics in technical manuals
- **Training materials**: For educational content where missing key concepts would be problematic  
- **Quality over quantity**: When systematic coverage is more important than hitting specific question counts
- **Complex chapters**: For content-rich chapters where size-based generation might miss important topics

**Size-based vs Coverage Mode Comparison:**

| Aspect | Size-based Mode | Coverage Mode |
|--------|----------------|---------------|
| **Question Count** | Fixed (≈ tokens/350, max 10) | Adaptive (varies by content complexity) |
| **Coverage** | Random/chance-based | Systematic concept coverage |
| **Performance** | Fast, single LLM call per chapter | Slower, multiple iterative calls |
| **Consistency** | Predictable output size | Variable output size based on content |
| **Best For** | Large-scale processing, consistent output | Quality documentation, comprehensive coverage |

**Coverage Mode Example Workflow:**

For a chapter about "Database Configuration":
1. **Extract Concepts**: Identifies 15 concepts like "Connection Pooling", "Index Optimization", "Backup Strategies"
2. **Iteration 1**: Generates 5 Q&A covering concepts C1, C3, C7, C9, C12 (33% coverage)
3. **Iteration 2**: Generates 4 Q&A covering concepts C2, C4, C5, C11 (60% coverage)
4. **Iteration 3**: Generates 3 Q&A covering concepts C6, C8, C10 (80% coverage)  
5. **Iteration 4**: Generates 2 Q&A covering concepts C13, C14 (93% coverage)
6. **Complete**: Coverage threshold exceeded, returns 14 Q&A pairs ensuring comprehensive database configuration coverage

Dependencies:
- python-docx, openai, tiktoken, tenacity (for retries)
Install:
```bash
pip3 install -U python-docx openai tiktoken tenacity
```

Environment:
- The script auto-loads .env if present. Supported variables:
```
# API key (one of these must be set)
SCW_API_KEY=your_scaleway_key
SCW_SECRET_KEY=your_scaleway_key        # alias

# Base URL (any of these supported; defaults to https://api.scaleway.ai if unset)
SCW_BASE_URL=https://api.scaleway.ai
SCW_OPENAI_BASE_URL=https://api.scaleway.ai/v1/chat/completions  # legacy full path ok; script normalizes

# Model (last path segment is used if you pass provider/model)
LLM_MODEL=gpt-oss-120b
# or SCW_MODEL=gpt-oss-120b

# Optional: request native JSON mode if the provider supports it
SCW_JSON_MODE=1
```

CLI:
- Extract chapters:
```bash
python3 scripts/generate_qa_from_docx.py extract --input QA_SOURCE --output QA_CHAPTERS --heading-level 1
```
- Generate Q&A JSON:
```bash
python3 scripts/generate_qa_from_docx.py qa --input QA_CHAPTERS --output QA_OUTPUT --max-per-chapter 10
```
- Export DOCX:
```bash
python3 scripts/generate_qa_from_docx.py docx --input QA_OUTPUT --output QA_DOCX
```

**Example: Complete pipeline to generate DOCX from existing Q&A JSON files:**
```bash
# If you already have Q&A JSON files in QA_OUTPUT, convert them directly to DOCX
python3 scripts/generate_qa_from_docx.py docx --input QA_OUTPUT --output QA_DOCX

# This will create DOCX files like: QA_DOCX/QA-{document_name}.docx
# Each DOCX contains a table with columns: Question | Answer
```

Options:
- --heading-level N
  - Which heading style to treat as chapter boundary (default 1)
- --max-per-chapter N
  - Upper bound of Q&A pairs per chapter for size-based mode (default 10)
- --max-per-document N
  - Optional ceiling on total Q&A per document in size-based mode. When set, the tool distributes the total across chapters proportionally to chapter size (largest-remainder method). Logs show requested vs assigned.
- Coverage-mode (adaptive, coverage-driven; generates “as many as needed” to cover the chapter):
  - --coverage-mode
    - Enable concept coverage-driven generation (adapts Q&A count to chapter content)
  - --coverage-threshold FLOAT (default 0.85)
    - Target concept coverage ratio (0..1) before stopping (e.g., 0.85 = 85% of extracted concepts covered)
  - --concepts-max INT (default 50)
    - Max distinct concepts to extract per chapter as coverage targets (definitions, procedures, options, exceptions, rules)
  - --max-qa-per-chapter-safety INT (default 60)
    - Safety cap per chapter to avoid unbounded growth in pathological cases
  - --max-iterations INT (default 8)
    - Max coverage iterations per chapter
- Environment-driven choices:
  - Base URL priority: SCW_BASE_URL | SCW_OPENAI_BASE_URL | OPENAI_BASE_URL | OPENAI_API_BASE (normalized to /v1)
  - API key: SCW_API_KEY | SCW_SECRET_KEY | OPENAI_API_KEY
  - Model: SCW_MODEL | LLM_MODEL | TOGETHER_MODEL (provider/model → model)

Examples:
- Size-based (per chapter, scales by size up to max):
```bash
python3 scripts/generate_qa_from_docx.py qa \
  --input QA_CHAPTERS \
  --output QA_OUTPUT \
  --max-per-chapter 10
```

- Size-based with per-document cap (distributes total by chapter size):
```bash
python3 scripts/generate_qa_from_docx.py qa \
  --input QA_CHAPTERS \
  --output QA_OUTPUT \
  --max-per-chapter 10 \
  --max-per-document 120
```

- Coverage-mode (recommended for “cover the whole chapter” behavior):
```bash
python3 scripts/generate_qa_from_docx.py qa \
  --input QA_CHAPTERS \
  --output QA_OUTPUT \
  --coverage-mode \
  --coverage-threshold 0.85 \
  --concepts-max 100 \
  --max-qa-per-chapter-safety 100 \
  --max-iterations 16
```

Intermediate JSON schema (QA_CHAPTERS/*.json):
```json
{
  "source_file": "MyDoc.docx",
  "heading_level": 1,
  "extracted_at": "2025-09-02T19:16:00Z",
  "chapters": [
    {
      "index": 1,
      "title": "Chapter Title",
      "content": "Full chapter text ...",
      "char_count": 1234,
      "token_estimate": 308
    }
  ]
}
```

Final Q&A JSON schema (QA_OUTPUT/*.json):
```json
{
  "source_file": "MyDoc.docx",
  "model": "gpt-oss-120b",
  "generated_at": "2025-09-02T19:20:00Z",
  "chapters": [
    {
      "chapter_title": "Chapter Title",
      "question_count": 6,
      "questions": [
        { "question": "…", "answer": "…" }
      ]
    }
  ]
}
```

DOCX export:
- Writes QA_DOCX/<doc_basename>.docx
- Table columns: Question | Answer (no Chapter column)

Progress logging (qa step):
- Per-document header (document name, number of chapters)
- Size-based mode:
  - Per-chapter: index, title, token estimate, target count (with “(doc-cap)” when per-document cap is active)
  - Skips empty chapters; prints number of Q&A generated
- Coverage-mode:
  - Per-chapter: “[coverage-mode]” tag
  - Iteration lines showing coverage progress, e.g.:
    [qa][coverage] 'Chapter Name': iter=2 added=6 covered=26/30 (87%)
  - Final per-chapter Q&A count
- Per-document totals and output path at the end

Notes:
- File naming mirrors the DOCX basename (spaces/case preserved), only extension changes to .json/.docx
- If chapters exceed model context, consider chunking per chapter (not enabled by default)
- Retries: transient provider errors are retried with exponential backoff

------------------------------------------------------------
## Utility Scripts

### scripts/dedupe_tickets.py

Purpose:
- Semantic deduplication of tickets using multilingual embeddings via Scaleway.
- Produces canonical ticket set and audit outputs (see section 2a).

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

### 3a. Deduplicate Ticket Summaries (Optional but recommended)
```bash
# Remove quasi-duplicates; tune thresholds for your data
python3 scripts/dedupe_tickets.py -i Ticket_Data.JSON --threshold 0.84 --threshold-low 0.78

# Use the canonical set for downstream rendering or analytics
python3 tickets_to_docx.py --input tickets_dedup.json
```

### 4. Generate Documents
```bash
# Create PDF from knowledge base
python3 kb_to_pdf.py -i JitBit_Knowledgebase.json -o KB.pdf

# Create DOCX from ticket summaries (deduped set recommended)
python3 tickets_to_docx.py -i tickets_dedup.json -o Tickets.docx
```

## Output Files

The repository generates several output files during processing:

| File | Created By | Content |
|------|------------|---------|
| `JitBit_relevante_Tickets.json` | ticket_relevante_felder.py | Raw ticket data with comments and attachments |
| `JitBit_Knowledgebase.json` | kb_export_json.py | Knowledge base articles with BBCode conversion |
| `Ticket_Data.JSON` | process_tickets_with_llm.py | LLM-processed ticket summaries (relevant only) |
| `tickets_dedup.json` | scripts/dedupe_tickets.py | Canonical tickets with `duplicates` list and `cluster_id` |
| `duplicate_groups.json` | scripts/dedupe_tickets.py | Full cluster membership and representative |
| `needs_review.csv` | scripts/dedupe_tickets.py | Borderline similar pairs to manually check |
| `not relevant.json` | process_tickets_with_llm.py | Raw tickets marked as not relevant by LLM |
| `llm_parse_errors/*.txt` | process_tickets_with_llm.py | Debug files for LLM parsing failures |
| `*.pdf` | kb_to_pdf.py | Formatted PDF documents |
| `*.docx` | tickets_to_docx.py | Formatted Word documents |

### Note on JSON formatting and IDs
- Ticket_Data.JSON is generated with Unicode-safe normalization to prevent JSON parse errors from curly quotes, non-breaking spaces/hyphens, ellipses, and similar characters. See JSON_Unicode_Fix_Documentation.md for the analysis and code examples used to fix these issues.
- ticket_id values in Ticket_Data.JSON are strings prefixed with "S4U_" (e.g., "S4U_98"). Update downstream consumers to treat ticket_id as a string with this prefix.

## Troubleshooting

### API Authentication Issues
- Verify `JITBIT_API_TOKEN` is correct and has sufficient permissions
- Test with `scripts/jitbit_fetch_attachment.py` using a known attachment ID
- Check if your Jitbit instance uses `/helpdesk/api/` or `/api/` endpoints

### LLM Processing Issues  
- Check `llm_parse_errors/` directory for parsing failures
- Verify `SCW_SECRET_KEY` is set and valid; also ensure `SCW_OPENAI_BASE_URL` is `https://api.scaleway.ai/v1/chat/completions`
- Use `--only-ticket-id` flag to debug specific tickets
- Reduce `--max-tokens` if hitting model limits

### Embeddings/Dedupe Issues
- Ensure `SCW_SECRET_KEY`/`SCW_API_KEY` and `SCW_OPENAI_BASE_URL` are set
- If no merges are found, lower `--threshold` slightly (e.g., 0.82) and re-run
- If false merges occur, raise `--threshold` (e.g., 0.86) or increase gray zone by raising `--threshold-low`
- Review `duplicate_groups.json` and `needs_review.csv` to calibrate thresholds

### Memory Issues with Large Datasets
- Install `ijson` for streaming: `pip3 install -U ijson` 
- Avoid `--newest-first` and install ijson to enable streaming
- Process in smaller batches using `--limit` and `--start-index`

### Image/Attachment Issues
- For protected images, ensure proper authentication (cookies or API tokens)
- Use `--verbose` flag to debug image download failures  
- Check Content-Type headers for non-image content
- Verify URLs are accessible from your network
