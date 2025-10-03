# Workflow Automation System for Jitbit, Jira, and WebCRM

A comprehensive Python application that automates ticket processing workflows for Jitbit, Jira, and WebCRM with LLM-powered analysis and document generation. The system provides both a modern web interface and CLI tools for complete end-to-end processing.

## 🚀 Quick Start

### Web Interface (Recommended)
```bash
# Install dependencies
pip install -r requirements.txt

# Start the web server
python3 cli.py web --port 8787

# Open browser to: http://127.0.0.1:8787
```

### CLI Interface
```bash
# Check environment configuration
python3 cli.py env-check

# Run Jitbit workflow
python3 cli.py run-jitbit --start-id 23000

# Run Jira workflow
python3 cli.py run-jira --project SUP --resolved-after 2024-01-01

# Run WebCRM workflow
python3 cli.py run-webcrm --extensions pdf docx --folders "Contracts" "Sales Terms"
```

## 📋 Overview

The Workflow Automation System provides three main workflows:

### 🔧 Jitbit Workflow (6 steps)
1. **Environment Validation** - Verify API tokens and URLs
2. **Export Tickets** - Extract closed tickets from Jitbit API
3. **Export Knowledge Base** - Download KB articles with BBCode conversion
4. **LLM Processing** - Analyze tickets for relevance and generate summaries
5. **Generate Ticket DOCX** - Create Word documents from processed tickets
6. **Generate KB DOCX** - Create Word documents from knowledge base

### 🎯 Jira Workflow (5 steps)
1. **Environment Validation** - Verify Jira and LLM credentials
2. **Export Tickets** - Extract resolved issues with project filtering
3. **LLM Processing** - Analyze tickets for relevance and generate summaries
4. **Deduplication** - Remove quasi-duplicate tickets using semantic similarity
5. **Generate DOCX** - Create Word documents from deduplicated data

### 📄 WebCRM Workflow (2 steps)
1. **Environment Validation** - Verify WebCRM API access
2. **Download Documents** - Bulk download documents from specified folders

## 🌟 Features

### Modern Web Interface
- **Beautiful Dashboard** - Visual environment status indicators and workflow cards
- **Interactive Forms** - Full parameter control with validation
- **Real-time Progress** - Live execution logs with step-by-step tracking
- **Run Management** - Browse history, view artifacts, and manage executions
- **Background Processing** - Workflows continue running even if browser is closed

### Advanced Workflow Controls
- **Skip/Overwrite Logic** - Intelligent handling of existing outputs
- **LLM Processing Controls** - Cost management with limits and save intervals
- **Project Support** - Separate processing for SUP and TMS Jira projects
- **Deduplication** - Semantic similarity analysis with configurable thresholds

### Security & Reliability
- **Local Execution** - All data remains on your machine
- **Credential Protection** - Sensitive data redacted from logs
- **Error Recovery** - Graceful failure handling with detailed diagnostics
- **Run Isolation** - Each workflow gets its own timestamped directory

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Setup
```bash
# Clone the repository
git clone <repository-url>
cd workflow-automation

# Install dependencies
pip install -r requirements.txt

# Install additional dependencies for web interface
pip install typer fastapi uvicorn jinja2 python-multipart

# Create environment file
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Environment Configuration

Create a `.env` file in the repository root:

```bash
# Jitbit Configuration
JITBIT_API_TOKEN=your_jitbit_bearer_token_here
JITBIT_BASE_URL=https://support.example.com

# Jira Configuration
JIRA_EMAIL=your_atlassian_email@example.com
JIRA_API_TOKEN=your_jira_api_token

# WebCRM Configuration
WEBCRM_API_KEY=your_webcrm_api_key_here

# LLM Configuration (Scaleway AI Gateway)
SCW_SECRET_KEY=your_scaleway_api_key_here
SCW_OPENAI_BASE_URL=https://api.scaleway.ai/v1/chat/completions
LLM_MODEL=gpt-oss-120b

# Optional Configuration
SCW_DEFAULT_PROJECT_ID=your_project_id
SCW_DEFAULT_ORGANIZATION_ID=your_org_id
SCW_REGION=fr-par
SCW_EMBEDDING_MODEL=bge-multilingual-gemma2

