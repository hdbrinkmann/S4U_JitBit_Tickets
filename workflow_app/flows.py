"""
High-level flow orchestration for Jitbit and Jira workflows.
"""

import time
from pathlib import Path
from typing import Dict, Any, List

from .logging import RunLogger, create_run_logger, log_run_start, log_run_end
from .util import (
    generate_run_id, create_run_directory, save_run_params, 
    init_run_status, update_step_status
)
from .steps import (
    # Jitbit steps
    step_jitbit_export_tickets, step_jitbit_export_kb, step_jitbit_process_llm,
    step_jitbit_tickets_to_docx, step_jitbit_kb_to_docx,
    # Jira steps  
    step_jira_export_tickets, step_jira_process_llm, step_jira_deduplicate,
    step_jira_tickets_to_docx,
    StepResult
)
from .envcheck import check_jitbit_env, check_jira_env, check_llm_env


class FlowResult:
    """Result of executing a complete workflow."""
    
    def __init__(self, success: bool, run_id: str, run_dir: Path, message: str = "", 
                 step_results: List[StepResult] = None, duration_seconds: float = 0.0):
        self.success = success
        self.run_id = run_id
        self.run_dir = run_dir
        self.message = message
        self.step_results = step_results or []
        self.duration_seconds = duration_seconds


def validate_env_for_flow(flow_name: str) -> tuple:
    """Validate environment variables required for the specified flow."""
    errors = []
    
    if flow_name == "jitbit":
        # Check Jitbit + LLM environment
        jitbit_results = check_jitbit_env()
        llm_results = check_llm_env()
        
        for result in jitbit_results + llm_results:
            if not result.is_ok:
                errors.append(result.message)
                
    elif flow_name == "jira":
        # Check Jira + LLM environment
        jira_results = check_jira_env()
        llm_results = check_llm_env()
        
        for result in jira_results + llm_results:
            if not result.is_ok:
                errors.append(result.message)
    else:
        errors.append(f"Unknown flow: {flow_name}")
    
    return len(errors) == 0, errors


def run_jitbit_flow(params: Dict[str, Any], options: Dict[str, Any] = None, 
                    run_id: str = None, run_dir: Path = None) -> FlowResult:
    """
    Run the complete Jitbit workflow.
    
    Steps:
    1. Validate environment
    2. Export tickets
    3. Export knowledge base
    4. Process with LLM
    5. Generate DOCX for tickets
    6. Generate DOCX for knowledge base
    """
    if options is None:
        options = {}
    
    # Use provided run_id/run_dir or create new ones
    if run_id is None:
        run_id = generate_run_id("jitbit")
    if run_dir is None:
        run_dir = create_run_directory(run_id)
    
    # Define workflow steps
    step_names = [
        "Validate Environment",
        "Export Jitbit Tickets", 
        "Export Jitbit Knowledge Base",
        "Process Tickets with LLM",
        "Generate DOCX from Tickets",
        "Generate DOCX from Knowledge Base"
    ]
    
    # Initialize run tracking only if not already initialized
    from pathlib import Path
    status_file = run_dir / "status.json"
    if not status_file.exists():
        init_run_status(run_dir, step_names)
    save_run_params(run_dir, {**params, "flow": "jitbit", **options})
    
    # Create logger
    console_output = options.get("console_output", True)
    logger = create_run_logger(run_dir, console_output)
    
    start_time = time.time()
    step_results = []
    
    try:
        log_run_start(logger, "Jitbit", params)
        
        # Step 1: Validate environment
        logger.step_start("Validate Environment")
        update_step_status(run_dir, "Validate Environment", "running")
        
        env_valid, env_errors = validate_env_for_flow("jitbit")
        if not env_valid:
            error_msg = "Environment validation failed: " + "; ".join(env_errors)
            logger.error(error_msg)
            logger.step_end("Validate Environment", success=False)
            update_step_status(run_dir, "Validate Environment", "failed", error_msg)
            
            duration = time.time() - start_time
            log_run_end(logger, "Jitbit", False, duration)
            
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=error_msg, duration_seconds=duration
            )
        
        logger.info("Environment validation passed")
        logger.step_end("Validate Environment", success=True)
        update_step_status(run_dir, "Validate Environment", "success")
        
        # Step 2: Export Jitbit tickets
        result = step_jitbit_export_tickets(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jitbit", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results, 
                duration_seconds=duration
            )
        
        # Step 3: Export Jitbit knowledge base
        result = step_jitbit_export_kb(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jitbit", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results,
                duration_seconds=duration
            )
        
        # Step 4: Process with LLM
        result = step_jitbit_process_llm(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jitbit", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results,
                duration_seconds=duration
            )
        
        # Step 5: Generate DOCX from tickets
        result = step_jitbit_tickets_to_docx(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jitbit", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results,
                duration_seconds=duration
            )
        
        # Step 6: Generate DOCX from knowledge base
        result = step_jitbit_kb_to_docx(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jitbit", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results,
                duration_seconds=duration
            )
        
        # Success!
        duration = time.time() - start_time
        log_run_end(logger, "Jitbit", True, duration)
        
        return FlowResult(
            success=True, run_id=run_id, run_dir=run_dir,
            message="Jitbit workflow completed successfully", 
            step_results=step_results, duration_seconds=duration
        )
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"Unexpected error in Jitbit workflow: {e}"
        logger.error(error_msg)
        log_run_end(logger, "Jitbit", False, duration)
        
        return FlowResult(
            success=False, run_id=run_id, run_dir=run_dir,
            message=error_msg, step_results=step_results,
            duration_seconds=duration
        )
    
    finally:
        logger.close()


