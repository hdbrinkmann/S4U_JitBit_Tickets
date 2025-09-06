"""
Configuration constants, file names, and environment variable names.
"""

import os
from pathlib import Path
from typing import Dict, List

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv not available, continue without it
    pass

# Default port configuration (never 8000 per requirements)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_PORT_RANGE = [8787, 8788, 8789]

# Environment variable names
ENV_VARS = {
    # Jitbit
    "JITBIT_API_TOKEN": "JITBIT_API_TOKEN",
    "JITBIT_BASE_URL": "JITBIT_BASE_URL",
    
    # Jira
    "JIRA_EMAIL": "JIRA_EMAIL", 
    "JIRA_API_TOKEN": "JIRA_API_TOKEN",
    
    # LLM (Scaleway)
    "SCW_SECRET_KEY": "SCW_SECRET_KEY",
    "SCW_API_KEY": "SCW_API_KEY", 
    "SCW_OPENAI_BASE_URL": "SCW_OPENAI_BASE_URL",
    "LLM_MODEL": "LLM_MODEL",
    
    # Web UI
    "WORKFLOW_APP_PORT": "WORKFLOW_APP_PORT",
    "WORKFLOW_APP_HOST": "WORKFLOW_APP_HOST",
    "WORKFLOW_APP_AUTO_PORT": "WORKFLOW_APP_AUTO_PORT"
}

# File naming conventions per the implementation plan
FILE_NAMES = {
    # Jitbit flow
    "JITBIT_EXPORT": "JitBit_relevante_Tickets.json",
    "JITBIT_KB_EXPORT": "JitBit_Knowledgebase.json", 
    "JITBIT_LLM_OUTPUT": "Ticket_Data_Jitbit.json",
    "JITBIT_NOT_RELEVANT": "Not_Relevant_Jitbit.json",
    "JITBIT_DOCX_DIR": "documents/jitbit",
    "JITBIT_KB_DOCX": "documents/jitbit/Knowledgebase.docx",
    
    # Jira flow
    "JIRA_EXPORT": "JIRA_relevante_Tickets.json",
    "JIRA_LLM_OUTPUT": "Ticket_Data_Jira.json", 
    "JIRA_NOT_RELEVANT": "Not_Relevant_Jira.json",
    "JIRA_DEDUP_OUTPUT": "tickets_dedup_Jira.json",
    "JIRA_DEDUP_GROUPS": "duplicate_groups_Jira.json",
    "JIRA_DEDUP_REVIEW": "needs_review_Jira.csv",
    "JIRA_DOCX_DIR": "documents/jira"
}

# Default script parameters
DEFAULTS = {
    # LLM processing
    "LLM_SAVE_INTERVAL": 50,
    "LLM_MAX_CALLS": None,
    "LLM_LIMIT": None,
    
    # Jira deduplication thresholds
    "DEDUP_THRESHOLD": 0.84,
    "DEDUP_THRESHOLD_LOW": 0.78,
    
    # DOCX generation
    "DOCX_TICKETS_PER_FILE": 50,
    
    # Run options
    "SKIP_EXISTING": True,
    "OVERWRITE": False,
    "APPEND": False
}

# Script paths (relative to repository root)
SCRIPTS = {
    "JITBIT_EXPORT": "ticket_relevante_felder.py",
    "JITBIT_KB_EXPORT": "kb_export_json.py", 
    "JIRA_EXPORT": "jira_relevant_tickets.py",
    "LLM_PROCESS": "process_tickets_with_llm.py",
    "DEDUP": "scripts/dedupe_tickets.py",
    "TICKETS_TO_DOCX": "tickets_to_docx.py",
    "KB_TO_DOCX": "kb_to_docx.py"
}

# Jira project options
JIRA_PROJECTS = ["SUP", "TMS"]

# Run directory configuration
RUN_DIR_PREFIX = "runs"
RUN_STATUS_FILE = "status.json"
RUN_PARAMS_FILE = "params.json"
RUN_LOG_FILE = "flow.log"
RUN_ARTIFACTS_DIR = "artifacts"

def get_env_var(key: str) -> str:
    """Get environment variable value."""
    return os.getenv(key, "").strip()

def get_port() -> int:
    """Get configured port from environment or default."""
    port_str = get_env_var(ENV_VARS["WORKFLOW_APP_PORT"])
    if port_str.isdigit():
        return int(port_str)
    return DEFAULT_PORT

def get_host() -> str:
    """Get configured host from environment or default."""
    host = get_env_var(ENV_VARS["WORKFLOW_APP_HOST"])
    return host if host else DEFAULT_HOST

def should_auto_port() -> bool:
    """Check if auto port fallback is enabled."""
    return get_env_var(ENV_VARS["WORKFLOW_APP_AUTO_PORT"]) == "1"

def get_repo_root() -> Path:
    """Get the repository root directory."""
    # This assumes the workflow_app package is at repo root level
    return Path(__file__).parent.parent

def make_absolute_path(relative_path: str) -> Path:
    """Convert relative path to absolute path from repo root."""
    return get_repo_root() / relative_path

def ensure_dir(path: Path) -> None:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)