# Web Interface Configuration
WORKFLOW_APP_PORT=8787
WORKFLOW_APP_HOST=127.0.0.1
WORKFLOW_APP_AUTO_PORT=1
```

## 📊 Web Interface Features

### Dashboard
- **Environment Status** - 7-point validation with visual indicators
- **Workflow Cards** - Quick access to Jitbit, Jira, and WebCRM workflows
- **Recent Runs** - Latest workflow executions with status indicators

### Workflow Forms

#### Jitbit Form
- **Start Ticket ID** - Starting ticket ID for export
- **LLM Options** - Limit, max calls, save interval, newest-first processing
- **Run Options** - Skip existing, overwrite, append modes

#### Jira Form
- **Project Selection** - SUP (Danish Support) or TMS (Timemap Support)
- **Date Range** - Resolved after/before dates for filtering
- **Advanced Options** - Progress mode, deduplication thresholds
- **LLM Controls** - Processing limits and API call caps

#### WebCRM Form
- **File Extensions** - Select file types to download (pdf, docx, doc, rtf)
- **Folder Selection** - Choose folders to scan
- **Skip Existing** - Avoid re-downloading existing files

### Real-time Progress Tracking
- **Visual Timeline** - Step-by-step progress with status indicators
- **Live Logs** - Real-time script output with auto-scrolling
- **Generated Artifacts** - Direct links to output files
- **Run History** - Complete execution history with detailed logs

## 🔧 CLI Commands

### Environment Check
```bash
python3 cli.py env-check
```

### Jitbit Workflow
```bash
# Basic usage
python3 cli.py run-jitbit --start-id 23000

# With LLM limits
python3 cli.py run-jitbit --start-id 23000 --llm-limit 100 --llm-max-calls 200

# Process newest tickets first
python3 cli.py run-jitbit --start-id 23000 --newest-first

# Append to existing outputs
python3 cli.py run-jitbit --start-id 23000 --append
```

### Jira Workflow
```bash
# Basic SUP project workflow
python3 cli.py run-jira --project SUP --resolved-after 2024-01-01

# TMS project with date range
python3 cli.py run-jira --project TMS --resolved-after 2024-01-01 --resolved-before 2024-12-31

# With custom deduplication thresholds
python3 cli.py run-jira --project SUP --resolved-after 2024-01-01 --dedup-threshold 0.82 --dedup-threshold-low 0.76

# Skip deduplication
python3 cli.py run-jira --project SUP --resolved-after 2024-01-01 --skip-dedup
```

### Web Server
```bash
# Default port 8787
python3 cli.py web

# Custom port
python3 cli.py web --port 8080

# Auto-port fallback (tries 8787→8788→8789)
python3 cli.py web --auto-port
```

## 📁 Project Structure

```
workflow-automation/
├── cli.py                          # Main CLI entry point
├── workflow_app/                   # Core workflow orchestration
│   ├── __init__.py
│   ├── config.py                   # Configuration constants
│   ├── envcheck.py                 # Environment validation
│   ├── flows.py                    # High-level workflow orchestration
│   ├── logging.py                  # Run logging utilities
│   ├── steps.py                    # Individual workflow steps
│   ├── subprocess_runner.py        # Subprocess execution
│   └── util.py                     # Utility functions
├── web/                            # Web interface
│   ├── main.py                     # FastAPI application
│   └── templates/                  # Jinja2 templates
│       ├── base.html
│       ├── index.html
│       ├── jitbit_form.html
│       ├── jira_form.html
│       ├── webcrm_form.html
│       ├── run_dashboard.html
│       └── runs_list.html
├── scripts/                        # Utility scripts
│   ├── dedupe_tickets.py           # Semantic deduplication
│   ├── generate_qa_from_docx.py    # Q&A generation
│   ├── jitbit_fetch_attachment.py  # Attachment downloader
│   └── test_llm_parse_errors.py    # LLM debugging
├── ticket_relevante_felder.py      # Jitbit ticket exporter
├── jira_relevant_tickets.py        # Jira ticket exporter
├── kb_export_json.py               # Knowledge base exporter
├── process_tickets_with_llm.py     # LLM ticket processor
├── tickets_to_docx.py              # DOCX generator for tickets
├── kb_to_docx.py                   # DOCX generator for KB
├── download_all_webcrm_docs.py     # WebCRM document downloader
├── requirements.txt                # Python dependencies
└── .env.example                    # Environment template
```

## 📄 Output Files

### Jitbit Workflow Outputs
- `JitBit_relevante_Tickets.json` - Raw ticket data with comments and attachments
- `JitBit_Knowledgebase.json` - Knowledge base articles with BBCode conversion
- `Ticket_Data_Jitbit.json` - LLM-processed ticket summaries
- `Not_Relevant_Jitbit.json` - Tickets marked as not relevant by LLM
- `documents/jitbit/` - Generated DOCX files

### Jira Workflow Outputs
- `JIRA_relevante_Tickets_[PROJECT].json` - Raw ticket data (project-specific)
- `Ticket_Data_Jira_[PROJECT].json` - LLM-processed summaries
- `tickets_dedup_Jira_[PROJECT].json` - Deduplicated tickets
- `duplicate_groups_Jira_[PROJECT].json` - Deduplication clusters
- `needs_review_Jira_[PROJECT].csv` - Borderline similar pairs
- `documents/jira/[PROJECT]/` - Generated DOCX files

### WebCRM Workflow Outputs
- `webcrm_documents/` - Downloaded documents organized by type
- `webcrm_documents/DOWNLOAD_LOG.txt` - Detailed download log

## 🔍 Troubleshooting

### Environment Issues
```bash
# Check all environment variables
python3 cli.py env-check

