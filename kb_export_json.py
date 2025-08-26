import os
import re
import sys
import json
import time
import argparse
from urllib.parse import urljoin, urlparse

import requests

# Optional: load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# === Configuration / Auth ===

api_token = os.getenv("JITBIT_API_TOKEN", "").strip()
if not api_token:
    raise EnvironmentError("JITBIT_API_TOKEN ist nicht gesetzt. Bitte in der .env-Datei (JITBIT_API_TOKEN=...) oder als Umgebungsvariable definieren.")

# Basis-URL Ihrer Jitbit-Installation (inkl. /helpdesk)
jitbit_url = "https://support.4plan.de"

# Standard-Header (Token, GZip)
headers = {
    "Authorization": f"Bearer {api_token}",
    "Accept-Encoding": "gzip",
}

# === Helpers ===

def normalisiere_url(u: str) -> str:
    """Macht relative URLs absolut mithilfe von jitbit_url"""
    if not u or not isinstance(u, str):
        return ""
    u = u.strip()
    if not u:
        return ""
    try:
        parsed = urlparse(u)
        if parsed.scheme in ("http", "https"):
            return u
        return urljoin(jitbit_url + "/", u.lstrip("/"))
    except Exception:
        return u


def guess_filename_from_url(u: str) -> str:
    try:
        path = urlparse(u).path
        if not path:
            return ""
        name = path.split("/")[-1]
        return name or ""
    except Exception:
        return ""


def api_get(path_or_url: str, params=None, timeout=30, max_retries=5):
    """
    GET mit einfachem Retry & 429-Handling.
    Akzeptiert absolute URLs oder Pfade beginnend mit '/' relativ zu jitbit_url.
    """
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        url = path_or_url
    else:
        # Ensure we use /helpdesk/api/... paths
        url = urljoin(jitbit_url + "/", path_or_url.lstrip("/"))

    backoff = 5
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 429:
                wait_s = max(30, backoff)
                print(f"429 Too Many Requests: warte {wait_s}s (Versuch {attempt}/{max_retries}) ...")
                time.sleep(wait_s)
                backoff = min(backoff * 2, 120)
                continue
            if resp.status_code >= 500:
                wait_s = max(5, backoff)
                print(f"HTTP {resp.status_code}: Serverfehler, warte {wait_s}s (Versuch {attempt}/{max_retries}) ...")
                time.sleep(wait_s)
                backoff = min(backoff * 2, 60)
                continue
            return resp
        except requests.exceptions.RequestException as e:
            wait_s = max(3, backoff)
            print(f"Netzwerkfehler: {e}. Warte {wait_s}s (Versuch {attempt}/{max_retries}) ...")
            time.sleep(wait_s)
            backoff = min(backoff * 2, 60)

    raise RuntimeError(f"GET fehlgeschlagen nach {max_retries} Versuchen: {url}")


# === Attachment extraction from body (BBCode + HTML + plain URLs) ===

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
FILE_EXTS = IMAGE_EXTS.union({
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".7z", ".rar", ".txt", ".log", ".csv"
})
KEYWORDS = ("attach", "attachment", "download", "file", "upload", "uploads", "image", "img", "KB", "kb")


def _maybe_attachment_url(url_str: str) -> bool:
    if not url_str:
        return False
    try:
        p = urlparse(url_str)
        path = (p.path or "").lower()
        query = (p.query or "").lower()
        looks_like_file = any(path.endswith(ext) for ext in FILE_EXTS)
        contains_kw = any(k in path for k in (kw.lower() for kw in KEYWORDS)) or any(k in query for k in (kw.lower() for kw in KEYWORDS))
        return looks_like_file or contains_kw
    except Exception:
        return False


