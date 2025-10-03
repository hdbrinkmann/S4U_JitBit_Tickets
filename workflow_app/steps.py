"""
Subprocess wrappers for calling existing scripts with proper logging and error handling.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from .config import (
    SCRIPTS, FILE_NAMES, DEFAULTS, get_repo_root, make_absolute_path
)
from .logging import RunLogger, StreamCapture
from .util import should_skip_step, update_step_status, copy_artifact_to_run, validate_json_file, file_exists_and_not_empty
from .subprocess_runner import execute_subprocess_realtime


class StepResult:
    """Result of executing a workflow step."""
    
    def __init__(self, success: bool, message: str = "", output_files: List[str] = None, 
                 skipped: bool = False, duration_seconds: float = 0.0):
        self.success = success
        self.message = message
        self.output_files = output_files or []
        self.skipped = skipped
        self.duration_seconds = duration_seconds


def execute_subprocess(cmd: List[str], logger: RunLogger, timeout: int = 3600) -> tuple:
    """Execute subprocess with proper logging and timeout."""
    logger.command(" ".join(cmd))
    
    try:
        # Set environment variables for unbuffered output
        env = dict(os.environ)
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        
        # Execute the command with real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            cwd=get_repo_root(),
            env=env,
            bufsize=1,  # Line buffered
            universal_newlines=True
        )
        
        # Stream output in real time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                # Log the output immediately with timestamp
                logger.subprocess_output(output.rstrip())
        
        # Wait for process to complete and get return code
        return_code = process.returncode
        if return_code is None:
            return_code = process.wait(timeout=timeout)
        
        return return_code, "Process completed", ""
        
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds")
        try:
            process.kill()
            process.wait(timeout=10)
        except Exception:
            pass
        return 1, f"Command timed out after {timeout} seconds", ""
        
    except Exception as e:
        error_msg = f"Failed to execute command: {e}"
        logger.error(error_msg)
        return 1, error_msg, str(e)


def run_step(step_name: str, cmd: List[str], expected_outputs: List[str], 
             run_dir: Path, logger: RunLogger, options: Dict[str, Any]) -> StepResult:
    """Run a single workflow step with proper error handling and status tracking."""
    start_time = time.time()
    
    # Check if step should be skipped
    overwrite = options.get("overwrite", DEFAULTS["OVERWRITE"])
    skip_existing = options.get("skip_existing", DEFAULTS["SKIP_EXISTING"])
    
    # If overwrite is enabled, never skip
    if overwrite:
        logger.info(f"Running {step_name} (overwrite mode)")
    elif skip_existing and should_skip_step(run_dir, expected_outputs, skip_existing):
        logger.info(f"Skipping {step_name} - outputs already exist")
        update_step_status(run_dir, step_name, "skipped")
        return StepResult(success=True, message="Skipped - outputs exist", 
                         output_files=expected_outputs, skipped=True)
    
    # Update status to running
    update_step_status(run_dir, step_name, "running")
    logger.step_start(step_name)
    
    try:
        # Execute the command with real-time output
        return_code = execute_subprocess_realtime(cmd, logger, timeout=3600)
        message = "Process completed"
        error = ""
        
        duration = time.time() - start_time
        
        if return_code == 0:
            # Post-validate expected outputs to ensure the step actually produced them
            repo_root = get_repo_root()
            missing_or_invalid = []
            for output_file in expected_outputs:
                full_path = repo_root / output_file
                if output_file.endswith(".json"):
                    if not validate_json_file(full_path):
                        missing_or_invalid.append(output_file)
                else:
                    if not file_exists_and_not_empty(full_path):
                        missing_or_invalid.append(output_file)
            
            if missing_or_invalid:
                error_msg = f"Expected outputs missing or invalid: {', '.join(missing_or_invalid)}"
                logger.step_end(step_name, success=False)
                update_step_status(run_dir, step_name, "failed", error_msg)
                return StepResult(success=False, message=error_msg, duration_seconds=duration)
            
            logger.step_end(step_name, success=True)
            update_step_status(run_dir, step_name, "success")
            
            # Copy artifacts to run directory
            for output_file in expected_outputs:
                copy_artifact_to_run(run_dir, output_file)
            
            return StepResult(success=True, message="Step completed successfully", 
                             output_files=expected_outputs, duration_seconds=duration)
        else:
            error_msg = f"Step failed with return code {return_code}: {message}"
            logger.step_end(step_name, success=False)
            update_step_status(run_dir, step_name, "failed", error_msg)
            
            return StepResult(success=False, message=error_msg, 
                             duration_seconds=duration)
            
    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"Step failed with exception: {e}"
        logger.error(error_msg)
        logger.step_end(step_name, success=False)
        update_step_status(run_dir, step_name, "failed", error_msg)
        
        return StepResult(success=False, message=error_msg, 
                         duration_seconds=duration)


# Jitbit workflow steps

def step_jitbit_export_tickets(params: Dict[str, Any], run_dir: Path, logger: RunLogger, 
                              options: Dict[str, Any]) -> StepResult:
    """Export Jitbit tickets."""
    start_id = params["start_id"]
    cmd = [
        sys.executable, 
        SCRIPTS["JITBIT_EXPORT"],
        "--start-id", str(start_id),
        "--yes"
    ]
    
    expected_outputs = [FILE_NAMES["JITBIT_EXPORT"]]
    return run_step("Export Jitbit Tickets", cmd, expected_outputs, run_dir, logger, options)


def step_jitbit_export_kb(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                         options: Dict[str, Any]) -> StepResult:
    """Export Jitbit knowledge base."""
    cmd = [
        sys.executable,
        SCRIPTS["JITBIT_KB_EXPORT"],
        "--out", FILE_NAMES["JITBIT_KB_EXPORT"],
        "--yes"
    ]
    
    expected_outputs = [FILE_NAMES["JITBIT_KB_EXPORT"]]
    return run_step("Export Jitbit Knowledge Base", cmd, expected_outputs, run_dir, logger, options)


def step_jitbit_process_llm(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                           options: Dict[str, Any]) -> StepResult:
    """Process Jitbit tickets with LLM."""
    cmd = [
        sys.executable,
        SCRIPTS["LLM_PROCESS"],
        "--input", FILE_NAMES["JITBIT_EXPORT"],
        "--output", FILE_NAMES["JITBIT_LLM_OUTPUT"],
        "--not-relevant-out", FILE_NAMES["JITBIT_NOT_RELEVANT"]
    ]
    
    # Add optional parameters
    if params.get("llm_limit"):
        cmd.extend(["--limit", str(params["llm_limit"])])
    if params.get("llm_max_calls"):
        cmd.extend(["--max-calls", str(params["llm_max_calls"])])
    if options.get("append"):
        cmd.append("--append")
    if params.get("newest_first"):
        cmd.append("--newest-first")
    
    save_interval = params.get("llm_save_interval", DEFAULTS["LLM_SAVE_INTERVAL"])
    cmd.extend(["--save-interval", str(save_interval)])
    
    expected_outputs = [FILE_NAMES["JITBIT_LLM_OUTPUT"], FILE_NAMES["JITBIT_NOT_RELEVANT"]]
    return run_step("Process Jitbit Tickets with LLM", cmd, expected_outputs, run_dir, logger, options)


def step_jitbit_tickets_to_docx(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                               options: Dict[str, Any]) -> StepResult:
    """Generate DOCX files from Jitbit tickets."""
    cmd = [
        sys.executable,
        SCRIPTS["TICKETS_TO_DOCX"],
        "--input", FILE_NAMES["JITBIT_LLM_OUTPUT"],
        "--output-dir", FILE_NAMES["JITBIT_DOCX_DIR"],
        "--verbose", "true"
    ]
    
    expected_outputs = [FILE_NAMES["JITBIT_DOCX_DIR"]]
    return run_step("Generate DOCX from Jitbit Tickets", cmd, expected_outputs, run_dir, logger, options)


def step_jitbit_kb_to_docx(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                          options: Dict[str, Any]) -> StepResult:
    """Generate DOCX file from Jitbit knowledge base."""
    cmd = [
        sys.executable,
        SCRIPTS["KB_TO_DOCX"],
        "--input", FILE_NAMES["JITBIT_KB_EXPORT"],
        "--output", FILE_NAMES["JITBIT_KB_DOCX"]
    ]
    
    expected_outputs = [FILE_NAMES["JITBIT_KB_DOCX"]]
    return run_step("Generate DOCX from Jitbit Knowledge Base", cmd, expected_outputs, run_dir, logger, options)


# Jira workflow steps

def step_jira_export_tickets(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                            options: Dict[str, Any]) -> StepResult:
    """Export Jira tickets."""
    project = params["project"]
    resolved_after = params["resolved_after"]
    
    # Build JQL
    jql = f"project={project} order by resolutiondate DESC"
    
    # Use project-specific output file
    export_file_key = f"JIRA_EXPORT_{project}" if project in ["SUP", "TMS"] else "JIRA_EXPORT"
    export_file = FILE_NAMES.get(export_file_key, FILE_NAMES["JIRA_EXPORT"])
    
    cmd = [
        sys.executable,
        SCRIPTS["JIRA_EXPORT"],
        "--jql", jql,
        "--resolved-only",
        "--resolved-after", resolved_after,
        "--export", export_file
    ]
    
    # Add optional parameters
    if params.get("resolved_before"):
        cmd.extend(["--resolved-before", params["resolved_before"]])
    if params.get("jira_limit"):
        cmd.extend(["--limit", str(params["jira_limit"])])
    if options.get("append"):
        cmd.append("--append")
    if params.get("progress"):
        cmd.append("--progress")
    
    expected_outputs = [export_file]
    return run_step("Export Jira Tickets", cmd, expected_outputs, run_dir, logger, options)


def step_jira_process_llm(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                         options: Dict[str, Any]) -> StepResult:
    """Process Jira tickets with LLM."""
    project = params.get("project", "SUP")  # Default to SUP for backward compatibility
    
    # Use project-specific file names
    export_file_key = f"JIRA_EXPORT_{project}" if project in ["SUP", "TMS"] else "JIRA_EXPORT"
    llm_output_file_key = f"JIRA_LLM_OUTPUT_{project}" if project in ["SUP", "TMS"] else "JIRA_LLM_OUTPUT"
    not_relevant_file_key = f"JIRA_NOT_RELEVANT_{project}" if project in ["SUP", "TMS"] else "JIRA_NOT_RELEVANT"
    
    export_file = FILE_NAMES.get(export_file_key, FILE_NAMES["JIRA_EXPORT"])
    llm_output_file = FILE_NAMES.get(llm_output_file_key, FILE_NAMES["JIRA_LLM_OUTPUT"])
    not_relevant_file = FILE_NAMES.get(not_relevant_file_key, FILE_NAMES["JIRA_NOT_RELEVANT"])
    
    cmd = [
        sys.executable,
        SCRIPTS["LLM_PROCESS"],
        "--input", export_file,
        "--output", llm_output_file,
        "--not-relevant-out", not_relevant_file
    ]
    
    # Add optional parameters
    if params.get("llm_limit"):
        cmd.extend(["--limit", str(params["llm_limit"])])
    if params.get("llm_max_calls"):
        cmd.extend(["--max-calls", str(params["llm_max_calls"])])
    if options.get("append"):
        cmd.append("--append")
    
    expected_outputs = [llm_output_file, not_relevant_file]
    return run_step("Process Tickets with LLM", cmd, expected_outputs, run_dir, logger, options)


def step_jira_deduplicate(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                         options: Dict[str, Any]) -> StepResult:
    """Deduplicate Jira tickets."""
    project = params.get("project", "SUP")  # Default to SUP for backward compatibility
    
    # Use project-specific file names
    llm_output_file_key = f"JIRA_LLM_OUTPUT_{project}" if project in ["SUP", "TMS"] else "JIRA_LLM_OUTPUT"
    dedup_output_file_key = f"JIRA_DEDUP_OUTPUT_{project}" if project in ["SUP", "TMS"] else "JIRA_DEDUP_OUTPUT"
    dedup_groups_file_key = f"JIRA_DEDUP_GROUPS_{project}" if project in ["SUP", "TMS"] else "JIRA_DEDUP_GROUPS"
    dedup_review_file_key = f"JIRA_DEDUP_REVIEW_{project}" if project in ["SUP", "TMS"] else "JIRA_DEDUP_REVIEW"
    
    llm_output_file = FILE_NAMES.get(llm_output_file_key, FILE_NAMES["JIRA_LLM_OUTPUT"])
    dedup_output_file = FILE_NAMES.get(dedup_output_file_key, FILE_NAMES["JIRA_DEDUP_OUTPUT"])
    dedup_groups_file = FILE_NAMES.get(dedup_groups_file_key, FILE_NAMES["JIRA_DEDUP_GROUPS"])
    dedup_review_file = FILE_NAMES.get(dedup_review_file_key, FILE_NAMES["JIRA_DEDUP_REVIEW"])
    
    threshold = params.get("dedup_threshold", DEFAULTS["DEDUP_THRESHOLD"])
    threshold_low = params.get("dedup_threshold_low", DEFAULTS["DEDUP_THRESHOLD_LOW"])
    
    cmd = [
        sys.executable,
        SCRIPTS["DEDUP"],
        "--input", llm_output_file,
        "--out", dedup_output_file,
        "--groups-out", dedup_groups_file,
        "--review-out", dedup_review_file,
        "--threshold", str(threshold),
        "--threshold-low", str(threshold_low)
    ]
    
    expected_outputs = [
        dedup_output_file,
        dedup_groups_file,
        dedup_review_file
    ]
    return run_step("Deduplicate Tickets", cmd, expected_outputs, run_dir, logger, options)


def step_jira_tickets_to_docx(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                              options: Dict[str, Any]) -> StepResult:
    """Generate DOCX files from Jira tickets (using deduplicated data by default)."""
    project = params.get("project", "SUP")  # Default to SUP for backward compatibility

    # Use project-specific file names
    dedup_output_file_key = f"JIRA_DEDUP_OUTPUT_{project}" if project in ["SUP", "TMS"] else "JIRA_DEDUP_OUTPUT"
    llm_output_file_key = f"JIRA_LLM_OUTPUT_{project}" if project in ["SUP", "TMS"] else "JIRA_LLM_OUTPUT"
    docx_dir_key = f"JIRA_DOCX_DIR_{project}" if project in ["SUP", "TMS"] else "JIRA_DOCX_DIR"

    dedup_output_file = FILE_NAMES.get(dedup_output_file_key, FILE_NAMES["JIRA_DEDUP_OUTPUT"])
    llm_output_file = FILE_NAMES.get(llm_output_file_key, FILE_NAMES["JIRA_LLM_OUTPUT"])
    docx_dir = FILE_NAMES.get(docx_dir_key, FILE_NAMES["JIRA_DOCX_DIR"])

    # Use deduplicated file if it exists, otherwise use regular LLM output
    repo_root = get_repo_root()
    dedup_file_path = repo_root / dedup_output_file

    if dedup_file_path.exists():
        input_file = dedup_output_file
    else:
        input_file = llm_output_file

    cmd = [
        sys.executable,
        SCRIPTS["TICKETS_TO_DOCX"],
        "--input", input_file,
        "--output-dir", docx_dir,
        "--verbose", "true"
    ]

    expected_outputs = [docx_dir]
    return run_step("Generate DOCX from Tickets", cmd, expected_outputs, run_dir, logger, options)


# WebCRM workflow steps

def step_webcrm_download_documents(params: Dict[str, Any], run_dir: Path, logger: RunLogger,
                                  options: Dict[str, Any]) -> StepResult:
    """Download documents from WebCRM."""
    extensions = params.get("extensions", ["pdf", "docx", "doc", "rtf"])
    folders = params.get("folders", ["Contracts", "Data Processing Agreement", "Sales Terms"])
    skip_existing = params.get("skip_existing", True)

    cmd = [
        sys.executable,
        SCRIPTS["WEBCRM_DOWNLOAD"],
        "--extensions"
    ] + extensions + [
        "--folders"
    ] + folders

    if skip_existing:
        cmd.append("--skip-existing")

    # For download workflows, we always want to run to check for new files
    # Set overwrite=True to ensure the step always executes
    download_options = {**options, "overwrite": True}
    expected_outputs = [FILE_NAMES["WEBCRM_DOCUMENTS_DIR"], FILE_NAMES["WEBCRM_DOWNLOAD_LOG"]]
    return run_step("Download WebCRM Documents", cmd, expected_outputs, run_dir, logger, download_options)