def run_jira_flow(params: Dict[str, Any], options: Dict[str, Any] = None,
                  run_id: str = None, run_dir: Path = None) -> FlowResult:
    """
    Run the complete Jira workflow.
    
    Steps:
    1. Validate environment
    2. Export tickets
    3. Process with LLM
    4. Deduplicate
    5. Generate DOCX for tickets
    """
    if options is None:
        options = {}
    
    # Use provided run_id/run_dir or create new ones
    if run_id is None:
        project = params.get("project", "")
        run_id = generate_run_id("jira", project)
    if run_dir is None:
        run_dir = create_run_directory(run_id)
    
    # Define workflow steps
    step_names = [
        "Validate Environment",
        "Export Jira Tickets",
        "Process Tickets with LLM", 
        "Deduplicate Tickets",
        "Generate DOCX from Tickets"
    ]
    
    # Initialize run tracking only if not already initialized
    status_file = run_dir / "status.json"
    if not status_file.exists():
        init_run_status(run_dir, step_names)
    save_run_params(run_dir, {**params, "flow": "jira", **options})
    
    # Create logger
    console_output = options.get("console_output", True)
    logger = create_run_logger(run_dir, console_output)
    
    start_time = time.time()
    step_results = []
    
    try:
        log_run_start(logger, "Jira", params)
        
        # Step 1: Validate environment
        logger.step_start("Validate Environment")
        update_step_status(run_dir, "Validate Environment", "running")
        
        env_valid, env_errors = validate_env_for_flow("jira")
        if not env_valid:
            error_msg = "Environment validation failed: " + "; ".join(env_errors)
            logger.error(error_msg)
            logger.step_end("Validate Environment", success=False)
            update_step_status(run_dir, "Validate Environment", "failed", error_msg)
            
            duration = time.time() - start_time
            log_run_end(logger, "Jira", False, duration)
            
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=error_msg, duration_seconds=duration
            )
        
        logger.info("Environment validation passed")
        logger.step_end("Validate Environment", success=True)
        update_step_status(run_dir, "Validate Environment", "success")
        
        # Step 2: Export Jira tickets
        result = step_jira_export_tickets(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jira", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results,
                duration_seconds=duration
            )
        
        # Step 3: Process with LLM
        result = step_jira_process_llm(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jira", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results,
                duration_seconds=duration
            )
        
        # Step 4: Deduplicate (recommended for Jira)
        skip_dedup = options.get("skip_deduplication", False)
        if not skip_dedup:
            result = step_jira_deduplicate(params, run_dir, logger, options)
            step_results.append(result)
            if not result.success:
                duration = time.time() - start_time
                log_run_end(logger, "Jira", False, duration)
                return FlowResult(
                    success=False, run_id=run_id, run_dir=run_dir,
                    message=result.message, step_results=step_results,
                    duration_seconds=duration
                )
        else:
            # Mark as skipped
            logger.info("Skipping deduplication as requested")
            update_step_status(run_dir, "Deduplicate Tickets", "skipped")
        
        # Step 5: Generate DOCX from tickets
        result = step_jira_tickets_to_docx(params, run_dir, logger, options)
        step_results.append(result)
        if not result.success:
            duration = time.time() - start_time
            log_run_end(logger, "Jira", False, duration)
            return FlowResult(
                success=False, run_id=run_id, run_dir=run_dir,
                message=result.message, step_results=step_results,
                duration_seconds=duration
            )
        
        # Success!
        duration = time.time() - start_time
        log_run_end(logger, "Jira", True, duration)
        
        return FlowResult(
            success=True, run_id=run_id, run_dir=run_dir,
            message="Jira workflow completed successfully",
            step_results=step_results, duration_seconds=duration
        )
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = f"Unexpected error in Jira workflow: {e}"
        logger.error(error_msg)
        log_run_end(logger, "Jira", False, duration)
        
        return FlowResult(
            success=False, run_id=run_id, run_dir=run_dir,
            message=error_msg, step_results=step_results,
            duration_seconds=duration
        )
    
    finally:
        logger.close()


def get_flow_steps(flow_name: str) -> List[str]:
    """Get the list of steps for a given flow."""
    if flow_name == "jitbit":
        return [
            "Validate Environment",
            "Export Jitbit Tickets", 
            "Export Jitbit Knowledge Base",
            "Process Tickets with LLM",
            "Generate DOCX from Tickets",
            "Generate DOCX from Knowledge Base"
        ]
    elif flow_name == "jira":
        return [
            "Validate Environment",
            "Export Jira Tickets",
            "Process Tickets with LLM", 
            "Deduplicate Tickets",
            "Generate DOCX from Tickets"
        ]
    else:
        return []