def extract_attachments_from_body(text: str):
    """
    Extrahiert potentielle Anhang-Links aus BBCode/HTML und nackten URLs.
    Rückgabe: Liste von Dicts: {FileName, Url, Size}
    """
    if not text or not isinstance(text, str):
        return []

    candidates = set()

    # 1) BBCode patterns
    # [img]URL[/img]
    for m in re.findall(r"\[img\](.*?)\[/img\]", text, flags=re.IGNORECASE | re.DOTALL):
        candidates.add(m.strip())
    # [url]URL[/url]
    for m in re.findall(r"\[url\](.*?)\[/url\]", text, flags=re.IGNORECASE | re.DOTALL):
        candidates.add(m.strip())
    # [url=URL]text[/url]
    for m in re.findall(r"\[url=(.+?)\](.*?)\[/url\]", text, flags=re.IGNORECASE | re.DOTALL):
        if isinstance(m, tuple) and len(m) >= 1:
            candidates.add(str(m[0]).strip())

    # 2) HTML href/src
    for m in re.findall(r'href=["\']([^"\']+)["\']', text, flags=re.IGNORECASE):
        candidates.add(m.strip())
    for m in re.findall(r'src=["\']([^"\']+)["\']', text, flags=re.IGNORECASE):
        candidates.add(m.strip())

    # 3) Plain URLs (http/https)
    for m in re.findall(r"(https?://[^\s\]\)]+)", text, flags=re.IGNORECASE):
        # strip trailing punctuation
        candidates.add(m.strip().rstrip(").,;\"'"))

    result = []
    seen = set()
    for c in candidates:
        if not c:
            continue
        # ignore mailto/javascript/hash
        l = c.lower()
        if l.startswith(("mailto:", "javascript:", "#")):
            continue
        full = normalisiere_url(c)
        if not _maybe_attachment_url(full):
            continue
        if full in seen:
            continue
        seen.add(full)
        result.append({
            "FileName": guess_filename_from_url(full),
            "Url": full,
            "Size": 0
        })
    return result


# === BBCode -> Markdown + Markdown -> Text ===

def bbcode_to_markdown(text: str) -> str:
    """
    Konservative Konvertierung häufiger BBCode-Tags zu Markdown.
    """
    if not text or not isinstance(text, str):
        return ""

    md = text
    md = md.replace("\r\n", "\n")

    # [b]bold[/b] -> **bold**
    md = re.sub(r"\[b\](.*?)\[/b\]", r"**\1**", md, flags=re.IGNORECASE | re.DOTALL)
    # [i]italic[/i] -> _italic_
    md = re.sub(r"\[i\](.*?)\[/i\]", r"_\1_", md, flags=re.IGNORECASE | re.DOTALL)
    # [u]underline[/u] -> <u>underline</u>
    md = re.sub(r"\[u\](.*?)\[/u\]", r"<u>\1</u>", md, flags=re.IGNORECASE | re.DOTALL)

    # [code]...[/code] -> ```...```
    def code_repl(m):
        inner = m.group(1).strip("\n")
        return f"\n```\n{inner}\n```\n"
    md = re.sub(r"\[code\](.*?)\[/code\]", code_repl, md, flags=re.IGNORECASE | re.DOTALL)

    # [quote]...[/quote] -> blockquote
    def quote_repl(m):
        inner = m.group(1).strip("\n")
        lines = inner.split("\n")
        lines = [f"> {ln}" if ln.strip() else ">" for ln in lines]
        return "\n" + "\n".join(lines) + "\n"
    md = re.sub(r"\[quote\](.*?)\[/quote\]", quote_repl, md, flags=re.IGNORECASE | re.DOTALL)

    # [img]url[/img] -> ![](url)
    def img_repl(m):
        url = normalisiere_url(m.group(1).strip())
        return f"![]({url})"
    md = re.sub(r"\[img\](.*?)\[/img\]", img_repl, md, flags=re.IGNORECASE | re.DOTALL)

    # [url]url[/url] -> <url>; [url=link]text[/url] -> [text](link)
    def url_plain_repl(m):
        url = normalisiere_url(m.group(1).strip())
        return f"<{url}>"
    md = re.sub(r"\[url\](.*?)\[/url\]", url_plain_repl, md, flags=re.IGNORECASE | re.DOTALL)

    def url_text_repl(m):
        link = normalisiere_url(m.group(1).strip())
        text = m.group(2).strip().replace("]", "\\]").replace(")", "\\)")
        return f"[{text}]({link})"
    md = re.sub(r"\[url=(.+?)\](.*?)\[/url\]", url_text_repl, md, flags=re.IGNORECASE | re.DOTALL)

    # Listen
    md = re.sub(r"\[\*\]\s*", r"- ", md, flags=re.IGNORECASE)
    md = re.sub(r"\[/?list\]", "", md, flags=re.IGNORECASE)

    # HTML line breaks
    md = re.sub(r"<br\s*/?>", "\n", md, flags=re.IGNORECASE)
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    md = re.sub(r"\n\s*\n\s*\n+", "\n\n", md)

    return md.strip()


