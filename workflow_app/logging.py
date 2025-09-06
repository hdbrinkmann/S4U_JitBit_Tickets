"""
Unified logging for per-run logging with redaction of sensitive information.
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import TextIO, Optional, List
from .util import get_log_file_path


class RunLogger:
    """Logger that writes to both console and run-specific log file."""
    
    # Patterns to redact sensitive information
    SENSITIVE_PATTERNS = [
        (re.compile(r'Authorization:\s*Bearer\s+[^\s]+', re.IGNORECASE), 'Authorization: Bearer [REDACTED]'),
        (re.compile(r'Authorization:\s*Basic\s+[^\s]+', re.IGNORECASE), 'Authorization: Basic [REDACTED]'),
        (re.compile(r'token[=:]\s*[^\s&]+', re.IGNORECASE), 'token=[REDACTED]'),
        (re.compile(r'key[=:]\s*[^\s&]+', re.IGNORECASE), 'key=[REDACTED]'),
        (re.compile(r'password[=:]\s*[^\s&]+', re.IGNORECASE), 'password=[REDACTED]'),
        (re.compile(r'secret[=:]\s*[^\s&]+', re.IGNORECASE), 'secret=[REDACTED]'),
    ]
    
    def __init__(self, run_dir: Path, console_output: bool = True):
        """Initialize logger with run directory and optional console output."""
        self.run_dir = run_dir
        self.console_output = console_output
        self.log_file_path = get_log_file_path(run_dir)
        self._log_file: Optional[TextIO] = None
        
        # Ensure log file exists and is writable
        self._ensure_log_file()
        
    def _ensure_log_file(self):
        """Ensure the log file exists and is open for writing."""
        try:
            if self._log_file is None:
                self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
                self._log_file = open(self.log_file_path, 'a', encoding='utf-8', buffering=1)
        except Exception as e:
            if self.console_output:
                print(f"Warning: Could not open log file {self.log_file_path}: {e}", file=sys.stderr)
    
    def _redact_sensitive_info(self, text: str) -> str:
        """Remove sensitive information from log text."""
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text
    
    def _format_message(self, level: str, message: str) -> str:
        """Format log message with timestamp and level."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{timestamp}] [{level}] {message}"
    
    def _write_log(self, formatted_message: str):
        """Write message to log file and optionally console."""
        # Redact sensitive information
        safe_message = self._redact_sensitive_info(formatted_message)
        
        # Write to console if enabled
        if self.console_output:
            print(safe_message, flush=True)
        
        # Write to log file
        try:
            if self._log_file:
                self._log_file.write(safe_message + '\n')
                self._log_file.flush()
        except Exception as e:
            if self.console_output:
                print(f"Warning: Could not write to log file: {e}", file=sys.stderr)
    
    def info(self, message: str):
        """Log an info message."""
        formatted = self._format_message("INFO", message)
        self._write_log(formatted)
    
    def warning(self, message: str):
        """Log a warning message."""
        formatted = self._format_message("WARN", message)
        self._write_log(formatted)
    
    def error(self, message: str):
        """Log an error message."""
        formatted = self._format_message("ERROR", message)
        self._write_log(formatted)
    
    def step_start(self, step_name: str):
        """Log the start of a workflow step."""
        self.info(f"=== STEP START: {step_name} ===")
    
    def step_end(self, step_name: str, success: bool = True):
        """Log the end of a workflow step."""
        status = "SUCCESS" if success else "FAILED"
        self.info(f"=== STEP END: {step_name} - {status} ===")
    
    def command(self, cmd: str):
        """Log a command that is about to be executed."""
        # Redact sensitive info from command
        safe_cmd = self._redact_sensitive_info(cmd)
        self.info(f"Executing: {safe_cmd}")
    
    def subprocess_output(self, line: str):
        """Log subprocess output line."""
        # Don't add extra formatting, just timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] {line.rstrip()}"
        self._write_log(formatted)
    
    def close(self):
        """Close the log file."""
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class StreamCapture:
    """Capture subprocess output and forward to logger."""
    
    def __init__(self, logger: RunLogger, stream_name: str = "OUTPUT"):
        self.logger = logger
        self.stream_name = stream_name
        self.buffer = ""
    
    def write(self, text: str):
        """Write text to the capture buffer and log complete lines."""
        self.buffer += text
        
        # Process complete lines
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            if line:  # Don't log empty lines
                self.logger.subprocess_output(f"[{self.stream_name}] {line}")
    
    def flush(self):
        """Flush any remaining content in buffer."""
        if self.buffer.strip():
            self.logger.subprocess_output(f"[{self.stream_name}] {self.buffer}")
            self.buffer = ""


def create_run_logger(run_dir: Path, console_output: bool = True) -> RunLogger:
    """Create a logger for a specific run."""
    return RunLogger(run_dir, console_output)


def log_run_start(logger: RunLogger, flow_name: str, params: dict):
    """Log the start of a workflow run."""
    logger.info(f"Starting {flow_name} workflow")
    logger.info(f"Run directory: {logger.run_dir}")
    
    # Log non-sensitive parameters
    safe_params = {k: v for k, v in params.items() 
                   if not any(sensitive in k.lower() for sensitive in ['token', 'key', 'password', 'secret'])}
    
    if safe_params:
        logger.info(f"Parameters: {safe_params}")


def log_run_end(logger: RunLogger, flow_name: str, success: bool, duration_seconds: float):
    """Log the end of a workflow run."""
    status = "SUCCESS" if success else "FAILED"
    logger.info(f"Workflow {flow_name} completed with status: {status}")
    logger.info(f"Total duration: {duration_seconds:.1f} seconds")
