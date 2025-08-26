#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process_tickets_with_llm.py

Standalone script to process exported Jitbit tickets with Together.ai, classify relevance,
and produce two outputs:
- Ticket_Data.JSON: JSON array of relevant ticket summaries (LLM-normalized; includes original Subject)
- not relevant.json: raw ticket objects for tickets classified as "not relevant"

Input is expected to be the output from ticket_relevante_felder.py:
{
  "export_info": {...},
  "tickets": [
     {
       "ticket_id": int,
       "CategoryName": str,
       "IssueDate": str,
       "Subject": str,
       "Body": str,
       "Status": "Geschlossen",
       "Url": str,
       "Attachments": [{ "FileName": str, "Url": str, "Size": int }],
       "kommentare": [
          { "CommentDate": str, "Body": str, "UserName": str, "Attachments": [{...}] }
       ]
     },
     ...
  ]
}

Environment:
- .env must include:
  - TOGETHER_API_KEY=<key> (required)
  - LLM_MODEL=<Together model id> (preferred, e.g., openai/gpt-oss-120b)
  - Optional fallback: TOGETHER_MODEL=<model id>

Usage:
  python process_tickets_with_llm.py \
    --input JitBit_relevante_Tickets.json \
    --output Ticket_Data.JSON \
    --not-relevant-out "not relevant.json" \
    --limit 50 \
    --max-calls 200 \
    --max-tokens 3000 \
    --start-index 0 \
    --append

Notes:
- --limit counts ONLY relevant tickets (continue until N relevant are gathered or input ends)
- Image URLs are aggregated by the script as "image_urls" (array). The LLM must not include URLs.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


# ---------------------------
# Environment loading helpers
# ---------------------------

def _fallback_load_dotenv() -> None:
    """
    Lightweight .env loader if python-dotenv is not installed.
    Only sets variables not already present in os.environ.
    """
    env_path = Path(".env")
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        # Silently ignore .env parsing errors in fallback
        pass


def load_env() -> None:
    """
    Load environment variables. Prefer python-dotenv if available,
    else fall back to minimal parser.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        _fallback_load_dotenv()


# ---------------------------
# Together.ai LLM client
# ---------------------------

class TogetherClient:
    API_URL = "https://api.together.xyz/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 3000,
        temperature: float = 0.2,
        request_timeout: int = 60,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 32.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """
        Call Together.ai chat completions with retry on 429/5xx.
        Returns response text (assistant content).
        Raises on persistent failures.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = requests.post(
                    self.API_URL,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=self.request_timeout,
                )
            except requests.RequestException as e:
                if attempt <= self.max_retries:
                    wait_s = self._compute_backoff(attempt)
                    print(f"[warn] Network error: {e}. Retry {attempt}/{self.max_retries} in {wait_s:.1f}s")
                    time.sleep(wait_s)
                    continue
                raise RuntimeError(f"Network error after {self.max_retries} retries: {e}")

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    raise RuntimeError("Invalid JSON response from Together.ai")
                content = self._extract_content(data)
                if content is None:
                    raise RuntimeError("Together.ai response missing content")
                return content

            # Retry on 429/5xx
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt <= self.max_retries:
                    wait_s = self._compute_backoff(attempt)
                    detail = ""
                    try:
                        detail = resp.text[:200]
                    except Exception:
                        pass
                    print(f"[warn] HTTP {resp.status_code}. Retry {attempt}/{self.max_retries} in {wait_s:.1f}s. {detail}")
                    time.sleep(wait_s)
                    continue
                raise RuntimeError(f"HTTP {resp.status_code} after {self.max_retries} retries: {resp.text[:500]}")

            # Other non-retryable errors:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:1000]}")

    def _compute_backoff(self, attempt: int) -> float:
        base = min(self.backoff_cap, self.backoff_base * (2 ** (attempt - 1)))
        jitter = random.uniform(0, 0.25 * base)
        return base + jitter

    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> Optional[str]:
        try:
            choices = data.get("choices")
            if not choices:
                return None
            message = choices[0].get("message")
            if not message:
                return None
            content = message.get("content")
            if not isinstance(content, str):
                return None
            return content
        except Exception:
            return None


# ---------------------------
# Prompting
# ---------------------------