# Verify specific service
python3 -c "from workflow_app.envcheck import check_jitbit_env; print(check_jitbit_env())"
```

### LLM Processing Issues
- Check `llm_parse_errors/` directory for parsing failures
- Verify Scaleway credentials and base URL
- Use `--only-ticket-id` flag for debugging specific tickets
- Reduce `--max-tokens` if hitting model limits

### Deduplication Issues
- Lower `--dedup-threshold` if too few merges (try 0.82)
- Raise threshold if false merges occur (try 0.86)
- Review `duplicate_groups.json` and `needs_review.csv`

### Memory Issues
- Install `ijson` for streaming large files: `pip install ijson`
- Avoid `--newest-first` for very large datasets
- Process in smaller batches using `--limit` and `--start-index`

### Image/Attachment Issues
- Verify API tokens have sufficient permissions
- Use `--verbose` flag for detailed download logs
- Check network connectivity to attachment URLs

## 🚀 Advanced Usage

### Custom LLM Models
```bash
# Use different model
export LLM_MODEL="custom-model-name"
python3 cli.py run-jitbit --start-id 23000
```

### Batch Processing
```bash
# Process multiple date ranges
for date in 2024-01-01 2024-02-01 2024-03-01; do
    python3 cli.py run-jira --project SUP --resolved-after $date --resolved-after $(date -d "$date +1 month" +%Y-%m-%d)
done
```

### Custom Deduplication
```bash
# Aggressive deduplication
python3 cli.py run-jira --project SUP --resolved-after 2024-01-01 --dedup-threshold 0.78 --dedup-threshold-low 0.72

# Conservative deduplication
python3 cli.py run-jira --project SUP --resolved-after 2024-01-01 --dedup-threshold 0.88 --dedup-threshold-low 0.82
```

## 📚 API Reference

### Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `JITBIT_API_TOKEN` | Yes | Jitbit Bearer token |
| `JITBIT_BASE_URL` | Yes | Jitbit instance URL |
| `JIRA_EMAIL` | Yes | Atlassian account email |
| `JIRA_API_TOKEN` | Yes | Jira API token |
| `WEBCRM_API_KEY` | Yes | WebCRM API key |
| `SCW_SECRET_KEY` | Yes | Scaleway API key |
| `SCW_OPENAI_BASE_URL` | Yes | Scaleway AI Gateway URL |
| `LLM_MODEL` | No | LLM model name (default: gpt-oss-120b) |

### Default Configuration
| Setting | Default | Description |
|---------|---------|-------------|
| `WORKFLOW_APP_PORT` | 8787 | Web server port |
| `LLM_SAVE_INTERVAL` | 50 | Save progress every N tickets |
| `DEDUP_THRESHOLD` | 0.84 | High similarity threshold |
| `DEDUP_THRESHOLD_LOW` | 0.78 | Low similarity threshold |
| `DOCX_TICKETS_PER_FILE` | 50 | Tickets per DOCX file |
| `SKIP_EXISTING` | True | Skip steps with existing outputs |
| `OVERWRITE` | False | Force re-run all steps |
| `APPEND` | False | Append to existing outputs |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes and add tests
4. Commit your changes: `git commit -am 'Add feature'`
5. Push to the branch: `git push origin feature-name`
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔗 Support

For support and questions:
- Check the troubleshooting section above
- Review run logs in the `runs/` directory
- Use `python3 cli.py env-check` to verify configuration
- Check the wiki for detailed guides and examples

---

**Note**: This application processes sensitive ticket data. Ensure proper security measures are in place and that all API credentials are stored securely.
