import os
import base64
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
import re
import html
import argparse
import json
import time
from datetime import datetime, timezone, timedelta

# ------------------------------
# 1️⃣  Konfiguration
# ------------------------------
# Load environment variables from a local .env file if present
load_dotenv()
JIRA_EMAIL = os.getenv("JIRA_EMAIL")          # deine Atlassian‑E‑Mail
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")  # das erzeugte API‑Token


JIRA_BASE_URL = "https://timeplan.atlassian.net"  # ohne /rest/…

if not JIRA_EMAIL or not JIRA_API_TOKEN:
    raise RuntimeError("Bitte JIRA_EMAIL und JIRA_API_TOKEN setzen (z.B. in einer .env Datei im Projektordner).")

# ------------------------------
# 2️⃣  Header erzeugen
# ------------------------------
basic_auth = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {basic_auth}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "JiraFetcher/1.0 (+python requests)"
}

# Configure requests Session with retries and set default headers
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

retries = Retry(
    total=5,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET"])
)
SESSION.mount("https://", HTTPAdapter(max_retries=retries))
SESSION.mount("http://", HTTPAdapter(max_retries=retries))

# Default timeout: (connect, read) in seconds
TIMEOUT = (10, 30)

# Progress logging toggle
PROGRESS = False
DETAILED_LOG = False

def log_progress(msg: str):
    try:
        if PROGRESS:
            print(str(msg), flush=True)
    except Exception:
        # avoid progress printing breaking execution
        pass

# Minimal heartbeat printing every HEARTBEAT_INTERVAL seconds, even without --progress
HEARTBEAT_INTERVAL = 10
_heartbeat_start_ts = 0.0
_heartbeat_last_ts = 0.0

def reset_heartbeat():
    global _heartbeat_start_ts, _heartbeat_last_ts
    _heartbeat_start_ts = time.time()
    _heartbeat_last_ts = 0.0

def heartbeat(label: str, current: int = None, total: int = None):
    # Print a minimal heartbeat every HEARTBEAT_INTERVAL seconds if --progress is not enabled.
    global _heartbeat_last_ts, _heartbeat_start_ts
    if PROGRESS:
        return
    now = time.time()
    if _heartbeat_start_ts == 0.0:
        _heartbeat_start_ts = now
    if (_heartbeat_last_ts == 0.0) or (now - _heartbeat_last_ts >= HEARTBEAT_INTERVAL):
        elapsed = int(now - _heartbeat_start_ts)
        rate = None
        if current is not None and elapsed > 0:
            try:
                rate = current / elapsed
            except Exception:
                rate = None
        eta = None
        if rate and total:
            remaining = max(0, total - current)
            try:
                eta = int(remaining / rate) if rate > 0 else None
            except Exception:
                eta = None
        msg = f"[heartbeat {label}] elapsed={elapsed}s"
        if current is not None:
            msg += f" progress={current}"
            if total is not None:
                msg += f"/≈{total}"
        if rate is not None:
            msg += f" rate={rate:.1f}/s"
        if eta is not None:
            msg += f" ETA≈{eta}s"
        try:
            print(msg, flush=True)
        except Exception:
            pass
        _heartbeat_last_ts = now