SYSTEM_PROMPT = """You analyze IT support tickets. Decide if the ticket addresses a real technical problem and a concrete solution (not a simple request like password reset, user creation, or similar routine tasks).
If relevant, produce a concise summary that enables deriving the solution steps; remove disclaimers, addresses, signatures, and unrelated content. Use Markdown within the fields where asked.

Strictly output a single JSON object only (no code fences, no prose). Exact keys and schema:
{
  "ticket_id": <int>,
  "date": "<ISO or original date>",
  "problem": "<string, Markdown allowed>",
  "solution": "<string, Markdown allowed>"
}

If the ticket is not relevant, set:
"problem": "not relevant", "solution": "".

Do not include any URLs in the JSON. The system will extract URLs separately.

IMPORTANT LANGUAGE INSTRUCTIONS: ALWAYS USE THE LANGUAGE OF THE TICKET (e.g., if the ticket is in German, respond in German).
IMPORTANT DATA PROTECTION INSTRUCTIONS: Do not include any personal data, email addresses, or names in the output. YOU ABSOLUTELY MUST anonymize any such information from the problem and solution fields!

"""

USER_SUFFIX_INSTRUCTION = """Output only a single JSON object with the exact keys: ticket_id, date, problem, solution. Do not include any URLs."""


def build_user_prompt_and_urls(ticket: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Build stitched prompt text for a ticket and collect all attachment URLs.
    Returns (user_prompt, attachment_urls).
    """
    tid = ticket.get("ticket_id", "")
    subject = ticket.get("Subject", "")
    issue_date = ticket.get("IssueDate", "")
    category = ticket.get("CategoryName", "")
    ticket_url = ticket.get("Url", "")

    initial_body = ticket.get("Body", "") or ""
    # Ensure it's a string (export should already normalize HTML)
    if not isinstance(initial_body, str):
        initial_body = str(initial_body)

    lines: List[str] = []
    lines.append(f"Ticket ID: {tid}")
    lines.append(f"Subject: {subject}")
    lines.append(f"Date: {issue_date}")
    lines.append(f"Category: {category}")
    lines.append(f"URL (ticket page): {ticket_url}")
    lines.append("")
    lines.append("Initial Body:")
    lines.append(initial_body.strip())
    lines.append("")
    lines.append("Kommentare:")

    attachment_urls: List[str] = []

    # Comments
    comments = ticket.get("kommentare") or []
    if isinstance(comments, list):
        for c in comments:
            try:
                cdate = c.get("CommentDate", "")
                uname = c.get("UserName", "")
                cbody = c.get("Body", "") or ""
                if not isinstance(cbody, str):
                    cbody = str(cbody)
                lines.append(f"- [{cdate}] {uname}: {cbody.strip()}")
                c_atts = c.get("Attachments") or []
                if isinstance(c_atts, list) and c_atts:
                    att_line_parts = []
                    for att in c_atts:
                        fn = (att.get("FileName") or "").strip()
                        url = (att.get("Url") or "").strip()
                        sz = att.get("Size")
                        if url:
                            attachment_urls.append(url)
                        if fn and url:
                            att_line_parts.append(f"{fn} ({url})")
                        elif fn:
                            att_line_parts.append(fn)
                        elif url:
                            att_line_parts.append(url)
                    if att_line_parts:
                        lines.append(f"  Attachments: {', '.join(att_line_parts)}")
            except Exception:
                # robust to malformed comment entries
                continue

    # Ticket-level attachments
    lines.append("")
    lines.append("Ticket-level Attachments:")
    t_atts = ticket.get("Attachments") or []
    if isinstance(t_atts, list) and t_atts:
        for att in t_atts:
            try:
                fn = (att.get("FileName") or "").strip()
                url = (att.get("Url") or "").strip()
                if url:
                    attachment_urls.append(url)
                if fn and url:
                    lines.append(f"- {fn} ({url})")
                elif fn:
                    lines.append(f"- {fn}")
                elif url:
                    lines.append(f"- {url}")
            except Exception:
                continue

    lines.append("")
    lines.append(USER_SUFFIX_INSTRUCTION)

    return "\n".join(lines), attachment_urls


# ---------------------------
# JSON parsing / normalization
# ---------------------------

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

URL_RE = re.compile(r"https?://[^\s\]\)\"'<>]+", re.IGNORECASE)

# Image URL helpers
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}

def _looks_like_image_url(u: str) -> bool:
    try:
        if not isinstance(u, str):
            return False
        lu = u.lower()
        # Quick heuristic: path or query contains an image extension
        if any(ext in lu for ext in IMAGE_EXTS):
            return True
        # Jitbit often serves files via extensionless endpoints like /helpdesk/File/Get/{id}
        # Treat those as images for downstream use (consumers can further filter if needed).
        from urllib.parse import urlparse
        p = urlparse(lu)
        path = (p.path or "")
        if "/file/get/" in path or "/helpdesk/file/get/" in path:
            return True
        return False
    except Exception:
        return False

def _filter_image_urls(urls: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for u in urls:
        if isinstance(u, str) and u.startswith(("http://", "https://")) and _looks_like_image_url(u):
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out

def strip_code_fences(text: str) -> str:
    """
    Remove surrounding Markdown code fences like ```json ... ``` or ``` ... ```.
    Returns the original text if no matching fences wrap the content.
    """
    if not isinstance(text, str):
        return str(text)

    s = text.strip()
    if not s.startswith("```"):
        return s

    # Find the first line break after opening fence
    nl = s.find("\n")
    if nl == -1:
        # Single-line with only backticks; just strip them
        return s.strip("`").strip()

    # Opening fence line may contain a language hint (e.g., ```json)
    # The closing fence must be on its own line with ```
    opening_line = s[:nl].strip()
    if not opening_line.startswith("```"):
        return s

    # Look for the last occurrence of a closing fence starting at a line start
    closing_idx = s.rfind("\n```")
    if closing_idx == -1:
        # No closing fence found; return without modification
        return s

    inner = s[nl + 1:closing_idx].strip()
    return inner


def extract_first_json_object(text: str) -> Optional[str]:
    """
    Extract the first top-level JSON object substring.
    - Strips Markdown code fences if present.
    - Tracks string state to avoid counting braces inside strings.
    """
    if not text:
        return None

    cleaned = strip_code_fences(text)

    # Find first '{'
    start = cleaned.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return cleaned[start:i + 1]

    # Fallback to regex (less reliable if braces occur in strings)
    m = JSON_OBJECT_RE.search(cleaned)
    return m.group(0) if m else None


# Heuristic repair helpers to make JSON parsing robust against common LLM mistakes

def _find_solution_string_bounds(obj_text: str) -> Optional[Tuple[int, int]]:
    """
    Find the start (index after opening quote) and end (index of closing quote) of the solution string value.
    Returns (start, end) or None if not found.
    """
    m = re.search(r'"solution"\s*:\s*"', obj_text)
    if not m:
        return None
    i = m.end()
    start = i
    escape = False
    while i < len(obj_text):
        ch = obj_text[i]
        if escape:
            escape = False
        else:
            if ch == "\\":
                escape = True
            elif ch == '"':
                return (start, i)
        i += 1
    return None


def _merge_numeric_keys_into_solution(obj_text: str) -> Tuple[str, Optional[str]]:
    """
    Merge stray numeric keys like ,"6": "text" into the end of the solution string.
    Returns (new_text, appended_text or None).
    """
    pattern = re.compile(r',\s*"\d+"\s*:\s*"(.*?)"\s*(?=[,}])', re.DOTALL)
    parts = []
    spans = []
    for m in pattern.finditer(obj_text):
        parts.append(m.group(1))
        spans.append(m.span())

    if not spans:
        return obj_text, None

    # Remove spans from text
    new_text_parts = []
    last = 0
    for s, e in spans:
        new_text_parts.append(obj_text[last:s])
        last = e
    new_text_parts.append(obj_text[last:])
    new_text = "".join(new_text_parts)

    # Append collected text to the end of the solution string if present
    bounds = _find_solution_string_bounds(new_text)
    if bounds:
        s_idx, e_idx = bounds
        append_text = " " + " ".join(parts).strip()
        new_text = new_text[:e_idx] + append_text + new_text[e_idx:]
        return new_text, append_text.strip()
    else:
        # If no solution field, just return with numeric keys removed
        return new_text, " ".join(parts).strip() if parts else None


def repair_llm_json_str(obj_text: str) -> str:
    """
    Attempt to repair common top-level JSON issues:
    - Missing ticket_id key at start: { 12345, ... } -> {"ticket_id": 12345, ...}
    - Bare ISO date value between fields -> insert as "date": "<iso>"
    - Stray numeric keys like "6": "..." -> merge into solution string
    """
    t = obj_text

    # Missing "ticket_id" key at start
    t = re.sub(r'^{\s*(\d+)\s*,', r'{"ticket_id": \1,', t)

    # Bare ISO date token between fields (with comma or end brace)
    t = re.sub(
        r'([{,]\s*)(\d{4}-\d{2}-\d{2}T[0-9:.+\-Zz]+)(\s*[,}])',
        lambda m: f'{m.group(1)}"date": "{m.group(2)}"{m.group(3)}',
        t,
    )

    # Merge stray numeric keys into the solution value
    t, _ = _merge_numeric_keys_into_solution(t)

    return t


def salvage_llm_fields(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort extraction when JSON parsing still fails.
    Tries to extract ticket_id/date/problem/solution via regex boundaries.
    """
    cleaned = strip_code_fences(raw_text or "")
    obj = extract_first_json_object(cleaned) or cleaned

    result: Dict[str, Any] = {}

    m = re.search(r'"ticket_id"\s*:\s*(\d+)', obj)
    if m:
        try:
            result["ticket_id"] = int(m.group(1))
        except Exception:
            pass

    m = re.search(r'"date"\s*:\s*"([^"]+)"', obj)
    if m:
        result["date"] = m.group(1).strip()
    else:
        # bare ISO date anywhere
        m2 = re.search(r'([12]\d{3}-\d{2}-\d{2}T[0-9:.+\-Zz]+)', obj)
        if m2:
            result["date"] = m2.group(1).strip()

    # problem: capture until next known key
    m = re.search(r'"problem"\s*:\s*"(.*?)"\s*,\s*"(?:solution|date|ticket_id)"', obj, re.DOTALL)
    if not m:
        m = re.search(r'"problem"\s*:\s*"(.*?)"\s*[},]', obj, re.DOTALL)
    if m:
        result["problem"] = m.group(1).strip()

    # solution: capture until , or }
    m = re.search(r'"solution"\s*:\s*"(.*?)"\s*[},]', obj, re.DOTALL)
    if m:
        result["solution"] = m.group(1).strip()

    if "problem" in result or "solution" in result:
        result.setdefault("problem", "")
        result.setdefault("solution", "")
        return result

    return None


def normalize_url_field(url_field: Any, attachment_urls: List[str], ticket_page_url: str) -> str:
    """
    Ensure a single URL string:
    - If url_field contains URLs, pick the first.
    - Else pick first attachment URL if present.
    - Else fallback to ticket_page_url (may be empty).
    """
    # If model returned a string, try to extract URL
    if isinstance(url_field, str):
        m = URL_RE.search(url_field)
        if m:
            return m.group(0).strip()
        # If it's a non-empty string w/o URL patterns, leave it if it looks like a URL
        if url_field.strip().startswith(("http://", "https://")):
            return url_field.strip()

    # Try attachments
    for u in attachment_urls:
        if isinstance(u, str) and u.startswith(("http://", "https://")):
            return u.strip()

    # Fallback to ticket page URL
    if isinstance(ticket_page_url, str):
        return ticket_page_url.strip()

    return ""


def parse_and_validate_llm_json(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Extract and parse JSON object from LLM output.
    Returns dict or None if parsing fails.
    Heuristically repairs common issues and finally attempts a salvage pass.
    """
    obj_str = extract_first_json_object(raw_text or "")
    if not obj_str:
        # Try salvage directly from raw text if no object found
        return salvage_llm_fields(raw_text)

    # First, a strict parse attempt
    try:
        return json.loads(obj_str)
    except Exception:
        pass

    # Second, sanitize control chars, NBSPs, trailing commas, and flatten newlines
    s = obj_str
    try:
        s = s.replace("\u00A0", " ")
        s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", s)
        s = re.sub(r",\s*([}\]])", r"\1", s)
        s = s.replace("\r", " ").replace("\n", " ")
        # Heuristic repairs for common Together/LLM mistakes
        s = repair_llm_json_str(s)
        return json.loads(s)
    except Exception:
        # Final salvage: try to pull fields without full JSON validity
        return salvage_llm_fields(raw_text)


def is_not_relevant(problem_field: Any) -> bool:
    if not isinstance(problem_field, str):
        return False
    val = problem_field.strip().lower()
    # Support multiple languages/synonyms
    return val in {"not relevant", "nicht relevant", "irrelevant"}


def normalize_summary(
    llm_obj: Dict[str, Any],
    ticket: Dict[str, Any],
    attachment_urls: List[str],
) -> Dict[str, Any]:
    """
    Ensure required keys with safe defaults; coerce types; and attach all URLs found in attachments.
    Prefer ground truth ticket_id and IssueDate from input if LLM deviates.
    """
    ticket_id = ticket.get("ticket_id")
    issue_date = ticket.get("IssueDate") or ""
    subject = ticket.get("Subject") or ""

    # Coerce and override ticket_id from source of truth
    out_ticket_id = int(ticket_id) if isinstance(ticket_id, (int, float, str)) and str(ticket_id).isdigit() else ticket_id

    problem = llm_obj.get("problem", "")
    if not isinstance(problem, str):
        problem = str(problem)

    solution = llm_obj.get("solution", "")
    if not isinstance(solution, str):
        solution = str(solution)

    date_val = llm_obj.get("date", issue_date)
    if not isinstance(date_val, str) or not date_val.strip():
        date_val = str(issue_date)

    # Build attachment URLs list (http/https only), preserve order, deduplicate
    urls: List[str] = []
    for u in attachment_urls:
        if isinstance(u, str) and u.startswith(("http://", "https://")):
            u = u.strip()
            if u:
                urls.append(u)
    seen = set()
    urls_dedup: List[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            urls_dedup.append(u)

    images_dedup = _filter_image_urls(urls_dedup)

    return {
        "ticket_id": out_ticket_id,
        "date": date_val,
        "subject": subject,
        "problem": problem,
        "solution": solution,
        "image_urls": images_dedup,
    }


# ---------------------------
# Streaming input iterator
# ---------------------------

def iter_tickets_streaming(path: Path):
    """
    Iterate tickets from a potentially very large JSON file without loading it fully.
    Supports:
    - Object with top-level "tickets": [ ... ]
    - Top-level array [ ... ]
    Tries ijson for streaming; falls back to regular json load if ijson is not available.
    """
    # Try ijson for streaming parse
    try:
        import ijson  # type: ignore
        # Try object with "tickets"
        try:
            with path.open("rb") as f:
                for item in ijson.items(f, "tickets.item"):
                    yield item
                return
        except Exception:
            pass
        # Try top-level array
        try:
            with path.open("rb") as f:
                for item in ijson.items(f, "item"):
                    yield item
                return
        except Exception:
            pass
    except Exception:
        pass

    # Fallback: non-streaming (may be memory-heavy)
    try:
        payload = json_load(path)
    except Exception as e:
        print(f"❌ Failed to load JSON from {path}: {e}")
        sys.exit(1)

    if isinstance(payload, dict) and isinstance(payload.get("tickets"), list):
        for item in payload["tickets"]:
            yield item
        return
    if isinstance(payload, list):
        for item in payload:
            yield item
        return

    print("❌ Input file does not contain a 'tickets' array or a top-level array.")
    sys.exit(1)

# ---------------------------
# File IO helpers
# ---------------------------

def json_load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

# ---------------------------
# Utility: load all tickets (non-streaming, allows sorting)
# ---------------------------

def load_all_tickets(path: Path) -> List[Dict[str, Any]]:
    """
    Load the entire input file into memory and return a list of tickets.
    Supports:
    - Object with top-level "tickets": [ ... ]
    - Top-level array [ ... ]
    Exits the program if structure is invalid.
    """
    try:
        payload = json_load(path)
    except Exception as e:
        print(f"❌ Failed to load JSON from {path}: {e}")
        sys.exit(1)

    if isinstance(payload, dict) and isinstance(payload.get("tickets"), list):
        return payload["tickets"]
    if isinstance(payload, list):
        return payload

    print("❌ Input file does not contain a 'tickets' array or a top-level array.")
    sys.exit(1)

# ---------------------------
# Debug helpers
# ---------------------------

def log_llm_parse_failure(debug_dir: Path, idx: int, ticket: Dict[str, Any], raw: str, prompt: str, reason: str) -> None:
    """
    Persist raw LLM output (and prompt tail) for tickets where JSON parsing fails.
    This helps diagnose whether the LLM returned invalid JSON or no JSON at all.
    """
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        tid = ticket.get("ticket_id")
        fname = debug_dir / f"ticket_{tid}_idx_{idx}.txt"
        with fname.open("w", encoding="utf-8") as f:
            f.write(f"Reason: {reason}\n\n")
            f.write("=== LLM raw output ===\n")
            f.write(raw if isinstance(raw, str) else str(raw))
            f.write("\n\n=== User prompt (tail, up to 5000 chars) ===\n")
            tail = prompt[-5000:] if isinstance(prompt, str) else str(prompt)
            f.write(tail)
    except Exception:
        # best-effort logging
        pass


# ---------------------------
# Main processing function
# ---------------------------

def process_tickets(
    input_path: Path,
    output_path: Path,
    not_relevant_path: Path,
    model: str,
    api_key: str,
    limit_relevant: Optional[int],
    max_calls: Optional[int],
    max_tokens: int,
    temperature: float,
    start_index: int,
    append: bool,
    only_ticket_id: Optional[int] = None,
    newest_first: bool = False,
) -> None:
    # Determine input iteration strategy
    if newest_first:
        # Load entire file into memory and sort by ticket_id descending
        tickets_all = load_all_tickets(input_path)

        def _ticket_id_key(t: Dict[str, Any]) -> int:
            tid = t.get("ticket_id")
            try:
                return int(tid)
            except Exception:
                return -1

        tickets_all_sorted = sorted(tickets_all, key=_ticket_id_key, reverse=True)
        tickets_iter = tickets_all_sorted  # iterate in-memory list
        input_mode_desc = "loaded fully, sorted by ticket_id desc"
    else:
        # Prepare streaming input iterator (handles very large files)
        tickets_iter = iter_tickets_streaming(input_path)
        input_mode_desc = "streaming if possible"

    # Prepare outputs
    relevant_list: List[Dict[str, Any]] = []
    not_relevant_list: List[Dict[str, Any]] = []

    if append:
        if output_path.exists():
            try:
                existing = json_load(output_path)
                if isinstance(existing, list):
                    relevant_list.extend(existing)
                else:
                    print(f"[warn] Existing {output_path.name} is not a JSON array. Overwriting.")
            except Exception as e:
                print(f"[warn] Could not read existing {output_path.name}: {e}. Overwriting.")
        if not_relevant_path.exists():
            try:
                existing = json_load(not_relevant_path)
                if isinstance(existing, dict) and isinstance(existing.get("tickets"), list):
                    not_relevant_list.extend(existing["tickets"])
                else:
                    print(f"[warn] Existing {not_relevant_path.name} is not in expected format. Overwriting.")
            except Exception as e:
                print(f"[warn] Could not read existing {not_relevant_path.name}: {e}. Overwriting.")

    client = TogetherClient(
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    total_calls = 0
    newly_relevant = 0
    processed_count = 0

    print(f"Input: {input_path} ({input_mode_desc})")
    print(f"Model: {model}")
    print(f"Max tokens: {max_tokens}, Temperature: {temperature}")
    print(f"Limit (relevant only): {limit_relevant if limit_relevant is not None else 'none'}")
    print(f"Max calls: {max_calls if max_calls is not None else 'none'}")
    print(f"Start index: {start_index}, Append: {append}")
    print("")

    for idx, ticket in enumerate(tickets_iter):
        if idx < start_index:
            continue
        if only_ticket_id is not None and ticket.get("ticket_id") != only_ticket_id:
            continue

        if max_calls is not None and total_calls >= max_calls:
            print(f"\nReached max_calls={max_calls}. Stopping.")
            break
        if limit_relevant is not None and newly_relevant >= limit_relevant:
            print(f"\nReached limit of relevant tickets: {limit_relevant}. Stopping.")
            break

        user_prompt, att_urls = build_user_prompt_and_urls(ticket)

        # Perform LLM call
        total_calls += 1
        try:
            raw = client.chat(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            print(f"[warn] LLM call failed for ticket index {idx} (id={ticket.get('ticket_id')}): {e}")
            # On failure, treat as not relevant to avoid blocking, but keep raw ticket for review
            not_relevant_list.append(ticket)
            continue

        # Parse JSON response
        llm_obj = parse_and_validate_llm_json(raw)
        if llm_obj is None:
            # Diagnose whether no JSON object was detected or parsing failed
            extracted = extract_first_json_object(raw or "")
            reason = "no JSON object found in LLM response" if not extracted else "invalid JSON (failed to parse extracted object)"
            print(f"[warn] Could not parse JSON for ticket index {idx} (id={ticket.get('ticket_id')}): {reason}. Classifying as not relevant.")
            # Persist raw output for debugging
            log_llm_parse_failure(Path("llm_parse_errors"), idx, ticket, raw or "", user_prompt, reason)
            not_relevant_list.append(ticket)
            continue

        # Classification
        if is_not_relevant(llm_obj.get("problem")):
            not_relevant_list.append(ticket)
        else:
            summary = normalize_summary(llm_obj, ticket, att_urls)
            relevant_list.append(summary)
            newly_relevant += 1

        # Progress log
        processed_count += 1
        if processed_count % 10 == 0:
            print(f"Processed {processed_count} tickets | Relevant (new): {newly_relevant} | Not relevant (new): {len(not_relevant_list)} | Calls: {total_calls}")

    # Write outputs atomically
    atomic_write_json(output_path, relevant_list)
    atomic_write_json(not_relevant_path, {"tickets": not_relevant_list})

    print("\nDone.")
    print(f"Relevant summaries written to: {output_path} (count: {len(relevant_list)})")
    print(f"Not relevant raw tickets written to: {not_relevant_path} (count: {len(not_relevant_list)})")
    print(f"Total API calls: {total_calls}")


# ---------------------------
# CLI
# ---------------------------

def resolve_model_from_env() -> str:
    # Priority: LLM_MODEL -> TOGETHER_MODEL -> default
    model = os.environ.get("LLM_MODEL") or os.environ.get("TOGETHER_MODEL")
    if not model:
        model = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
    return model


def main() -> None:
    load_env()
    api_key = os.environ.get("TOGETHER_API_KEY", "").strip()
    if not api_key:
        print("❌ TOGETHER_API_KEY not set in environment or .env")
        sys.exit(1)

    model = resolve_model_from_env()

    parser = argparse.ArgumentParser(description="Process Jitbit tickets with Together.ai and classify relevance.")
    parser.add_argument("--input", default="JitBit_relevante_Tickets.json", help="Path to input JSON (export from Jitbit).")
    parser.add_argument("--output", default="Ticket_Data.JSON", help="Path to aggregated relevant summaries (JSON array).")
    parser.add_argument("--not-relevant-out", default="not relevant.json", help="Path for raw 'not relevant' tickets JSON.")
    parser.add_argument("--limit", type=int, default=None, help="Number of relevant tickets to collect (counts relevant only).")
    parser.add_argument("--max-calls", type=int, default=None, help="Safety cap on total LLM calls.")
    parser.add_argument("--max-tokens", type=int, default=3000, help="max_tokens for Together.ai.")
    parser.add_argument("--temperature", type=float, default=0.2, help="temperature for Together.ai.")
    parser.add_argument("--start-index", type=int, default=0, help="Start processing from this ticket index.")
    parser.add_argument("--append", action="store_true", help="Append to existing output files if present.")
    parser.add_argument("--only-ticket-id", type=int, default=None, help="Process only the ticket with this ID.")
    parser.add_argument(
        "--newest-first",
        action="store_true",
        help="Process tickets in descending ticket_id order (loads the entire input into memory)."
    )
    args = parser.parse_args()

    try:
        process_tickets(
            input_path=Path(args.input),
            output_path=Path(args.output),
            not_relevant_path=Path(args["not_relevant_out"]) if isinstance(args, dict) else Path(getattr(args, "not_relevant_out")),
            model=model,
            api_key=api_key,
            limit_relevant=args.limit,
            max_calls=args.max_calls,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            start_index=args.start_index,
            append=args.append,
            only_ticket_id=getattr(args, "only_ticket_id", None),
            newest_first=getattr(args, "newest_first", False),
        )
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
