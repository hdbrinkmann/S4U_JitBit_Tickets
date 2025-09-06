"""
Environment validation functions for checking required tokens and URLs.
"""

import os
import re
from typing import Dict, List, Tuple
from .config import ENV_VARS, get_env_var


class EnvCheckResult:
    """Result of an environment variable check."""
    
    def __init__(self, key: str, is_present: bool, is_valid: bool = True, message: str = ""):
        self.key = key
        self.is_present = is_present
        self.is_valid = is_valid
        self.message = message
        self.is_ok = is_present and is_valid
    
    def __repr__(self):
        status = "✓" if self.is_ok else "✗"
        return f"{status} {self.key}: {self.message}"


def check_env_var(key: str, required: bool = True, validator=None, description: str = "") -> EnvCheckResult:
    """Check if environment variable is present and optionally validate its value."""
    value = get_env_var(key)
    
    if not value:
        if required:
            return EnvCheckResult(key, False, False, f"Missing required variable {description}")
        else:
            return EnvCheckResult(key, False, True, f"Optional variable not set {description}")
    
    # If validator is provided, use it
    if validator:
        try:
            is_valid = validator(value)
            if is_valid:
                return EnvCheckResult(key, True, True, f"Present and valid {description}")
            else:
                return EnvCheckResult(key, True, False, f"Present but invalid format {description}")
        except Exception as e:
            return EnvCheckResult(key, True, False, f"Present but validation failed: {e}")
    
    # Default case - just check if present
    return EnvCheckResult(key, True, True, f"Present {description}")


def validate_url(url: str) -> bool:
    """Validate URL format."""
    if not url:
        return False
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return bool(url_pattern.match(url))


def validate_email(email: str) -> bool:
    """Validate email format."""
    if not email:
        return False
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    return bool(email_pattern.match(email))


def check_jitbit_env() -> List[EnvCheckResult]:
    """Check Jitbit environment variables."""
    return [
        check_env_var(ENV_VARS["JITBIT_API_TOKEN"], required=True, description="(Jitbit API token)"),
        check_env_var(ENV_VARS["JITBIT_BASE_URL"], required=True, validator=validate_url, 
                     description="(Jitbit base URL)")
    ]


def check_jira_env() -> List[EnvCheckResult]:
    """Check Jira environment variables."""
    return [
        check_env_var(ENV_VARS["JIRA_EMAIL"], required=True, validator=validate_email,
                     description="(Jira email address)"),
        check_env_var(ENV_VARS["JIRA_API_TOKEN"], required=True, description="(Jira API token)")
    ]


def check_llm_env() -> List[EnvCheckResult]:
    """Check LLM (Scaleway) environment variables."""
    results = []
    
    # Check for either SCW_SECRET_KEY or SCW_API_KEY
    secret_key = get_env_var(ENV_VARS["SCW_SECRET_KEY"])
    api_key = get_env_var(ENV_VARS["SCW_API_KEY"])
    
    if secret_key or api_key:
        if secret_key:
            results.append(EnvCheckResult(ENV_VARS["SCW_SECRET_KEY"], True, True, 
                                        "(Scaleway secret key present)"))
        if api_key:
            results.append(EnvCheckResult(ENV_VARS["SCW_API_KEY"], True, True,
                                        "(Scaleway API key present)"))
    else:
        results.append(EnvCheckResult("SCW_SECRET_KEY or SCW_API_KEY", False, False,
                                    "(At least one Scaleway key required)"))
    
    results.extend([
        check_env_var(ENV_VARS["SCW_OPENAI_BASE_URL"], required=True, validator=validate_url,
                     description="(Scaleway OpenAI base URL)"),
        check_env_var(ENV_VARS["LLM_MODEL"], required=False, description="(LLM model name, optional)")
    ])
    
    return results


def check_all_env() -> Dict[str, List[EnvCheckResult]]:
    """Check all environment variables and group by service."""
    return {
        "jitbit": check_jitbit_env(),
        "jira": check_jira_env(), 
        "llm": check_llm_env()
    }


def get_env_status_summary() -> Dict[str, Dict[str, any]]:
    """Get a summary of environment status for web UI."""
    env_results = check_all_env()
    
    summary = {}
    for service, results in env_results.items():
        total = len(results)
        ok = sum(1 for r in results if r.is_ok)
        summary[service] = {
            "ok": ok,
            "total": total,
            "status": "ok" if ok == total else "error",
            "details": [{"key": r.key, "ok": r.is_ok, "message": r.message} for r in results]
        }
    
    return summary


def print_env_check():
    """Print environment check results to console."""
    env_results = check_all_env()
    
    print("=== Environment Check ===")
    
    for service, results in env_results.items():
        print(f"\n{service.upper()}:")
        for result in results:
            print(f"  {result}")
    
    # Summary
    total_checks = sum(len(results) for results in env_results.values())
    ok_checks = sum(sum(1 for r in results if r.is_ok) for results in env_results.values())
    
    print(f"\nSummary: {ok_checks}/{total_checks} checks passed")
    
    if ok_checks < total_checks:
        print("\n⚠️  Some environment variables are missing or invalid.")
        print("Please check your .env file or environment configuration.")
        return False
    else:
        print("\n✅ All environment checks passed!")
        return True