# ------------------------------
# Filter helpers (resolved-only, resolved-after)
# ------------------------------
def parse_resolved_after_arg(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{8}", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    raise ValueError("Date must be YYYYMMDD or YYYY-MM-DD")

def build_filtered_jql(base_jql: str, resolved_only: bool, resolved_after: str, resolved_before: str) -> str:
    jql = base_jql or ""
    lower = jql.lower()
    order_by = ""
    idx = lower.rfind(" order by ")
    if idx != -1:
        order_by = jql[idx:]
        jql_main = jql[:idx]
    else:
        jql_main = jql
    clauses = [f"({jql_main.strip()})"] if jql_main.strip() else []
    if resolved_only:
        clauses.append("statusCategory = Done")
    if resolved_after:
        date_str = parse_resolved_after_arg(resolved_after)
        clauses.append(f'resolutiondate >= "{date_str}"')
    if resolved_before:
        date_str_b = parse_resolved_after_arg(resolved_before)
        clauses.append(f'resolutiondate <= "{date_str_b} 23:59"')
    filtered = " AND ".join(clauses) if clauses else ""
    return (filtered + " " + order_by).strip()

def iso_to_datetime(s: str):
    try:
        # Normalize timezone like +0200 -> +02:00; also handle Z
        m = re.match(r"(.+)([+-]\d{2})(\d{2})$", s or "")
        if m:
            s = f"{m.group(1)}{m.group(2)}:{m.group(3)}"
        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None

def meets_resolved_filters(details: dict, resolved_only: bool, resolved_after: str, resolved_before: str) -> bool:
    if resolved_only and not details.get("resolved"):
        return False
    rdt = iso_to_datetime(details.get("resolved") or "")
    if resolved_after:
        cutoff = parse_resolved_after_arg(resolved_after)
        cutoff_dt = datetime.fromisoformat(cutoff + "T00:00:00+00:00")
        if not rdt or rdt < cutoff_dt:
            return False
    if resolved_before:
        cutoff_b = parse_resolved_after_arg(resolved_before)
        end_excl = datetime.fromisoformat(cutoff_b + "T00:00:00+00:00") + timedelta(days=1)
        if not rdt or rdt >= end_excl:
            return False
    return True

# ------------------------------
# Helper functions for text/ADF/comments
# ------------------------------
def strip_html(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r'<br\s*/?>', '\n', s, flags=re.IGNORECASE)
    s = re.sub(r'</?(?:div|p|li|ul|ol|table|tr|td|th|thead|tbody|strong|em|span|pre|code)[^>]*>', '', s, flags=re.IGNORECASE)
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()

def adf_to_text(adf):
    try:
        def walk(node):
            out = []
            if isinstance(node, dict):
                t = node.get('type')
                if t == 'text':
                    out.append(node.get('text', ''))
                if isinstance(node.get('content'), list):
                    for c in node['content']:
                        out.append(walk(c))
                if t in ('paragraph', 'heading', 'listItem'):
                    out.append('\n')
            elif isinstance(node, list):
                for c in node:
                    out.append(walk(c))
            return ''.join(out)
        txt = walk(adf)
        txt = re.sub(r'\n{3,}', '\n\n', txt)
        return txt.strip()
    except Exception:
        return ""

def get_issue_details(key: str):
    """
    Fetch full issue details including:
    - problem (description as plain text; prefers renderedFields HTML if available, else ADF -> text)
    - resolution name and resolutiondate
    - attachments (filename, mimeType, size, content url, thumbnail)
    - support comments (JSM agents/internal users; filters out customer comments)
    """
    params = {
        "fields": "summary,status,assignee,description,attachment,resolution,resolutiondate,created,issuetype",
        "expand": "renderedFields"
    }
    resp = SESSION.get(f"{JIRA_BASE_URL}/rest/api/3/issue/{key}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    issue = resp.json()
    fields = issue.get("fields", {}) or {}
    rendered = issue.get("renderedFields", {}) or {}

    # Problem/Description
    problem_html = rendered.get("description")
    if problem_html:
        problem = strip_html(problem_html)
    else:
        desc = fields.get("description")
        problem = adf_to_text(desc) if isinstance(desc, (dict, list)) else (desc or "")

    # Attachments
    atts = []
    for a in (fields.get("attachment") or []):
        atts.append({
            "filename": a.get("filename"),
            "mimeType": a.get("mimeType"),
            "size": a.get("size"),
            "content": a.get("content"),
            "thumbnail": a.get("thumbnail")
        })

    # Support comments (filter out customers)
    comments = []
    start_at = 0
    page_size = 100
    while True:
        c_resp = SESSION.get(
            f"{JIRA_BASE_URL}/rest/api/3/issue/{key}/comment",
            params={"startAt": start_at, "maxResults": page_size, "expand": "renderedBody"},
            timeout=TIMEOUT
        )
        c_resp.raise_for_status()
        cdata = c_resp.json() or {}
        values = cdata.get("comments") or cdata.get("values") or []
        total = cdata.get("total", len(values))

        for c in values:
            author = c.get("author") or {}
            acct = author.get("accountType")
            # In Jira Service Management Cloud, customers have accountType == "customer".
            # Treat non-customer as "support".
            if acct == "customer":
                continue
            body_html = c.get("renderedBody")
            if body_html:
                body_text = strip_html(body_html)
            else:
                body_text = adf_to_text(c.get("body"))
            comments.append({
                "created": c.get("created"),
                "author": author.get("displayName"),
                "body": body_text
            })

        start_at += len(values)
        if DETAILED_LOG:
            log_progress(f"[comments] {key}: fetched {start_at}/{total}")
        if start_at >= total or not values:
            break

    issue_id = issue.get("id")
    created = fields.get("created")
    category = (fields.get("issuetype") or {}).get("name")
    url = f"{JIRA_BASE_URL}/browse/{key}"

    return {
        "id": issue_id,
        "key": key,
        "summary": fields.get("summary"),
        "status": (fields.get("status") or {}).get("name"),
        "assignee": (fields.get("assignee") or {}).get("displayName"),
        "problem": problem,
        "resolution": (fields.get("resolution") or {}).get("name"),
        "resolved": fields.get("resolutiondate"),
        "attachments": atts,
        "support_comments": comments,
        "created": created,
        "category": category,
        "url": url
    }

# ------------------------------
# 3️⃣  Alle Issues holen (wie oben)
# ------------------------------
def get_first_issues(jql: str = "order by created ASC", limit: int = None):
    """
    Fetch issues that match the given JQL.
    - If 'limit' is provided, fetch up to that many issues (with pagination if needed).
    - If 'limit' is None, fetch ALL matching issues (full pagination).
    """
    issues = []
    start_at = 0
    page_size = 100
    printed = False

    reset_heartbeat()

    while True:
        if limit is not None:
            remaining = max(0, limit - len(issues))
            if remaining == 0:
                break
            batch_size = min(page_size, remaining)
            if not printed:
                print(f"Requesting up to {limit} issues with JQL: {jql}")
                printed = True
        else:
            batch_size = page_size
            if not printed:
                print(f"Requesting ALL issues with JQL: {jql}")
                printed = True

        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": batch_size,
            "fields": "summary,status,assignee,description,attachment,resolution,resolutiondate"
        }
        resp = SESSION.get(
            f"{JIRA_BASE_URL}/rest/api/3/search",
            params=params,
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json() or {}
        batch = data.get("issues") or []
        total = data.get("total", 0)

        prev_start = start_at

        issues.extend(batch)
        start_at += len(batch)

        log_progress(f"[search] startAt={prev_start} fetched={len(batch)} total≈{total} accumulated={len(issues)}")
        heartbeat("search", len(issues), total)

        if len(batch) == 0 or start_at >= total:
            break

    return issues

# Utility: export Jira issues to the same JSON schema as Jitbit exporter
def export_jira_json(issue_keys, out_path="JIRA_relevante_Tickets.json", filter_criteria=None, resolved_only=False, resolved_after=None, resolved_before=None, append=False):
    start_time = time.time()
    reset_heartbeat()
    tickets = []
    total_comments = 0
    total_ticket_attachments = 0
    total_comment_attachments = 0
    n = len(issue_keys)

    for idx, key in enumerate(issue_keys, 1):
        if idx == 1 or idx % 10 == 0 or idx == n:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0.0
            eta = int((n - idx) / rate) if rate > 0 else -1
            if DETAILED_LOG:
                log_progress(f"[{idx}/{n}] Fetching {key} | {rate:.1f} issues/s | ETA {eta if eta>=0 else '?'}s")
            else:
                log_progress(f"[{idx}/{n}] {rate:.1f} issues/s | ETA {eta if eta>=0 else '?'}s")
        heartbeat("issues", idx, n)
        d = get_issue_details(key)
        if not meets_resolved_filters(d, resolved_only, resolved_after, resolved_before):
            continue

        # Map attachments
        attachments = []
        for a in (d.get("attachments") or []):
            attachments.append({
                "FileName": a.get("filename"),
                "Url": a.get("content"),
                "Size": a.get("size")
            })

        # Map comments (support-only)
        kommentare = []
        for c in (d.get("support_comments") or []):
            kommentare.append({
                "CommentDate": c.get("created"),
                "Body": c.get("body"),
                "UserName": c.get("author"),
                "Attachments": []
            })

        # ticket_id should be int if possible (Jira's 'id' is numeric string)
        tid = d.get("id")
        if isinstance(tid, str) and tid.isdigit():
            try:
                ticket_id = int(tid)
            except Exception:
                ticket_id = tid
        else:
            ticket_id = tid or d.get("key")

        tickets.append({
            "ticket_id": ticket_id,
            "CategoryName": d.get("category"),
            "IssueDate": d.get("created"),
            "Subject": d.get("summary"),
            "Body": d.get("problem") or "",
            "Status": d.get("status"),
            "Url": d.get("url"),
            "Attachments": attachments,
            "kommentare": kommentare
        })

        total_comments += len(kommentare)
        total_ticket_attachments += len(attachments)
        # We are not extracting per-comment attachments from Jira; keep 0
        total_comment_attachments += 0

        time.sleep(0.05)  # be polite

    export_data = {
        "export_info": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_closed_tickets": len(tickets),
            "total_comments": total_comments,
            "total_ticket_attachments": total_ticket_attachments,
            "total_comment_attachments": total_comment_attachments,
            "export_duration_seconds": time.time() - start_time,
            "filter_criteria": filter_criteria or "",
            "api_base_url": JIRA_BASE_URL
        },
        "tickets": tickets
    }

    to_write = export_data
    if append and os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = None

        if isinstance(existing, dict) and isinstance(existing.get("tickets"), list):
            existing_ids = set(str((t or {}).get("ticket_id")) for t in (existing.get("tickets") or []) if isinstance(t, dict))
            new_unique = [t for t in tickets if str((t or {}).get("ticket_id")) not in existing_ids]

            # Recompute metrics for new_unique to avoid counting duplicates
            new_comments = sum(len(t.get("kommentare") or []) for t in new_unique)
            new_ticket_atts = sum(len(t.get("Attachments") or []) for t in new_unique)
            new_comment_atts = 0

            existing["tickets"].extend(new_unique)
            ex_info = existing.get("export_info") or {}
            ex_info["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
            ex_info["total_closed_tickets"] = len(existing["tickets"])
            ex_info["total_comments"] = (ex_info.get("total_comments") or 0) + new_comments
            ex_info["total_ticket_attachments"] = (ex_info.get("total_ticket_attachments") or 0) + new_ticket_atts
            ex_info["total_comment_attachments"] = (ex_info.get("total_comment_attachments") or 0) + new_comment_atts
            ex_info["export_duration_seconds"] = (ex_info.get("export_duration_seconds") or 0) + (time.time() - start_time)
            fc_existing = ex_info.get("filter_criteria") or ""
            ex_info["filter_criteria"] = (fc_existing + " | " if fc_existing else "") + (filter_criteria or "")
            ex_info["api_base_url"] = JIRA_BASE_URL
            existing["export_info"] = ex_info
            to_write = existing

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(to_write, f, ensure_ascii=False, indent=2)

            print(f"[OK] Appended {len(new_unique)} new tickets (deduped) to {out_path} (total now {len(existing['tickets'])})")
            print(f"[OK] New comments added: {new_comments}, ticket attachments added: {new_ticket_atts}")
            return
        elif isinstance(existing, list):
            # Existing file is a raw array of tickets
            existing_ids = set(str((t or {}).get("ticket_id")) for t in existing if isinstance(t, dict))
            new_unique = [t for t in tickets if str((t or {}).get("ticket_id")) not in existing_ids]
            combined = existing + new_unique
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(combined, f, ensure_ascii=False, indent=2)
            print(f"[OK] Appended {len(new_unique)} tickets to existing array file {out_path} (total now {len(combined)})")
            return
        # Fallback to overwrite if existing format is unexpected

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(to_write, f, ensure_ascii=False, indent=2)

    print(f"[OK] Exported {len(tickets)} tickets to {out_path}")
    print(f"[OK] Total comments: {total_comments}, ticket attachments: {total_ticket_attachments}, comment attachments: {total_comment_attachments}")

# ------------------------------
# 4️⃣  Ausführen
# ------------------------------
if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="Fetch Jira issues or a specific issue with details")
        parser.add_argument("--issue", "-i", help="Issue key, e.g., SUP-41210")
        parser.add_argument("--jql", default="project=SUP order by created ASC", help="JQL for listing issues")
        parser.add_argument("--limit", type=int, default=None, help="Max results for JQL search (omit to fetch ALL that match)")
        parser.add_argument("--resolved-only", action="store_true", help="Only include issues with statusCategory=Done")
        parser.add_argument("--resolved-after", type=str, help="Only include issues resolved on/after this date (YYYYMMDD or YYYY-MM-DD)")
        parser.add_argument("--resolved-before", type=str, help="Only include issues resolved on/before this date (YYYYMMDD or YYYY-MM-DD)")
        parser.add_argument("--export", "-o", help="Write JSON to this file using Jitbit-like schema (e.g., JIRA_relevante_Tickets.json)")
        parser.add_argument("--append", action="store_true", help="Append to existing export file and de-duplicate by ticket_id")
        parser.add_argument("--progress", action="store_true", help="Print progress while fetching")
        parser.add_argument("--detailed-log", action="store_true", help="Show detailed per-ticket output; otherwise with --progress only progress is shown")
        args = parser.parse_args()

        PROGRESS = bool(args.progress)
        DETAILED_LOG = bool(args.detailed_log)

        if args.issue:
            key = args.issue.strip()
            if args.export:
                fc = f"issue={key}"
                if args.resolved_only:
                    fc += " AND statusCategory=Done"
                if args.resolved_after:
                    fc += f' AND resolutiondate >= "{parse_resolved_after_arg(args.resolved_after)}"'
                if args.resolved_before:
                    fc += f' AND resolutiondate <= "{parse_resolved_after_arg(args.resolved_before)} 23:59"'
                export_jira_json([key], args.export, filter_criteria=fc, resolved_only=args.resolved_only, resolved_after=args.resolved_after, resolved_before=args.resolved_before, append=args.append)
            else:
                details = get_issue_details(key)
                print(f"1. {key}: {details['summary']} | Status: {details['status']} | Bearbeiter: {details['assignee']}")
                # Problem/Description preview (longer for single issue)
                problem_preview = (details.get('problem') or '').replace('\n', ' ')[:400]
                tail = '...' if len((details.get('problem') or '')) > 400 else ''
                print(f"   Problem: {problem_preview}{tail}")
                # Resolution info
                print(f"   Resolution: {details.get('resolution') or '-'} | Resolved at: {details.get('resolved') or '-'}")
                # Attachments
                print(f"   Attachments: {len(details.get('attachments') or [])}")
                # Support comments
                print(f"   Support comments: {len(details.get('support_comments') or [])}")
        else:
            # Require at least one of --limit or --resolved-after to be defined to avoid unbounded fetches
            if args.limit is None and not args.resolved_after:
                parser.error("Either --limit or --resolved-after must be provided. Aborting without starting the process.")

            # Validate date range if both bounds are provided
            if args.resolved_after and args.resolved_before:
                if parse_resolved_after_arg(args.resolved_after) > parse_resolved_after_arg(args.resolved_before):
                    parser.error("--resolved-after date must be on or before --resolved-before date.")

            built_jql = build_filtered_jql(args.jql, args.resolved_only, args.resolved_after, args.resolved_before)
            issues = get_first_issues(jql=built_jql, limit=args.limit)
            keys = [it.get("key") for it in issues if it and it.get("key")]
            if args.export:
                out = args.export or "JIRA_relevante_Tickets.json"
                limit_info = f"LIMIT {args.limit}" if args.limit is not None else "ALL"
                fc = f"JQL: {built_jql} {limit_info}"
                export_jira_json(keys, out_path=out, filter_criteria=fc, resolved_only=args.resolved_only, resolved_after=args.resolved_after, resolved_before=args.resolved_before, append=args.append)
            else:
                print(f"Gefundene Tickets: {len(issues)}")
                n = len(issues)
                reset_heartbeat()
                for i, issue in enumerate(issues, start=1):
                    if i == 1 or i % 10 == 0 or i == n:
                        if DETAILED_LOG:
                            log_progress(f"[{i}/{n}] Fetching details for {issue.get('key')}")
                        else:
                            log_progress(f"[{i}/{n}] Processing...")
                    heartbeat("details", i, n)
                    key = issue.get('key')
                    details = get_issue_details(key)
                    if DETAILED_LOG or not PROGRESS:
                        print(f"{i}. {key}: {details['summary']} | Status: {details['status']} | Bearbeiter: {details['assignee']}")
                        # Problem/Description preview
                        problem_preview = (details.get('problem') or '').replace('\n', ' ')[:200]
                        tail = '...' if len((details.get('problem') or '')) > 200 else ''
                        print(f"   Problem: {problem_preview}{tail}")
                        # Resolution info
                        print(f"   Resolution: {details.get('resolution') or '-'} | Resolved at: {details.get('resolved') or '-'}")
                        # Attachments
                        print(f"   Attachments: {len(details.get('attachments') or [])}")
                        # Support comments
                        print(f"   Support comments: {len(details.get('support_comments') or [])}")
    except requests.exceptions.Timeout:
        print("Zeitüberschreitung bei der Anfrage. Bitte Netzwerk/Jira-Verfügbarkeit prüfen.")
    except requests.exceptions.HTTPError as e:
        body = ""
        if getattr(e, "response", None) is not None:
            try:
                body = e.response.text[:500]
            except Exception:
                body = ""
        print(f"HTTP-Fehler: {e}. Antwortauszug: {body}")
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
