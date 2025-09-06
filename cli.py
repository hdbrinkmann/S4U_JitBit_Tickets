"""
CLI interface for the workflow app using Typer.
"""

import sys
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    print("Error: typer is required. Please install it with: pip install typer")
    sys.exit(1)

from workflow_app.envcheck import print_env_check
from workflow_app.flows import run_jitbit_flow, run_jira_flow
from workflow_app.config import JIRA_PROJECTS, DEFAULTS

app = typer.Typer(help="Workflow App - CLI and Web UI for Jitbit and Jira ticket processing")


@app.command("env-check")
def env_check():
    """Check environment variables and configuration."""
    success = print_env_check()
    if not success:
        raise typer.Exit(1)


@app.command("run-jitbit")
def run_jitbit(
    start_id: int = typer.Option(..., "--start-id", help="Starting ticket ID for Jitbit export"),
    llm_limit: Optional[int] = typer.Option(None, "--llm-limit", help="Limit number of tickets for LLM processing"),
    llm_max_calls: Optional[int] = typer.Option(None, "--llm-max-calls", help="Maximum LLM API calls"),
    llm_save_interval: int = typer.Option(DEFAULTS["LLM_SAVE_INTERVAL"], "--llm-save-interval", help="Save interval for LLM processing"),
    newest_first: bool = typer.Option(False, "--newest-first", help="Process newest tickets first"),
    skip_existing: bool = typer.Option(DEFAULTS["SKIP_EXISTING"], "--skip-existing/--no-skip-existing", help="Skip steps with existing outputs"),
    overwrite: bool = typer.Option(DEFAULTS["OVERWRITE"], "--overwrite/--no-overwrite", help="Overwrite existing outputs"),
    append: bool = typer.Option(DEFAULTS["APPEND"], "--append/--no-append", help="Append to existing outputs")
):
    """Run the Jitbit workflow."""
    typer.echo(f"Starting Jitbit workflow with start ID: {start_id}")
    
    params = {
        "start_id": start_id,
        "llm_limit": llm_limit,
        "llm_max_calls": llm_max_calls,
        "llm_save_interval": llm_save_interval,
        "newest_first": newest_first
    }
    
    options = {
        "skip_existing": skip_existing,
        "overwrite": overwrite,
        "append": append,
        "console_output": True
    }
    
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}
    
    try:
        result = run_jitbit_flow(params, options)
        
        if result.success:
            typer.echo(f"\n✅ Jitbit workflow completed successfully!")
            typer.echo(f"Run ID: {result.run_id}")
            typer.echo(f"Duration: {result.duration_seconds:.1f} seconds")
            typer.echo(f"Run directory: {result.run_dir}")
        else:
            typer.echo(f"\n❌ Jitbit workflow failed: {result.message}", err=True)
            typer.echo(f"Run ID: {result.run_id}")
            typer.echo(f"Run directory: {result.run_dir}")
            raise typer.Exit(1)
            
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command("run-jira")
def run_jira(
    project: str = typer.Option("SUP", "--project", help=f"Jira project ({'/'.join(JIRA_PROJECTS)})"),
    resolved_after: str = typer.Option(..., "--resolved-after", help="Resolved after date (YYYY-MM-DD or YYYYMMDD)"),
    resolved_before: Optional[str] = typer.Option(None, "--resolved-before", help="Resolved before date (YYYY-MM-DD or YYYYMMDD)"),
    jira_limit: Optional[int] = typer.Option(None, "--jira-limit", help="Limit number of tickets to export"),
    llm_limit: Optional[int] = typer.Option(None, "--llm-limit", help="Limit number of tickets for LLM processing"),
    llm_max_calls: Optional[int] = typer.Option(None, "--llm-max-calls", help="Maximum LLM API calls"),
    dedup_threshold: float = typer.Option(DEFAULTS["DEDUP_THRESHOLD"], "--dedup-threshold", help="Deduplication similarity threshold"),
    dedup_threshold_low: float = typer.Option(DEFAULTS["DEDUP_THRESHOLD_LOW"], "--dedup-threshold-low", help="Low deduplication threshold"),
    progress: bool = typer.Option(False, "--progress/--no-progress", help="Show detailed progress during Jira export"),
    skip_deduplication: bool = typer.Option(False, "--skip-dedup/--no-skip-dedup", help="Skip deduplication step"),
    skip_existing: bool = typer.Option(DEFAULTS["SKIP_EXISTING"], "--skip-existing/--no-skip-existing", help="Skip steps with existing outputs"),
    overwrite: bool = typer.Option(DEFAULTS["OVERWRITE"], "--overwrite/--no-overwrite", help="Overwrite existing outputs"),
    append: bool = typer.Option(DEFAULTS["APPEND"], "--append/--no-append", help="Append to existing outputs")
):
    """Run the Jira workflow."""
    # Validate project
    if project not in JIRA_PROJECTS:
        typer.echo(f"❌ Invalid project: {project}. Must be one of: {', '.join(JIRA_PROJECTS)}", err=True)
        raise typer.Exit(1)
    
    typer.echo(f"Starting Jira workflow for project {project}, resolved after: {resolved_after}")
    
    params = {
        "project": project,
        "resolved_after": resolved_after,
        "resolved_before": resolved_before,
        "jira_limit": jira_limit,
        "llm_limit": llm_limit,
        "llm_max_calls": llm_max_calls,
        "dedup_threshold": dedup_threshold,
        "dedup_threshold_low": dedup_threshold_low,
        "progress": progress
    }
    
    options = {
        "skip_deduplication": skip_deduplication,
        "skip_existing": skip_existing,
        "overwrite": overwrite,
        "append": append,
        "console_output": True
    }
    
    # Remove None values  
    params = {k: v for k, v in params.items() if v is not None}
    
    try:
        result = run_jira_flow(params, options)
        
        if result.success:
            typer.echo(f"\n✅ Jira workflow completed successfully!")
            typer.echo(f"Run ID: {result.run_id}")
            typer.echo(f"Duration: {result.duration_seconds:.1f} seconds")
            typer.echo(f"Run directory: {result.run_dir}")
        else:
            typer.echo(f"\n❌ Jira workflow failed: {result.message}", err=True)
            typer.echo(f"Run ID: {result.run_id}")
            typer.echo(f"Run directory: {result.run_dir}")
            raise typer.Exit(1)
            
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command("web")
def web(
    host: str = typer.Option(None, "--host", help="Host to bind to (default from env or 127.0.0.1)"),
    port: int = typer.Option(None, "--port", help="Port to bind to (default from env or 8787)"),
    auto_port: bool = typer.Option(False, "--auto-port", help="Try fallback ports if default is busy")
):
    """Start the web UI server."""
    try:
        # Import here to avoid early dependency issues
        import uvicorn
        from workflow_app.config import get_host, get_port, should_auto_port, DEFAULT_PORT_RANGE
        
        # Determine host and port
        bind_host = host or get_host()
        bind_port = port or get_port()
        
        # Auto port fallback if requested
        if auto_port or should_auto_port():
            if bind_port in DEFAULT_PORT_RANGE:
                # Try ports in the configured range
                for try_port in DEFAULT_PORT_RANGE:
                    if try_port >= bind_port:
                        try:
                            import socket
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.bind((bind_host, try_port))
                                bind_port = try_port
                                break
                        except OSError:
                            continue
        
        typer.echo(f"Starting web server on http://{bind_host}:{bind_port}")
        typer.echo("Press Ctrl+C to stop the server")
        
        # Start the server
        uvicorn.run(
            "web.main:app",
            host=bind_host,
            port=bind_port,
            reload=False,
            access_log=True
        )
        
    except ImportError as e:
        typer.echo(f"❌ Missing dependencies for web server: {e}", err=True)
        typer.echo("Install with: pip install fastapi uvicorn jinja2 python-multipart")
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Error starting web server: {e}", err=True)
        raise typer.Exit(1)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