def markdown_to_text(md: str) -> str:
    """
    Grobe Reduktion von Markdown/Inline-HTML zu Plaintext.
    Ziel: gut lesbarer Text ähnlich bereinige_html_text aus Tickets.
    """
    if not md or not isinstance(md, str):
        return ""

    text = md.replace("\r\n", "\n")

    # Codeblöcke ```...``` -> Inhalt behalten, Backticks entfernen
    text = re.sub(r"```(.*?)```", lambda m: "\n" + m.group(1).strip() + "\n", text, flags=re.DOTALL)

    # Blockquotes: führendes "> " entfernen
    text = re.sub(r"^[ \t]*> ?(.*)$", r"\1", text, flags=re.MULTILINE)

    # Bilder ![alt](url) -> url
    text = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", r"\1", text)

    # Links [text](url) -> "text (url)"
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

    # Inline-HTML <u>text</u> -> text
    text = re.sub(r"</?u>", "", text, flags=re.IGNORECASE)

    # Überschriften ###, ##, # -> einfache Zeilen
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)

    # Emphasis **text** und _text_ entfernen, Inhalt behalten
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"_(.*?)_", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)

    # Listenpunkte normalisieren: "-   " -> "- "
    text = re.sub(r"^-{1}\s+", "- ", text, flags=re.MULTILINE)

    # Mehrfache Leerzeichen/Zeilenumbrüche konsolidieren
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


# === API wrappers ===

