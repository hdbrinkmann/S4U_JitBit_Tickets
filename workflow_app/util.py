"""
Utility functions for run directory creation, artifact linking, and file validation.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from .config import (
    RUN_DIR_PREFIX, RUN_STATUS_FILE, RUN_PARAMS_FILE, 
    RUN_LOG_FILE, RUN_ARTIFACTS_DIR, get_repo_root, ensure_dir
)


def generate_run_id(flow_name: str, project: str = None) -> str:
    """Generate a unique run ID with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if project:
        return f"{timestamp}-{flow_name}-{project}"
    return f"{timestamp}-{flow_name}"


def create_run_directory(run_id: str) -> Path:
    """Create and return the run directory path."""
    repo_root = get_repo_root()
    run_dir = repo_root / RUN_DIR_PREFIX / run_id
    ensure_dir(run_dir)
    ensure_dir(run_dir / RUN_ARTIFACTS_DIR)
    return run_dir


def get_run_directory(run_id: str) -> Path:
    """Get the run directory path (may not exist)."""
    repo_root = get_repo_root()
    return repo_root / RUN_DIR_PREFIX / run_id


def list_runs() -> List[Dict[str, Any]]:
    """List all available runs with their basic info."""
    repo_root = get_repo_root()
    runs_dir = repo_root / RUN_DIR_PREFIX
    
    if not runs_dir.exists():
        return []
    
    runs = []
    for run_dir in runs_dir.iterdir():
        if run_dir.is_dir():
            status_file = run_dir / RUN_STATUS_FILE
            params_file = run_dir / RUN_PARAMS_FILE
            
            run_info = {
                "id": run_dir.name,
                "path": str(run_dir),
                "created": datetime.fromtimestamp(run_dir.stat().st_mtime).isoformat()
            }
            
            # Add status info if available
            if status_file.exists():
                try:
                    with open(status_file, 'r') as f:
                        status = json.load(f)
                        run_info["status"] = status.get("current_status", "unknown")
                        run_info["steps"] = len(status.get("steps", []))
                except Exception:
                    run_info["status"] = "error"
            else:
                run_info["status"] = "no_status"
            
            # Add params info if available  
            if params_file.exists():
                try:
                    with open(params_file, 'r') as f:
                        params = json.load(f)
                        run_info["flow"] = params.get("flow", "unknown")
                        run_info["project"] = params.get("project")
                except Exception:
                    pass
            
            runs.append(run_info)
    
    # Sort by creation time (newest first)
    runs.sort(key=lambda x: x["created"], reverse=True)
    return runs


def save_run_params(run_dir: Path, params: Dict[str, Any]) -> None:
    """Save run parameters to JSON file."""
    params_file = run_dir / RUN_PARAMS_FILE
    # Remove sensitive information from saved params
    safe_params = {k: v for k, v in params.items() 
                   if not any(sensitive in k.lower() for sensitive in ['token', 'key', 'password', 'secret'])}
    
    with open(params_file, 'w') as f:
        json.dump(safe_params, f, indent=2, default=str)


