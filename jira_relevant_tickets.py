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
from datetime import datetime, timezone

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
    raise ValueError("resolved-after must be YYYYMMDD or YYYY-MM-DD")

def build_filtered_jql(base_jql: str, resolved_only: bool, resolved_after: str) -> str:
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

def meets_resolved_filters(details: dict, resolved_only: bool, resolved_after: str) -> bool:
    if resolved_only and not details.get("resolved"):
        return False
    if resolved_after:
        cutoff = parse_resolved_after_arg(resolved_after)
        cutoff_dt = datetime.fromisoformat(cutoff + "T00:00:00+00:00")
        rdt = iso_to_datetime(details.get("resolved") or "")
        if not rdt or rdt < cutoff_dt:
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
def get_first_issues(jql: str = "order by created ASC", limit: int = 5):
    """
    Fetch only the first 'limit' issues that match the given JQL.
    Avoids long-running pagination and uses a request timeout.
    """
    params = {
        "jql": jql,
        "startAt": 0,
        "maxResults": limit,
        "fields": "summary,status,assignee,description,attachment,resolution,resolutiondate"
    }
    print(f"Requesting first {limit} issues with JQL: {jql}")
    resp = SESSION.get(
        f"{JIRA_BASE_URL}/rest/api/3/search",
        params=params,
        timeout=TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("issues", [])

# Utility: export Jira issues to the same JSON schema as Jitbit exporter
def export_jira_json(issue_keys, out_path="JIRA_relevante_Tickets.json", filter_criteria=None, resolved_only=False, resolved_after=None):
    start_time = time.time()
    tickets = []
    total_comments = 0
    total_ticket_attachments = 0
    total_comment_attachments = 0

    for key in issue_keys:
        d = get_issue_details(key)
        if not meets_resolved_filters(d, resolved_only, resolved_after):
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

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

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
        parser.add_argument("--limit", type=int, default=5, help="Max results for JQL search")
        parser.add_argument("--resolved-only", action="store_true", help="Only include issues with statusCategory=Done")
        parser.add_argument("--resolved-after", type=str, help="Only include issues resolved on/after this date (YYYYMMDD or YYYY-MM-DD)")
        parser.add_argument("--export", "-o", help="Write JSON to this file using Jitbit-like schema (e.g., JIRA_relevante_Tickets.json)")
        args = parser.parse_args()

        if args.issue:
            key = args.issue.strip()
            if args.export:
                fc = f"issue={key}"
                if args.resolved_only:
                    fc += " AND statusCategory=Done"
                if args.resolved_after:
                    fc += f' AND resolutiondate >= "{parse_resolved_after_arg(args.resolved_after)}"'
                export_jira_json([key], args.export, filter_criteria=fc, resolved_only=args.resolved_only, resolved_after=args.resolved_after)
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
            built_jql = build_filtered_jql(args.jql, args.resolved_only, args.resolved_after)
            issues = get_first_issues(jql=built_jql, limit=args.limit)
            keys = [it.get("key") for it in issues if it and it.get("key")]
            if args.export:
                out = args.export or "JIRA_relevante_Tickets.json"
                fc = f"JQL: {built_jql} LIMIT {args.limit}"
                export_jira_json(keys, out_path=out, filter_criteria=fc, resolved_only=args.resolved_only, resolved_after=args.resolved_after)
            else:
                print(f"Gefundene Tickets: {len(issues)}")
                for i, issue in enumerate(issues, start=1):
                    key = issue.get('key')
                    details = get_issue_details(key)
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