def hole_kb_artikel_uebersicht(category_id: int | None = None):
    params = {}
    if isinstance(category_id, int):
        params["categoryId"] = category_id
    resp = api_get("/helpdesk/api/Articles", params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"/Articles -> HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def hole_kb_artikel_detail(article_id: int):
    resp = api_get(f"/helpdesk/api/Article/{int(article_id)}", timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"/Article/{article_id} -> HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def hole_kategorien():
    """
    Ruft alle Kategorien ab, die der aktuelle Benutzer sehen darf.
    Hinweis: Die Sichtbarkeit hängt von den Berechtigungen des Tokens ab.
    """
    resp = api_get("/helpdesk/api/categories", timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"/categories -> HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    # Manche Installationen liefern direkt eine Liste, andere ggf. ein Objekt
    if isinstance(data, list):
        return data
    return data.get("Categories") or []


def sammle_kb_artikel_vollstaendig(category_id: int | None):
    """
    Sammelt Artikel aus der Gesamtübersicht und zusätzlich je Kategorie,
    um sicherzugehen, dass keine Artikel durch Server-Limits/Filter fehlen.
    Gibt (articles, categories) zurück.
    """
    if isinstance(category_id, int):
        ov = hole_kb_artikel_uebersicht(category_id=category_id)
        arts = list(ov.get("Articles") or [])
        cats = list(ov.get("Categories") or [])
        return arts, cats

    # Ohne Kategorie-Filter: zunächst die Gesamtübersicht laden
    ov = hole_kb_artikel_uebersicht(category_id=None)
    articles = list(ov.get("Articles") or [])
    cats_from_overview = list(ov.get("Categories") or [])

    # Danach alle Kategorien separat abfragen und zusammenführen (deduplizieren)
    try:
        alle_kategorien = hole_kategorien()
    except Exception as e:
        print(f"[WARN] Konnte Kategorienliste nicht separat laden, nutze Kategorien aus Overview: {e}")
        alle_kategorien = cats_from_overview

    seen_ids = set()
    for a in articles:
        if isinstance(a, dict):
            aid = a.get("ArticleId")
            if isinstance(aid, int):
                seen_ids.add(aid)

    for cat in alle_kategorien or []:
        try:
            cid = cat.get("CategoryID")
        except AttributeError:
            cid = None
        if not isinstance(cid, int):
            continue
        try:
            sub = hole_kb_artikel_uebersicht(category_id=cid)
        except Exception as e:
            print(f"[WARN] Kategorienabruf fehlgeschlagen für CategoryID={cid}: {e}")
            continue
        for a in sub.get("Articles") or []:
            if not isinstance(a, dict):
                continue
            aid = a.get("ArticleId")
            if isinstance(aid, int) and aid not in seen_ids:
                articles.append(a)
                seen_ids.add(aid)

    categories = cats_from_overview or alle_kategorien or []
    return articles, categories


# === Orchestration (JSON export) ===

def exportiere_kb_json(category_id: int | None, first_n: int | None, out_path: str, auto_confirm: bool = False):
    print("=== JITBIT KNOWLEDGE BASE EXPORT (JSON) ===\n")
    print(f"Zieldatei: {out_path}")

    print("Sammle Artikel-Übersicht...")
    if category_id is not None:
        overview = hole_kb_artikel_uebersicht(category_id=category_id)
        articles = list(overview.get("Articles") or [])
        categories = list(overview.get("Categories") or [])
    else:
        print("Kein Kategorie-Filter angegeben. Lade Übersicht und iteriere zusätzlich über alle Kategorien für vollständige Abdeckung...")
        articles, categories = sammle_kb_artikel_vollstaendig(category_id=None)

    print(f"Gefundene Artikel (gesamt, dedupliziert): {len(articles)}")
    print(f"Kategorien (Begleitinfo): {len(categories)}")

    if first_n is not None and first_n > 0 and len(articles) > first_n:
        print(f"Begrenze auf die ersten {first_n} Artikel (Testlauf).")
        articles = articles[:first_n]

    if not auto_confirm:
        try:
            q = input(f"{len(articles)} Artikel sammeln und als JSON exportieren? (j/n): ").strip().lower()
            if q not in ("j", "ja", "y", "yes"):
                print("Abgebrochen.")
                return
        except KeyboardInterrupt:
            print("\nAbgebrochen.")
            return
    else:
        print(f"{len(articles)} Artikel exportieren? (j/n): j (via --yes)")

    exported_articles = []
    total_body_atts = 0
    total_api_atts = 0

    start = time.time()
    for i, art in enumerate(articles, start=1):
        if not isinstance(art, dict):
            continue
        aid = art.get("ArticleId")
        subj = art.get("Subject") or ""
        print(f"[{i}/{len(articles)}] Lade Artikel {aid} - {subj!r} ...", flush=True)

        try:
            detail = hole_kb_artikel_detail(aid)
        except Exception as e:
            print(f"  Fehler beim Laden von Article/{aid}: {e}")
            continue

        # Rohdaten
        body_raw = detail.get("Body") or ""
        body_md = bbcode_to_markdown(body_raw)
        body_text = markdown_to_text(body_md)

        # Attachments: API + Body-Extraktion
        api_atts = detail.get("Attachments") if detail.get("Attachments") is not None else (art.get("Attachments") or [])
        if not isinstance(api_atts, list):
            api_atts = []
        merged_atts = []
        seen = set()

        # API-Attachments
        for att in api_atts:
            if not isinstance(att, dict):
                continue
            url_val = (att.get("Url") or att.get("FileUrl") or att.get("DownloadUrl") or att.get("GoogleDriveUrl") or "")
            url_val = normalisiere_url(url_val)
            if not url_val or url_val in seen:
                continue
            merged_atts.append({
                "FileName": att.get("FileName") or guess_filename_from_url(url_val),
                "Url": url_val,
                "Size": att.get("FileSize") or att.get("Size") or 0,
            })
            seen.add(url_val)
        total_api_atts += len(merged_atts)

        # Body-Attachments
        body_atts = extract_attachments_from_body(body_raw)
        for att in body_atts:
            u = att.get("Url") or ""
            if not u or u in seen:
                continue
            merged_atts.append(att)
            seen.add(u)
        total_body_atts += max(0, len(merged_atts) - total_api_atts)

        # Artikelobjekt
        exported_articles.append({
            "ArticleId": detail.get("ArticleId") or art.get("ArticleId"),
            "Subject": detail.get("Subject") or art.get("Subject") or "",
            "Body": body_text,  # Plaintext (ähnlich tickets)
            "BodyMarkdown": body_md,  # zusätzlich zur Nachnutzung
            "ForTechsOnly": bool(detail.get("ForTechsOnly") if detail.get("ForTechsOnly") is not None else art.get("ForTechsOnly")),
            "CategoryID": detail.get("CategoryID") or art.get("CategoryID"),
            "CategoryName": detail.get("CategoryName") or art.get("CategoryName"),
            "TagString": detail.get("TagString") or art.get("TagString"),
            "Tags": detail.get("Tags") if detail.get("Tags") is not None else (art.get("Tags") or []),
            "UrlId": art.get("UrlId"),
            "DateCreated": detail.get("DateCreated") or art.get("DateCreated"),
            "LastUpdated": detail.get("LastUpdated") or art.get("LastUpdated"),
            "Url": normalisiere_url(detail.get("Url") or art.get("Url") or ""),
            "Attachments": merged_atts
        })

        # Gentle rate-limit
        time.sleep(0.12)

    duration = time.time() - start

    # Statistiken
    total_articles = len(exported_articles)
    total_attachments = sum(len(a.get("Attachments") or []) for a in exported_articles)

    export_data = {
        "export_info": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_articles": total_articles,
            "total_attachments": total_attachments,
            "api_base_url": jitbit_url,
            "category_filter": category_id,
            "limited_to_first_n": first_n,
            "export_duration_seconds": duration
        },
        "articles": exported_articles
    }

    # Schreiben
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        size = len(json.dumps(export_data, ensure_ascii=False, default=str))
        print(f"\n✅ JSON-Export erfolgreich: {out_path}")
        print(f"Artikel: {total_articles}, Attachments: {total_attachments}, Größe: {size/1024/1024:.2f} MB, Dauer: {duration:.1f}s")
        if exported_articles:
            beispiel = exported_articles[0]
            print("\nBeispiel-Artikel:")
            print(f"  ID: {beispiel['ArticleId']}")
            print(f"  Subject: {beispiel['Subject']}")
            print(f"  Attachments: {len(beispiel.get('Attachments') or [])}")
    except Exception as e:
        print(f"❌ Fehler beim JSON-Export: {e}")


# === CLI ===

def main():
    parser = argparse.ArgumentParser(description="Exportiert JitBit Knowledgebase als JSON-Datei.")
    parser.add_argument("--category-id", type=int, default=None, help="Nur eine bestimmte KB-Kategorie exportieren")
    parser.add_argument("--first", type=int, default=None, help="Nur die ersten N Artikel laden (Test)")
    parser.add_argument("--out", type=str, default="JitBit_Knowledgebase.json", help="Zieldatei (JSON)")
    parser.add_argument("--yes", action="store_true", help="Ohne Rückfrage ausführen")
    args = parser.parse_args()

    exportiere_kb_json(
        category_id=args.category_id,
        first_n=args.first,
        out_path=args.out,
        auto_confirm=bool(args.yes),
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