def load_run_params(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Load run parameters from JSON file."""
    params_file = run_dir / RUN_PARAMS_FILE
    if not params_file.exists():
        return None
    
    try:
        with open(params_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def init_run_status(run_dir: Path, steps: List[str]) -> None:
    """Initialize run status with step definitions."""
    status = {
        "run_id": run_dir.name,
        "created": datetime.now().isoformat(),
        "current_status": "initialized",
        "steps": []
    }
    
    for i, step_name in enumerate(steps):
        status["steps"].append({
            "name": step_name,
            "status": "pending",
            "start_time": None,
            "end_time": None,
            "duration_seconds": None,
            "error": None
        })
    
    save_run_status(run_dir, status)


def save_run_status(run_dir: Path, status: Dict[str, Any]) -> None:
    """Save run status to JSON file."""
    status_file = run_dir / RUN_STATUS_FILE
    status["updated"] = datetime.now().isoformat()
    
    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2, default=str)


def load_run_status(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Load run status from JSON file."""
    status_file = run_dir / RUN_STATUS_FILE
    if not status_file.exists():
        return None
    
    try:
        with open(status_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def update_step_status(run_dir: Path, step_name: str, status: str, error: str = None) -> None:
    """Update the status of a specific step."""
    try:
        run_status = load_run_status(run_dir)
        if not run_status:
            print(f"DEBUG: Could not load run status for {run_dir}")
            return
        
        current_time = datetime.now().isoformat()
        step_found = False
        
        # Find and update the step
        for step in run_status["steps"]:
            if step["name"] == step_name:
                step_found = True
                print(f"DEBUG: Updating step '{step_name}' to status '{status}'")
                
                if status == "running" and not step["start_time"]:
                    step["start_time"] = current_time
                elif status in ["success", "failed"]:
                    if not step["end_time"]:
                        step["end_time"] = current_time
                        # Calculate duration if we have start time
                        if step["start_time"]:
                            try:
                                start = datetime.fromisoformat(step["start_time"])
                                end = datetime.fromisoformat(step["end_time"])
                                step["duration_seconds"] = (end - start).total_seconds()
                            except Exception:
                                pass
                
                step["status"] = status
                if error:
                    step["error"] = error
                break
        
        if not step_found:
            print(f"DEBUG: Step '{step_name}' not found in steps: {[s['name'] for s in run_status['steps']]}")
        
        # Update overall status
        if status == "running":
            run_status["current_status"] = "running"
        elif status == "failed":
            run_status["current_status"] = "failed"
        elif status == "success":
            # Check if all steps are complete
            if all(step["status"] in ["success", "skipped"] for step in run_status["steps"]):
                run_status["current_status"] = "completed"
        
        save_run_status(run_dir, run_status)
        print(f"DEBUG: Status file saved for '{step_name}' -> '{status}'")
        
    except Exception as e:
        print(f"DEBUG: Error updating step status: {e}")


def get_log_file_path(run_dir: Path) -> Path:
    """Get the path to the run log file."""
    return run_dir / RUN_LOG_FILE


def tail_log_file(run_dir: Path, offset: int = 0, max_lines: int = 100) -> Dict[str, Any]:
    """Tail the log file and return new content."""
    log_file = get_log_file_path(run_dir)
    
    if not log_file.exists():
        return {"content": "", "new_offset": offset, "exists": False}
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # Seek to the offset position
            f.seek(offset)
            content = f.read()
            new_offset = f.tell()
        
        # Limit the number of lines returned
        lines = content.split('\n')
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            content = '\n'.join(lines)
        
        return {
            "content": content,
            "new_offset": new_offset,
            "exists": True,
            "size": log_file.stat().st_size
        }
    except Exception as e:
        return {"content": f"Error reading log: {e}", "new_offset": offset, "exists": True}


def validate_json_file(file_path: Path) -> bool:
    """Check if a JSON file exists and is valid."""
    if not file_path.exists():
        return False
    
    try:
        with open(file_path, 'r') as f:
            json.load(f)
        return True
    except Exception:
        return False


def file_exists_and_not_empty(file_path: Path) -> bool:
    """Check if file exists and is not empty."""
    if not file_path.exists():
        return False
    return file_path.stat().st_size > 0


def should_skip_step(run_dir: Path, output_files: List[str], skip_existing: bool) -> bool:
    """Determine if a step should be skipped based on existing outputs."""
    if not skip_existing:
        return False
    
    repo_root = get_repo_root()
    
    # Check if all output files exist and are valid
    for file_path in output_files:
        full_path = repo_root / file_path
        
        if file_path.endswith('.json'):
            if not validate_json_file(full_path):
                return False
        else:
            if not file_exists_and_not_empty(full_path):
                return False
    
    return True


def copy_artifact_to_run(run_dir: Path, source_file: str, artifact_name: str = None) -> None:
    """Copy an artifact file or directory to the run's artifacts directory."""
    repo_root = get_repo_root()
    source_path = repo_root / source_file
    
    if not source_path.exists():
        return
    
    artifacts_dir = run_dir / RUN_ARTIFACTS_DIR
    ensure_dir(artifacts_dir)
    
    if artifact_name is None:
        artifact_name = source_path.name
    
    dest_path = artifacts_dir / artifact_name
    
    # Handle both files and directories
    if source_path.is_dir():
        if dest_path.exists():
            shutil.rmtree(dest_path)
        shutil.copytree(source_path, dest_path)
    else:
        shutil.copy2(source_path, dest_path)


def get_run_artifacts(run_dir: Path) -> List[Dict[str, Any]]:
    """Get list of artifacts (files and directories) in the run directory."""
    artifacts_dir = run_dir / RUN_ARTIFACTS_DIR
    
    if not artifacts_dir.exists():
        return []
    
    artifacts: List[Dict[str, Any]] = []
    for artifact in artifacts_dir.iterdir():
        try:
            if artifact.is_file():
                stat = artifact.stat()
                artifacts.append({
                    "name": artifact.name,
                    "path": str(artifact),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "file"
                })
            elif artifact.is_dir():
                # Aggregate size and latest modified time for directories
                total_size = 0
                latest_mtime = artifact.stat().st_mtime
                items = 0
                for p in artifact.rglob("*"):
                    try:
                        st = p.stat()
                        if p.is_file():
                            total_size += st.st_size
                        latest_mtime = max(latest_mtime, st.st_mtime)
                        items += 1
                    except Exception:
                        # Skip unreadable entries
                        continue
                artifacts.append({
                    "name": artifact.name,
                    "path": str(artifact),
                    "size": total_size,
                    "modified": datetime.fromtimestamp(latest_mtime).isoformat(),
                    "type": "dir",
                    "items": items
                })
        except Exception:
            # Skip items we cannot stat/read
            continue
    
    # Sort: directories first, then files, by name
    artifacts.sort(key=lambda x: (x.get("type") != "dir", x.get("name", "").lower()))
    return artifacts


def clean_old_runs(keep_count: int = 50) -> int:
    """Clean up old run directories, keeping only the most recent ones."""
    runs = list_runs()
    
    if len(runs) <= keep_count:
        return 0
    
    # Remove oldest runs
    runs_to_remove = runs[keep_count:]
    removed_count = 0
    
    for run in runs_to_remove:
        try:
            run_path = Path(run["path"])
            if run_path.exists():
                shutil.rmtree(run_path)
                removed_count += 1
        except Exception:
            pass  # Ignore errors when cleaning up
    
    return removed_count
