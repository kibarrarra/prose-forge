"""
subprocess_helpers.py - Common subprocess execution utilities

Provides standardized subprocess execution with proper error handling,
UTF-8 encoding, and environment setup.
"""

import os
import subprocess
import pathlib
from typing import Dict, List, Optional
from .logging_helper import get_logger

log = get_logger()


def setup_subprocess_env(
    writer_spec: Optional[str] = None,
    editor_spec: Optional[str] = None,
    model: Optional[str] = None,
    additional_env: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Set up environment variables for subprocess calls.
    
    Args:
        writer_spec: Path to writer prompt template file
        editor_spec: Editor prompt template content (for now)
        model: Model override
        additional_env: Additional environment variables to merge
        
    Returns:
        Environment dictionary with UTF-8 encoding and proper paths
    """
    env = os.environ.copy()
    
    # Ensure project root is on PYTHONPATH
    from .paths import ROOT
    python_path = env.get("PYTHONPATH", "")
    project_root_str = str(ROOT.resolve())
    if project_root_str not in python_path.split(os.pathsep):
        env["PYTHONPATH"] = f"{project_root_str}{os.pathsep}{python_path}"
    
    # Add prompts and model overrides
    if writer_spec:
        env["WRITER_PROMPT_TEMPLATE"] = writer_spec
    if editor_spec:
        env["EDITOR_PROMPT_TEMPLATE"] = editor_spec
    if model:
        env["WRITER_MODEL"] = model
        env["EDITOR_MODEL"] = model
        
    # Ensure UTF-8 encoding
    env["PYTHONIOENCODING"] = "utf-8"
    
    # Merge additional environment variables
    if additional_env:
        env.update(additional_env)
    
    return env


def run_subprocess_safely(
    cmd: List,
    env: Dict[str, str],
    cwd: Optional[pathlib.Path] = None,
    description: str = "subprocess",
    capture_output: bool = True,
    check: bool = True
) -> subprocess.CompletedProcess:
    """Run a subprocess with proper error handling and logging.
    
    Args:
        cmd: Command and arguments
        env: Environment variables
        cwd: Working directory (defaults to project root)
        description: Description for logging
        capture_output: Whether to capture stdout/stderr
        check: Whether to raise on non-zero exit codes
        
    Returns:
        CompletedProcess result
        
    Raises:
        subprocess.CalledProcessError: If subprocess fails and check=True
    """
    if cwd is None:
        from .paths import ROOT
        cwd = ROOT
        
    log.info(f"Running {description}: {' '.join(str(arg) for arg in cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            check=check,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )
        
        # Log stdout if present and captured
        if capture_output and result.stdout:
            for line in result.stdout.splitlines():
                log.info(f"{description}: {line}")
                
        return result
        
    except subprocess.CalledProcessError as e:
        log.error(f"{description} failed with exit code {e.returncode}")
        if e.stderr:
            log.error(f"Error output: {e.stderr}")
        raise
    except OSError as e:
        log.error(f"{description} failed with OS error: {e}")
        log.error(f"Command: {' '.join(str(arg) for arg in cmd)}")
        log.error(f"Working directory: {cwd}")
        # Check if any paths in the command have issues
        for i, arg in enumerate(cmd):
            arg_str = str(arg)
            if ('\\' in arg_str or '/' in arg_str) and len(arg_str) > 10:
                try:
                    path_obj = pathlib.Path(arg_str)
                    if not path_obj.parent.exists():
                        log.error(f"Argument {i} contains non-existent parent directory: {arg_str}")
                    elif len(arg_str) > 260:
                        log.error(f"Argument {i} path may be too long ({len(arg_str)} chars): {arg_str}")
                except Exception:
                    log.error(f"Argument {i} contains invalid path: {arg_str}")
        raise


def run_python_script(
    script_path: pathlib.Path,
    args: List[str],
    env: Optional[Dict[str, str]] = None,
    description: Optional[str] = None,
    **kwargs
) -> subprocess.CompletedProcess:
    """Convenience function to run a Python script.
    
    Args:
        script_path: Path to the Python script
        args: Arguments to pass to the script
        env: Environment variables (will set up defaults if None)
        description: Description for logging (defaults to script name)
        **kwargs: Additional arguments for run_subprocess_safely
        
    Returns:
        CompletedProcess result
    """
    import sys
    
    if env is None:
        env = setup_subprocess_env()
        
    if description is None:
        description = f"script {script_path.name}"
    
    cmd = [sys.executable, str(script_path)] + args
    
    return run_subprocess_safely(cmd, env, description=description, **kwargs) 