"""
Main FastAPI application for the workflow web UI.
"""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from fastapi import FastAPI, Request, Form, HTTPException, Depends
    from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
    from fastapi.templating import Jinja2Templates
    from fastapi.staticfiles import StaticFiles
except ImportError:
    raise ImportError("FastAPI dependencies missing. Install with: pip install fastapi uvicorn jinja2 python-multipart")

from workflow_app.envcheck import get_env_status_summary
from workflow_app.flows import run_jitbit_flow, run_jira_flow
from workflow_app.config import JIRA_PROJECTS, DEFAULTS
from workflow_app.util import (
    list_runs, get_run_directory, load_run_status, 
    load_run_params, tail_log_file, get_run_artifacts
)

# Initialize FastAPI app
app = FastAPI(
    title="Workflow App",
    description="CLI and Web UI for Jitbit and Jira ticket processing workflows",
    version="1.0.0"
)

# Setup templates
templates = Jinja2Templates(directory="web/templates")

# Background job executor
executor = ThreadPoolExecutor(max_workers=2)

# Active runs storage
active_runs: Dict[str, any] = {}


async def run_workflow_background(flow_name: str, params: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    """Run workflow in background and return result."""
    try:
        if flow_name == "jitbit":
            result = run_jitbit_flow(params, options)
        elif flow_name == "jira":
            result = run_jira_flow(params, options)
        else:
            raise ValueError(f"Unknown flow: {flow_name}")
        
        return {
            "success": result.success,
            "run_id": result.run_id,
            "message": result.message,
            "duration": result.duration_seconds
        }
    except Exception as e:
        return {
            "success": False,
            "run_id": None,
            "message": f"Error: {e}",
            "duration": 0
        }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page with environment status and flow cards."""
    env_status = get_env_status_summary()
    recent_runs = list_runs()[:5]  # Show 5 most recent runs
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "env_status": env_status,
        "recent_runs": recent_runs
    })


@app.get("/jitbit", response_class=HTMLResponse)
async def jitbit_form(request: Request):
    """Jitbit workflow form."""
    env_status = get_env_status_summary()
    
    return templates.TemplateResponse("jitbit_form.html", {
        "request": request,
        "env_status": env_status,
        "defaults": DEFAULTS
    })


@app.post("/jitbit/start")
async def start_jitbit(
    request: Request,
    start_id: int = Form(...),
    llm_limit: str = Form(""),
    llm_max_calls: str = Form(""),
    llm_save_interval: int = Form(DEFAULTS["LLM_SAVE_INTERVAL"]),
    newest_first: bool = Form(False),
    skip_existing: bool = Form(True),
    overwrite: bool = Form(False),
    append: bool = Form(False)
):
    """Start Jitbit workflow."""
    params = {
        "start_id": start_id,
        "llm_save_interval": llm_save_interval,
        "newest_first": newest_first
    }
    
    # Convert empty strings to None for optional integer fields
    if llm_limit and llm_limit.strip().isdigit():
        params["llm_limit"] = int(llm_limit)
    if llm_max_calls and llm_max_calls.strip().isdigit():
        params["llm_max_calls"] = int(llm_max_calls)
    
    options = {
        "skip_existing": skip_existing,
        "overwrite": overwrite,
        "append": append,
        "console_output": False  # Don't output to console for web runs
    }
    
    # Start background task for better real-time experience
    try:
        from workflow_app.util import generate_run_id, create_run_directory, save_run_params, init_run_status
        from workflow_app.flows import get_flow_steps
        
        # Pre-create run directory and initialize status
        run_id = generate_run_id("jitbit")
        run_dir = create_run_directory(run_id)
        save_run_params(run_dir, {**params, "flow": "jitbit", **options})
        init_run_status(run_dir, get_flow_steps("jitbit"))
        
        # Start background execution with the pre-created run directory
        future = executor.submit(run_jitbit_flow, params, {**options, "console_output": False}, run_id, run_dir)
        active_runs[run_id] = future
        
        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {e}")


@app.get("/jira", response_class=HTMLResponse)
async def jira_form(request: Request):
    """Jira workflow form."""
    env_status = get_env_status_summary()
    
    return templates.TemplateResponse("jira_form.html", {
        "request": request,
        "env_status": env_status,
        "projects": JIRA_PROJECTS,
        "defaults": DEFAULTS
    })


@app.post("/jira/start")
async def start_jira(
    request: Request,
    project: str = Form(...),
    resolved_after: str = Form(...),
    resolved_before: Optional[str] = Form(None),
    jira_limit: str = Form(""),
    llm_limit: str = Form(""),
    llm_max_calls: str = Form(""),
    dedup_threshold: float = Form(DEFAULTS["DEDUP_THRESHOLD"]),
    dedup_threshold_low: float = Form(DEFAULTS["DEDUP_THRESHOLD_LOW"]),
    progress: bool = Form(False),
    skip_deduplication: bool = Form(False),
    skip_existing: bool = Form(True),
    overwrite: bool = Form(False),
    append: bool = Form(False)
):
    """Start Jira workflow."""
    if project not in JIRA_PROJECTS:
        raise HTTPException(status_code=400, detail=f"Invalid project: {project}")
    
    params = {
        "project": project,
        "resolved_after": resolved_after,
        "dedup_threshold": dedup_threshold,
        "dedup_threshold_low": dedup_threshold_low,
        "progress": progress
    }
    
    if resolved_before:
        params["resolved_before"] = resolved_before
    
    # Convert empty strings to None for optional integer fields
    if jira_limit and jira_limit.strip().isdigit():
        params["jira_limit"] = int(jira_limit)
    if llm_limit and llm_limit.strip().isdigit():
        params["llm_limit"] = int(llm_limit)
    if llm_max_calls and llm_max_calls.strip().isdigit():
        params["llm_max_calls"] = int(llm_max_calls)
    
    options = {
        "skip_deduplication": skip_deduplication,
        "skip_existing": skip_existing,
        "overwrite": overwrite,
        "append": append,
        "console_output": False
    }
    
    # Start background task for better real-time experience
    try:
        from workflow_app.util import generate_run_id, create_run_directory, save_run_params, init_run_status
        from workflow_app.flows import get_flow_steps
        
        # Pre-create run directory and initialize status
        run_id = generate_run_id("jira", project)
        run_dir = create_run_directory(run_id)
        save_run_params(run_dir, {**params, "flow": "jira", **options})
        init_run_status(run_dir, get_flow_steps("jira"))
        
        # Start background execution with the pre-created run directory
        future = executor.submit(run_jira_flow, params, {**options, "console_output": False}, run_id, run_dir)
        active_runs[run_id] = future
        
        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {e}")


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_dashboard(request: Request, run_id: str):
    """Run dashboard showing status and progress."""
    run_dir = get_run_directory(run_id)
    
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    
    status = load_run_status(run_dir)
    params = load_run_params(run_dir)
    artifacts = get_run_artifacts(run_dir)
    
    # Check if run is active
    is_active = run_id in active_runs
    if is_active:
        task = active_runs[run_id]
        if task.done():
            # Clean up completed task
            del active_runs[run_id]
            is_active = False
    
    return templates.TemplateResponse("run_dashboard.html", {
        "request": request,
        "run_id": run_id,
        "status": status,
        "params": params,
        "artifacts": artifacts,
        "is_active": is_active
    })


@app.get("/runs/{run_id}/log")
async def get_run_log(run_id: str, offset: int = 0):
    """Get incremental log content for a run."""
    run_dir = get_run_directory(run_id)
    
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    
    log_data = tail_log_file(run_dir, offset)
    return JSONResponse(content=log_data)


@app.get("/runs/{run_id}/status")
async def get_run_status(run_id: str):
    """Get current run status."""
    run_dir = get_run_directory(run_id)
    
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    
    status = load_run_status(run_dir)
    
    # Check if run is active
    is_active = run_id in active_runs
    if is_active:
        future = active_runs[run_id]
        if future.done():
            del active_runs[run_id]
            is_active = False
    
    return JSONResponse(content={
        "status": status,
        "is_active": is_active
    })


@app.get("/runs/{run_id}/steps")
async def get_run_steps(request: Request, run_id: str):
    """Get current run steps as HTML fragment."""
    run_dir = get_run_directory(run_id)
    
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    
    status = load_run_status(run_dir)
    
    if not status or not status.get("steps"):
        return HTMLResponse("")
    
    # Render just the steps HTML fragment
    steps_html = ""
    for i, step in enumerate(status["steps"]):
        is_last = i == len(status["steps"]) - 1
        
        # Determine icon based on status
        if step["status"] == "success":
            icon = '''<span class="h-8 w-8 rounded-full bg-green-500 flex items-center justify-center ring-8 ring-white">
                        <svg class="h-5 w-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
                        </svg>
                    </span>'''
        elif step["status"] == "running":
            icon = '''<span class="h-8 w-8 rounded-full bg-blue-500 flex items-center justify-center ring-8 ring-white">
                        <svg class="h-5 w-5 text-white animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 818-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    </span>'''
        elif step["status"] == "skipped":
            icon = '''<span class="h-8 w-8 rounded-full bg-yellow-500 flex items-center justify-center ring-8 ring-white">
                        <svg class="h-5 w-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.414-1.414L10 9.586V6z" clip-rule="evenodd"/>
                        </svg>
                    </span>'''
        elif step["status"] == "failed":
            icon = '''<span class="h-8 w-8 rounded-full bg-red-500 flex items-center justify-center ring-8 ring-white">
                        <svg class="h-5 w-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                        </svg>
                    </span>'''
        else:
            icon = '''<span class="h-8 w-8 rounded-full bg-gray-400 flex items-center justify-center ring-8 ring-white">
                        <span class="h-2 w-2 bg-gray-300 rounded-full"></span>
                    </span>'''
        
        # Determine line color
        if step["status"] in ["success", "skipped"]:
            line_color = "bg-green-200"
        elif step["status"] == "failed":
            line_color = "bg-red-200"
        elif step["status"] == "running":
            line_color = "bg-blue-200"
        else:
            line_color = "bg-gray-200"
            
        line_html = "" if is_last else f'<span class="absolute top-4 left-4 -ml-px h-full w-0.5 {line_color}" aria-hidden="true"></span>'
        
        duration_html = ""
        if step.get("duration_seconds"):
            duration_html = f'<span>{step["duration_seconds"]:.1f}s</span>'
        
        start_time_html = ""
        if step.get("start_time"):
            start_time_html = f'<div class="text-xs">{step["start_time"][:19].replace("T", " ")}</div>'
        
        error_html = ""
        if step.get("error"):
            error_html = f'<p class="text-sm text-red-600 mt-1">{step["error"]}</p>'
        
        steps_html += f'''
        <li class="workflow-step">
            <div class="relative pb-8">
                {line_html}
                <div class="relative flex space-x-3">
                    <div class="step-icon">
                        {icon}
                    </div>
                    <div class="min-w-0 flex-1 pt-1.5 flex justify-between space-x-4">
                        <div>
                            <p class="text-sm text-gray-900 font-medium">{step["name"]}</p>
                            {error_html}
                        </div>
                        <div class="text-right text-sm whitespace-nowrap text-gray-500">
                            {duration_html}
                            {start_time_html}
                        </div>
                    </div>
                </div>
            </div>
        </li>
        '''
    
    return HTMLResponse(content=steps_html)


@app.get("/runs", response_class=HTMLResponse)
async def runs_list(request: Request):
    """List all runs."""
    runs = list_runs()
    
    return templates.TemplateResponse("runs_list.html", {
        "request": request,
        "runs": runs
    })


@app.post("/runs/delete-all")
async def delete_all_runs(request: Request):
    """Delete all workflow runs."""
    try:
        from workflow_app.util import clean_old_runs
        from workflow_app.config import get_repo_root
        import shutil
        
        # Get the runs directory and remove it entirely
        repo_root = get_repo_root()
        runs_dir = repo_root / "runs"
        
        deleted_count = 0
        if runs_dir.exists():
            # Count existing runs
            deleted_count = len([d for d in runs_dir.iterdir() if d.is_dir()])
            # Remove the entire runs directory
            shutil.rmtree(runs_dir)
        
        # Clear active runs tracking
        active_runs.clear()
        
        return JSONResponse(content={
            "success": True,
            "message": f"Deleted {deleted_count} workflow runs",
            "deleted_count": deleted_count
        })
        
    except Exception as e:
        return JSONResponse(content={
            "success": False,
            "message": f"Error deleting runs: {e}"
        }, status_code=500)


@app.get("/env-status")
async def env_status_api():
    """API endpoint for environment status."""
    return JSONResponse(content=get_env_status_summary())


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
