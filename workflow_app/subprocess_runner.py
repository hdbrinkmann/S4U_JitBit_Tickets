"""
Improved subprocess execution with real-time output capture.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import List, Callable

from .config import get_repo_root


class RealTimeSubprocess:
    """Execute subprocess with real-time output streaming."""
    
    def __init__(self, cmd: List[str], cwd: Path, output_callback: Callable[[str], None]):
        self.cmd = cmd
        self.cwd = cwd
        self.output_callback = output_callback
        self.return_code = None
        self.process = None
        
    def run(self, timeout: int = 3600) -> int:
        """Run the subprocess with real-time output capture."""
        try:
            # Set environment for unbuffered output
            env = dict(os.environ)
            env['PYTHONUNBUFFERED'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'
            
            # Start process
            self.process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                env=env,
                bufsize=0  # Completely unbuffered
            )
            
            # Read output in real time
            while True:
                line = self.process.stdout.readline()
                if line:
                    # Call callback with each line immediately
                    self.output_callback(line.rstrip())
                elif self.process.poll() is not None:
                    # Process finished
                    break
                    
            # Get final return code
            self.return_code = self.process.returncode
            return self.return_code
            
        except Exception as e:
            self.output_callback(f"ERROR: {e}")
            return 1


def execute_subprocess_realtime(cmd: List[str], logger, timeout: int = 3600) -> int:
    """Execute subprocess with real-time logging."""
    
    def log_output(line: str):
        """Callback to log each line of output immediately."""
        if line.strip():
            logger.subprocess_output(line)
    
    # Log the command being executed
    logger.command(" ".join(cmd))
    
    # Execute with real-time capture
    runner = RealTimeSubprocess(cmd, get_repo_root(), log_output)
    return_code = runner.run(timeout)
    
    return return_code
