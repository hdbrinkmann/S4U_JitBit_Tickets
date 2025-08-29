import os
import base64
import requests

# ------------------------------
# 1️⃣  Konfiguration
# ------------------------------
JIRA_EMAIL = os.getenv("JIRA_EMAIL")          # deine Atlassian‑E‑Mail
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")  # das erzeugte API‑Token


JIRA_BASE_URL = "https://timeplan.atlassian.net"  # ohne /rest/…

if not JIRA_EMAIL or not JIRA_API_TOKEN:
    raise RuntimeError("Bitte JIRA_EMAIL und JIRA_API_TOKEN setzen.")

# ------------------------------
# 2️⃣  Header erzeugen
# ------------------------------
basic_auth = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {basic_auth}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

# ------------------------------
# 3️⃣  Alle Issues holen (wie oben)
# ------------------------------
def get_all_issues(jql: str = "order by created ASC"):
    start_at = 0
    max_results = 5
    all_issues = []

    while True:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": "summary,status,assignee"
        }
        resp = requests.get(
            f"{JIRA_BASE_URL}/rest/api/3/search",
            headers=HEADERS,
            params=params
        )
        resp.raise_for_status()
        data = resp.json()

        issues = data.get("issues", [])
        all_issues.extend(issues)

        if len(issues) < max_results:
            break
        start_at += max_results

    return all_issues

# ------------------------------
# 4️⃣  Ausführen
# ------------------------------
if __name__ == "__main__":
    tickets = get_all_issues(jql="project=SUP")
    print(f"Gefundene Tickets: {len(tickets)}")
