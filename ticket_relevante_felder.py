import requests
import json
import time
import re
import html
from urllib.parse import urljoin, urlparse
import argparse
import sys

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # Wenn python-dotenv nicht installiert ist, versuchen wir trotzdem die Umgebungsvariablen zu lesen
    pass

# API-Token aus .env lesen
api_token = os.getenv("JITBIT_API_TOKEN", "").strip()

if not api_token:
    raise EnvironmentError("JITBIT_API_TOKEN ist nicht gesetzt. Bitte in der .env-Datei (JITBIT_API_TOKEN=...) oder als Umgebungsvariable definieren.")

# URL Ihrer Jitbit-Installation
jitbit_url = 'https://support.4plan.de'

# Header mit API-Token  
headers = {
    'Authorization': f'Bearer {api_token}'
}

# Erlaubte Kategorien
ERLAUBTE_KATEGORIEN = ["Allgemeine Frage", "Fehlermeldung", "Sonstiges"]

def hole_alle_ticket_ids():
    """Sammelt alle verfügbaren echten TicketIDs mit Pagination"""
    print("Sammle alle verfügbaren Ticket-IDs mit Pagination...")
    
    alle_tickets = []
    offset = 0
    batch_size = 300
    batch_count = 0
    start_time = time.time()
    
    # Phase 1: Alle Tickets über Pagination sammeln
    while True:
        batch_count += 1
        print(f"Lade Batch {batch_count} (Tickets {offset + 1}-{offset + batch_size})...")
        
        params = {
            'count': batch_size,
            'offset': offset
        }
        
        try:
            response = requests.get(f'{jitbit_url}/helpdesk/api/Tickets', headers=headers, params=params, timeout=30)
            
            if response.status_code == 429:  # Rate limit exceeded
                print("Rate-Limit erreicht, warte 60 Sekunden...")
                time.sleep(60)
                continue
            elif response.status_code != 200:
                print(f"Fehler beim Laden von Batch {batch_count}: HTTP {response.status_code}")
                print(f"Response: {response.text[:200]}")
                break
            
            tickets = response.json()
            if not tickets or len(tickets) == 0:
                print("Keine weiteren Tickets gefunden - Pagination beendet.")
                break
            
            alle_tickets.extend(tickets)
            print(f"  → {len(tickets)} Tickets geladen (Gesamt: {len(alle_tickets)})")
            
            # Wenn weniger als batch_size Tickets zurückkommen, sind wir am Ende
            if len(tickets) < batch_size:
                print("Letzter Batch erreicht - alle Tickets geladen.")
                break
            
            offset += batch_size
            
            # Rate-Limiting berücksichtigen: max 90 Aufrufe pro Minute
            # Pause zwischen Batches für API-Schonung
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            print(f"Netzwerk-Fehler bei Batch {batch_count}: {e}")
            print("Warte 10 Sekunden und versuche es erneut...")
            time.sleep(10)
            continue
    
    batch_time = time.time() - start_time
    print(f"\n=== BATCH-LOADING ABGESCHLOSSEN ===")
    print(f"Geladene Batches: {batch_count}")
    print(f"Gesamte Tickets gefunden: {len(alle_tickets)}")
    print(f"Zeit für Batch-Loading: {batch_time:.1f} Sekunden")
    
    if not alle_tickets:
        print("Keine Tickets gefunden!")
        return []
    
    # Phase 2: Echte Ticket-IDs extrahieren
    print(f"\nExtrahiere echte Ticket-IDs aus {len(alle_tickets)} Tickets...")
    echte_ticket_ids = []
    fehler_count = 0
    
    for i, ticket in enumerate(alle_tickets):
        if i % 100 == 0 and i > 0:
            fortschritt = (i / len(alle_tickets)) * 100
            elapsed = time.time() - start_time
            avg_time = elapsed / i
            eta_seconds = (len(alle_tickets) - i) * avg_time
            eta_minutes = int(eta_seconds / 60)
            print(f"Fortschritt: {fortschritt:.1f}% - {i}/{len(alle_tickets)} - ETA: {eta_minutes}min")
        
        issue_id = ticket.get('IssueID')
        if issue_id:
            # Lade das Einzelticket um die echte TicketID zu bekommen
            einzelticket = hole_ticket_basis_daten(issue_id)
            if einzelticket:
                ticket_id = einzelticket.get('TicketID')
                if ticket_id:
                    echte_ticket_ids.append(ticket_id)
            else:
                fehler_count += 1
        
        # API schonen - Rate-Limiting beachten
        time.sleep(0.02)
    
    total_time = time.time() - start_time
    echte_ticket_ids.sort()
    
    print(f"\n=== TICKET-ID EXTRAKTION ABGESCHLOSSEN ===")
    print(f"Echte Ticket-IDs gefunden: {len(echte_ticket_ids)}")
    print(f"Fehler bei Extraktion: {fehler_count}")
    print(f"Gesamtdauer: {total_time:.1f} Sekunden ({total_time/60:.1f} Minuten)")
    if echte_ticket_ids:
        print(f"ID-Bereich: {min(echte_ticket_ids)} bis {max(echte_ticket_ids)}")
    
    return echte_ticket_ids

def hole_ticket_basis_daten(ticket_id):
    """Lädt die Basis-Daten eines Tickets"""
    url = f'{jitbit_url}/helpdesk/api/Ticket/{ticket_id}'
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return {'error': f'HTTP {response.status_code}', 'ticket_id': ticket_id}
    except Exception as e:
        return {'error': f'Exception: {str(e)}', 'ticket_id': ticket_id}

def hole_ticket_kommentare(ticket_id):
    """Lädt alle Kommentare/Konversation eines Tickets (mit Fallback-Endpoint)"""
    # Primär: Pfad-Variante
    url1 = f'{jitbit_url}/helpdesk/api/Comments/{ticket_id}'
    # Fallback: Query-Variante (manche Jitbit-Deployments erwarten dies)
    url2 = f'{jitbit_url}/helpdesk/api/Comments'
    try:
        resp = requests.get(url1, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # Wenn Liste und ggf. Inhalte vorhanden, zurückgeben
            if isinstance(data, list) and (len(data) > 0 or data == []):
                return data
        # Fallback 1: ticketId
        resp2 = requests.get(url2, headers=headers, params={'ticketId': ticket_id}, timeout=15)
        if resp2.status_code == 200:
            data2 = resp2.json()
            if isinstance(data2, list):
                return data2
        # Fallback 2: ticketid (andere Schreibweise)
        resp3 = requests.get(url2, headers=headers, params={'ticketid': ticket_id}, timeout=15)
        if resp3.status_code == 200:
            data3 = resp3.json()
            if isinstance(data3, list):
                return data3
        return []
    except Exception:
        return []

def hole_ticket_anhange(ticket_id):
    """Lädt alle Anhänge eines Tickets (mit Fallback-Endpoint)"""
    # Primär: Pfad-Variante
    url1 = f'{jitbit_url}/helpdesk/api/Attachments/{ticket_id}'
    # Fallback: Query-Variante (manche Jitbit-Deployments erwarten dies)
    url2 = f'{jitbit_url}/helpdesk/api/Attachments'
    try:
        resp = requests.get(url1, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            # Wenn Liste und ggf. Inhalte vorhanden, zurückgeben
            if isinstance(data, list) and (len(data) > 0 or data == []):
                return data
        # Fallback 1: ticketId
        resp2 = requests.get(url2, headers=headers, params={'ticketId': ticket_id}, timeout=15)
        if resp2.status_code == 200:
            data2 = resp2.json()
            if isinstance(data2, list):
                return data2
        # Fallback 2: ticketid (andere Schreibweise)
        resp3 = requests.get(url2, headers=headers, params={'ticketid': ticket_id}, timeout=15)
        if resp3.status_code == 200:
            data3 = resp3.json()
            if isinstance(data3, list):
                return data3
        return []
    except Exception:
        return []

def hole_kommentar_anhange(comment_id):
    """Lädt alle Anhänge eines Kommentars (separate API-Abfrage nach commentId)"""
    url = f'{jitbit_url}/helpdesk/api/Attachments'
    try:
        # Verschiedene Schreibweisen für den Parameternamen testen
        for key in ('commentId', 'commentID', 'commentid', 'CommentId', 'CommentID'):
            resp = requests.get(url, headers=headers, params={key: comment_id}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
        return []
    except Exception:
        return []

def bereinige_html_text(html_content):
    """Entfernt HTML-Tags und bereinigt den Text"""
    if not html_content or not isinstance(html_content, str):
        return ""
    
    # Entferne <!--html--> Marker
    text = html_content.replace('<!--html-->', '')
    
    # Ersetze <br>, <br/>, <br /> mit Zeilenumbrüchen
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    
    # Ersetze <div> und </div> mit Zeilenumbrüchen
    text = re.sub(r'</?div[^>]*>', '\n', text, flags=re.IGNORECASE)
    
    # Ersetze <p> und </p> mit Zeilenumbrüchen  
    text = re.sub(r'</?p[^>]*>', '\n', text, flags=re.IGNORECASE)
    
    # Entferne alle anderen HTML-Tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # HTML-Entities decodieren
    text = html.unescape(text)
    
    # Mehrfache Leerzeichen durch einzelne ersetzen
    text = re.sub(r' +', ' ', text)
    
    # Mehrfache Zeilenumbrüche reduzieren
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # Führende und nachfolgende Leerzeichen entfernen
    text = text.strip()
    
    return text

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
        # relative Pfade -> absolut machen
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

def extrahiere_attachments_aus_html(html_content: str):
    """
    Extrahiert potentielle Anhang-Links aus HTML (href/src).
    Viele Jitbit-Instanzen liefern Attachments nicht über /api/Attachments,
    sondern als Links/Images in Body/Comments.
    """
    if not html_content or not isinstance(html_content, str):
        return []

    candidates = set()
    try:
        # href und src extrahieren
        for m in re.findall(r'href=["\']([^"\']+)["\']', html_content, flags=re.IGNORECASE):
            candidates.add(m)
        for m in re.findall(r'src=["\']([^"\']+)["\']', html_content, flags=re.IGNORECASE):
            candidates.add(m)
    except Exception:
        pass

    # Heuristik: nur Links behalten, die wie Dateien/Attachments aussehen
    exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".zip", ".7z", ".rar", ".txt", ".log", ".csv"}
    keywords = ("attach", "attachment", "download", "file", "upload", "uploads", "image", "img")

    result = []
    seen = set()
    for c in candidates:
        if not c:
            continue
        lc = c.lower()
        if lc.startswith(("mailto:", "javascript:", "#")):
            continue
        full = normalisiere_url(c)
        pl = urlparse(full)
        # Filter nach Anzeichen für Datei/Attachment
        looks_like_file = any(pl.path.lower().endswith(ext) for ext in exts)
        contains_kw = any(k in pl.path.lower() for k in keywords) or any(k in (pl.query or "").lower() for k in keywords)
        if looks_like_file or contains_kw:
            if full not in seen:
                seen.add(full)
                result.append({
                    "FileName": guess_filename_from_url(full),
                    "Url": full,
                    "Size": 0
                })
    return result

def extrahiere_relevante_daten(ticket_id):
    """Extrahiert nur die relevanten Felder für geschlossene Tickets"""
    
    # Basis-Daten laden
    basis_daten = hole_ticket_basis_daten(ticket_id)
    if not basis_daten:
        return None
    
    # Nur geschlossene Tickets berücksichtigen
    status = basis_daten.get('Status', '')
    if status != 'Geschlossen':
        return None
    
    # Nur erlaubte Kategorien berücksichtigen
    category_name = basis_daten.get('CategoryName', '')
    if category_name not in ERLAUBTE_KATEGORIEN:
        return None
    
    # Kommentare laden
    kommentare_raw = hole_ticket_kommentare(ticket_id)
    
    # Anhänge laden
    anhange_raw = hole_ticket_anhange(ticket_id)
    
    # Ticket-Anhänge URLs extrahieren (API + aus HTML-Body)
    ticket_attachments = []
    seen_ticket_urls = set()

    # 1) API-Resultate (falls vorhanden)
    if anhange_raw:
        for attachment in anhange_raw:
            if isinstance(attachment, dict):
                url_val = (attachment.get('Url') or attachment.get('FileUrl') or attachment.get('DownloadUrl') or attachment.get('Link') or '')
                url_val = normalisiere_url(url_val)
                if url_val and url_val not in seen_ticket_urls:
                    att_data = {
                        "FileName": attachment.get('FileName', '') or guess_filename_from_url(url_val),
                        "Url": url_val,
                        "Size": attachment.get('Size', 0)
                    }
                    ticket_attachments.append(att_data)
                    seen_ticket_urls.add(url_val)

    # 2) HTML-Links im Ticket-Body (häufige Quelle für Anhänge bei Jitbit)
    html_ticket_atts = extrahiere_attachments_aus_html(basis_daten.get('Body', ''))
    for att in html_ticket_atts:
        u = att.get("Url") or ""
        if u and u not in seen_ticket_urls:
            ticket_attachments.append(att)
            seen_ticket_urls.add(u)
    
    # Kommentare filtern und relevante Felder extrahieren
    relevante_kommentare = []
    if kommentare_raw:
        for comment in kommentare_raw:
            if isinstance(comment, dict):
                # Kommentar-Anhänge verarbeiten
                comment_attachments = []
                # Manche Jitbit-Deployments liefern KEINE eingebetteten Attachments in Comments.
                # Dann müssen sie separat über /Attachments?commentId=... geladen werden.
                attachments_field = comment.get('Attachments')
                if not isinstance(attachments_field, list):
                    attachments_field = []
                
                comment_id = (comment.get('CommentId') or comment.get('CommentID') or
                              comment.get('Id') or comment.get('ID'))
                attachments_count_hint = (comment.get('AttachmentsCount') or comment.get('AttachmentCount') or
                                          comment.get('FilesCount') or comment.get('Files') or 0)
                
                # Falls keine eingebetteten Anhänge vorhanden sind, via API pro Kommentar nachladen
                if (not attachments_field) and comment_id:
                    fetched_atts = hole_kommentar_anhange(comment_id)
                    if isinstance(fetched_atts, list):
                        attachments_field = fetched_atts
                
                if isinstance(attachments_field, list) and attachments_field:
                    for att in attachments_field:
                        if isinstance(att, dict):
                            comment_attachments.append({
                                "FileName": att.get('FileName', ''),
                                "Url": (att.get('Url') or att.get('FileUrl') or att.get('DownloadUrl') or att.get('Link') or ''),
                                "Size": att.get('Size', 0)
                            })

                # 3) HTML-Links im Kommentar-Body als zusätzliche Anhänge
                html_comment_atts = extrahiere_attachments_aus_html(comment.get('Body', ''))
                if html_comment_atts:
                    seen_urls = set(a.get("Url") for a in comment_attachments if isinstance(a, dict))
                    for hatt in html_comment_atts:
                        u = hatt.get("Url") or ""
                        if u and u not in seen_urls:
                            comment_attachments.append(hatt)
                            seen_urls.add(u)
                
                kommentar_data = {
                    "CommentDate": (comment.get('CommentDate') or comment.get('Date') or ''),
                    "Body": bereinige_html_text(comment.get('Body', '')),
                    "UserName": comment.get('UserName', ''),
                    "Attachments": comment_attachments
                }
                relevante_kommentare.append(kommentar_data)
    
    # Nur relevante Felder extrahieren
    relevante_daten = {
        "ticket_id": ticket_id,
        "CategoryName": basis_daten.get('CategoryName', ''),
        "IssueDate": basis_daten.get('IssueDate', ''),
        "Subject": basis_daten.get('Subject', ''),
        "Body": bereinige_html_text(basis_daten.get('Body', '')),
        "Status": status,
        "Url": basis_daten.get('Url', ''),
        "Attachments": ticket_attachments,
        "kommentare": relevante_kommentare
    }
    
    return relevante_daten

def debug_attachments(ticket_id):
    """Diagnose: prüft Ticket- und Kommentar-Anhänge direkt über die API und protokolliert Details"""
    print(f"=== DEBUG ANHÄNGE FÜR TICKET {ticket_id} ===")
    try:
        basis = hole_ticket_basis_daten(ticket_id)
        echte_ticket_id = ticket_id
        if isinstance(basis, dict):
            echte_ticket_id = basis.get('TicketID') or ticket_id
        if echte_ticket_id != ticket_id:
            print(f"Hinweis: übergebene ID {ticket_id} ist vermutlich IssueID; verwende TicketID {echte_ticket_id}")
    except Exception as e:
        print(f"Fehler beim Laden der Basisdaten: {e}")
        echte_ticket_id = ticket_id

    # Basisdaten-Details
    if isinstance(basis, dict):
        print(f"\nBasisdaten Keys: {list(basis.keys())[:20]}{' ...' if len(basis.keys())>20 else ''}")
        print(f"Basis TicketID={basis.get('TicketID')}, IssueID={basis.get('IssueID')}, Id={basis.get('Id')}, Url={basis.get('Url')}")
        print(f"HasAttachments Flags (falls vorhanden): HasAttachments={basis.get('HasAttachments')}, AttachmentsCount={basis.get('AttachmentsCount')}, AttachmentCount={basis.get('AttachmentCount')}, FilesCount={basis.get('FilesCount')}, Files={basis.get('Files')}")

    # Ticket-Level Attachments
    print("\n-- Ticket-Anhänge --")
    try:
        url1 = f'{jitbit_url}/helpdesk/api/Attachments/{echte_ticket_id}'
        r1 = requests.get(url1, headers=headers, timeout=15)
        print(f"GET {url1} -> HTTP {r1.status_code}, len(body)={len(r1.text)}")
        if r1.status_code == 200:
            data1 = r1.json()
            print(f"Anhänge (Pfad-Variante): {len(data1) if isinstance(data1, list) else 'keine Liste'}")
            if isinstance(data1, list) and data1:
                print(f"Beispiel Keys: {list(data1[0].keys())}")
        else:
            print(f"Antwort (Snippet): {r1.text[:300].strip()}")
    except Exception as e:
        print(f"Fehler bei Attachments/{echte_ticket_id}: {e}")

    try:
        url2 = f'{jitbit_url}/helpdesk/api/Attachments'
        r2 = requests.get(url2, headers=headers, params={'ticketId': echte_ticket_id}, timeout=15)
        print(f"GET {url2}?ticketId={echte_ticket_id} -> HTTP {r2.status_code}, len(body)={len(r2.text)}")
        if r2.status_code == 200:
            data2 = r2.json()
            print(f"Anhänge (Query-Variante ticketId): {len(data2) if isinstance(data2, list) else 'keine Liste'}")
            if isinstance(data2, list) and data2:
                print(f"Beispiel Keys: {list(data2[0].keys())}")
        else:
            print(f"Antwort (Snippet): {r2.text[:300].strip()}")
    except Exception as e:
        print(f"Fehler bei Attachments?ticketId: {e}")

    # Kommentare und Kommentar-Anhänge
    print("\n-- Kommentar-Anhänge --")
    comments = hole_ticket_kommentare(echte_ticket_id) or []
    print(f"Kommentare geladen: {len(comments)}")
    if isinstance(comments, list) and comments:
        print(f"Kommentar[0] Keys: {list(comments[0].keys())[:20]}{' ...' if len(comments[0].keys())>20 else ''}")
        print(f"Kommentar[0] Flags: HasAttachments={comments[0].get('HasAttachments')}, AttachmentsCount={comments[0].get('AttachmentsCount')}, AttachmentCount={comments[0].get('AttachmentCount')}, FilesCount={comments[0].get('FilesCount')}, Files={comments[0].get('Files')}")
    for idx, c in enumerate(comments[:10]):
        if not isinstance(c, dict):
            continue
        cid = (c.get('CommentId') or c.get('CommentID') or c.get('Id') or c.get('ID'))
        embedded = c.get('Attachments')
        count_hint = (c.get('AttachmentsCount') or c.get('AttachmentCount') or c.get('FilesCount') or c.get('Files') or 0)
        print(f"- Kommentar #{idx+1}: cid={cid}, embedded_type={type(embedded).__name__}, embedded_count={len(embedded) if isinstance(embedded, list) else 'n/a'}, hint={count_hint}")
        if cid:
            fetched = hole_kommentar_anhange(cid) or []
            print(f"  -> Nachgeladen über /Attachments?commentId={cid}: {len(fetched)} Anhänge")
            if isinstance(fetched, list) and fetched:
                print(f"     Beispiel Keys: {list(fetched[0].keys())}")

def exportiere_relevante_tickets(scope_mode=None, first_n=None, start_ticket_id=None, auto_confirm=False):
    """Hauptfunktion: Exportiert alle geschlossenen Tickets mit relevanten Feldern"""
    print("=== JITBIT GESCHLOSSENE TICKETS - RELEVANTE FELDER EXPORT ===\n")
    
    # 1. Sammle alle Ticket-IDs
    ticket_ids = hole_alle_ticket_ids()
    if not ticket_ids:
        print("Keine Ticket-IDs gefunden!")
        return
    
    print(f"\nGefunden: {len(ticket_ids)} Tickets")
    print(f"Bereich: {min(ticket_ids)} bis {max(ticket_ids)}")
    
    # Benutzer fragen (mit Wiederholung bei ungültiger Eingabe)
    zu_pruefende_ids = None

    # Non-interactive scope selection via CLI flags
    if scope_mode in ('all', 'first', 'start'):
        if scope_mode == 'all':
            zu_pruefende_ids = ticket_ids
        elif scope_mode == 'first':
            n = first_n if isinstance(first_n, int) and first_n > 0 else 10
            zu_pruefende_ids = ticket_ids[:min(n, len(ticket_ids))]
        elif scope_mode == 'start':
            if isinstance(start_ticket_id, int):
                if start_ticket_id in ticket_ids:
                    start_index = ticket_ids.index(start_ticket_id)
                    zu_pruefende_ids = ticket_ids[start_index:]
                    print(f"Beginne ab Ticket-ID {start_ticket_id} (Position {start_index + 1} von {len(ticket_ids)})")
                    print(f"Verbleibende Tickets zu prüfen: {len(zu_pruefende_ids)}")
                else:
                    hohere_ids = [tid for tid in ticket_ids if tid >= start_ticket_id]
                    if hohere_ids:
                        naechste_id = min(hohere_ids)
                        start_index = ticket_ids.index(naechste_id)
                        zu_pruefende_ids = ticket_ids[start_index:]
                        print(f"Ticket-ID {start_ticket_id} nicht gefunden.")
                        print(f"Beginne stattdessen ab nächsthöherer ID: {naechste_id} (Position {start_index + 1} von {len(ticket_ids)})")
                        print(f"Verbleibende Tickets zu prüfen: {len(zu_pruefende_ids)}")
            if zu_pruefende_ids is None:
                print("Start-ID ungültig – falle auf interaktive Auswahl zurück.")

    if zu_pruefende_ids is None:
        while zu_pruefende_ids is None:
            print("\nOptionen:")
            print(f"1) Alle {len(ticket_ids)} Tickets prüfen (nur geschlossene werden exportiert)")
            print("2) Nur eine Teilmenge prüfen")
            print("3) Test: Nur die ersten 10 Tickets")
            print("4) Ab bestimmter Ticket-ID beginnen")
            print("\nHinweis: Erst nach Auswahl (1–4) und Bestätigung mit 'j' wird die Datei 'JitBit_relevante_Tickets.json' erstellt.")
            print("Tipp: Für einen schnellen Test wählen Sie Option 3.")
            
            wahl = input("\nIhre Wahl (1-4): ").strip()
            
            if wahl == '1':
                zu_pruefende_ids = ticket_ids
            elif wahl == '2':
                while True:
                    anzahl = input(f"Wie viele Tickets prüfen (max {len(ticket_ids)})? ")
                    if anzahl.isdigit():
                        anzahl = min(int(anzahl), len(ticket_ids))
                        zu_pruefende_ids = ticket_ids[:anzahl]
                        break
                    else:
                        print("Ungültige Eingabe. Bitte eine Zahl eingeben.")
            elif wahl == '3':
                zu_pruefende_ids = ticket_ids[:10]
            elif wahl == '4':
                # Ab bestimmter Ticket-ID beginnen
                print(f"\nVerfügbare Ticket-IDs: {min(ticket_ids)} bis {max(ticket_ids)}")
                
                while True:
                    start_ticket_id = input("Ab welcher Ticket-ID beginnen? ").strip()
                    
                    if start_ticket_id.isdigit():
                        start_ticket_id = int(start_ticket_id)
                        
                        # Finde den Index der Start-Ticket-ID
                        if start_ticket_id in ticket_ids:
                            start_index = ticket_ids.index(start_ticket_id)
                            zu_pruefende_ids = ticket_ids[start_index:]
                            print(f"Beginne ab Ticket-ID {start_ticket_id} (Position {start_index + 1} von {len(ticket_ids)})")
                            print(f"Verbleibende Tickets zu prüfen: {len(zu_pruefende_ids)}")
                            break
                        else:
                            # Ticket-ID nicht gefunden - finde die nächsthöhere
                            hohere_ids = [tid for tid in ticket_ids if tid >= start_ticket_id]
                            if hohere_ids:
                                naechste_id = min(hohere_ids)
                                start_index = ticket_ids.index(naechste_id)
                                zu_pruefende_ids = ticket_ids[start_index:]
                                print(f"Ticket-ID {start_ticket_id} nicht gefunden.")
                                print(f"Beginne stattdessen ab nächsthöherer ID: {naechste_id} (Position {start_index + 1} von {len(ticket_ids)})")
                                print(f"Verbleibende Tickets zu prüfen: {len(zu_pruefende_ids)}")
                                break
                            else:
                                print(f"Keine Ticket-ID >= {start_ticket_id} gefunden! Bitte eine andere ID eingeben.")
                    else:
                        print("Ungültige Ticket-ID. Bitte eine Zahl eingeben.")
            else:
                print("Ungültige Wahl. Bitte 1, 2, 3 oder 4 eingeben.")
    
    print(f"\nPrüfe {len(zu_pruefende_ids)} Tickets auf geschlossene Tickets...")
    print(f"(Filter: Status='Geschlossen' UND Kategorie in {ERLAUBTE_KATEGORIEN})")
    
    # Zeitschätzung
    geschaetzte_zeit = len(zu_pruefende_ids) * 0.3
    print(f"Geschätzte Dauer: {geschaetzte_zeit/60:.1f} Minuten")
    
    if not auto_confirm:
        if input("Fortfahren? (j/n): ").lower() not in ['j', 'ja']:
            print("Abgebrochen.")
            return
    else:
        print("Fortfahren? (j/n): j (via --yes)")
    
    # 2. Lade relevante Daten nur für geschlossene Tickets mit detaillierter Fehlersammlung
    geschlossene_tickets = []
    nicht_geschlossen = 0
    fehler_details = {
        'http_fehler': [],
        'kategorien_ausschluss': [],
        'api_exceptions': [],
        'unbekannte_fehler': [],
        'status_nicht_geschlossen': []
    }
    start_time = time.time()
    
    for i, ticket_id in enumerate(zu_pruefende_ids):
        if i % 10 == 0:
            fortschritt = (i / len(zu_pruefende_ids)) * 100
            elapsed_time = time.time() - start_time
            if i > 0:
                avg_time = elapsed_time / i
                eta_seconds = (len(zu_pruefende_ids) - i) * avg_time
                eta_minutes = int(eta_seconds / 60)
                print(f"Fortschritt: {fortschritt:.1f}% - Ticket {i+1}/{len(zu_pruefende_ids)} (ID: {ticket_id}) - Geschlossen: {len(geschlossene_tickets)} - ETA: {eta_minutes}min")
        
        # Detaillierte Analyse des Tickets
        basis_daten = hole_ticket_basis_daten(ticket_id)
        
        # Prüfe auf Fehler beim Laden der Basis-Daten
        if isinstance(basis_daten, dict) and 'error' in basis_daten:
            error_msg = basis_daten['error']
            if 'HTTP' in error_msg:
                fehler_details['http_fehler'].append({'ticket_id': ticket_id, 'error': error_msg})
            elif 'Exception' in error_msg:
                fehler_details['api_exceptions'].append({'ticket_id': ticket_id, 'error': error_msg})
            else:
                fehler_details['unbekannte_fehler'].append({'ticket_id': ticket_id, 'error': error_msg})
            continue
        elif not basis_daten:
            fehler_details['unbekannte_fehler'].append({'ticket_id': ticket_id, 'error': 'Keine Daten erhalten'})
            continue
        
        # Prüfe Status
        status = basis_daten.get('Status', '')
        if status != 'Geschlossen':
            fehler_details['status_nicht_geschlossen'].append({'ticket_id': ticket_id, 'status': status})
            continue
        
        # Prüfe Kategorie
        category_name = basis_daten.get('CategoryName', '')
        if category_name not in ERLAUBTE_KATEGORIEN:
            fehler_details['kategorien_ausschluss'].append({'ticket_id': ticket_id, 'kategorie': category_name})
            continue
        
        # Wenn wir hier ankommen, ist es ein gültiges Ticket
        relevante_daten = extrahiere_relevante_daten(ticket_id)
        if relevante_daten:
            geschlossene_tickets.append(relevante_daten)
        else:
            fehler_details['unbekannte_fehler'].append({'ticket_id': ticket_id, 'error': 'Extraktion fehlgeschlagen trotz gültiger Basis-Daten'})
        
        # API schonen
        time.sleep(0.1)
    
    total_time = time.time() - start_time
    
    # Fehlerstatistiken berechnen
    gesamt_fehler = (len(fehler_details['http_fehler']) + 
                     len(fehler_details['api_exceptions']) + 
                     len(fehler_details['unbekannte_fehler']) + 
                     len(fehler_details['kategorien_ausschluss']) + 
                     len(fehler_details['status_nicht_geschlossen']))
    
    print(f"\n=== LADE-ERGEBNIS ===")
    print(f"Geschlossene Tickets gefunden: {len(geschlossene_tickets)}")
    print(f"Gesamt-Fehler: {gesamt_fehler}")
    print(f"Dauer: {total_time:.1f} Sekunden ({total_time/60:.1f} Minuten)")
    
    print(f"\n=== FEHLER-DETAILS ===")
    print(f"HTTP-Fehler: {len(fehler_details['http_fehler'])}")
    print(f"API-Exceptions: {len(fehler_details['api_exceptions'])}")
    print(f"Status nicht geschlossen: {len(fehler_details['status_nicht_geschlossen'])}")
    print(f"Kategorien ausgeschlossen: {len(fehler_details['kategorien_ausschluss'])}")
    print(f"Unbekannte Fehler: {len(fehler_details['unbekannte_fehler'])}")
    
    # Beispiele für häufigste Fehlertypen zeigen
    if fehler_details['http_fehler']:
        print(f"\nBeispiele HTTP-Fehler (erste 3):")
        for beispiel in fehler_details['http_fehler'][:3]:
            print(f"  Ticket {beispiel['ticket_id']}: {beispiel['error']}")
    
    if fehler_details['status_nicht_geschlossen']:
        status_counts = {}
        for item in fehler_details['status_nicht_geschlossen']:
            status = item['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        print(f"\nStatus-Verteilung (nicht geschlossen):")
        for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {status}: {count} Tickets")
    
    if fehler_details['kategorien_ausschluss']:
        kategorie_counts = {}
        for item in fehler_details['kategorien_ausschluss']:
            kategorie = item['kategorie']
            kategorie_counts[kategorie] = kategorie_counts.get(kategorie, 0) + 1
        print(f"\nKategorien (ausgeschlossen):")
        for kategorie, count in sorted(kategorie_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {kategorie}: {count} Tickets")
    
    if not geschlossene_tickets:
        print("Keine geschlossenen Tickets gefunden!")
        return
    
    # 3. Datenstatistiken
    total_comments = sum(len(t.get('kommentare', [])) for t in geschlossene_tickets)
    total_attachments = sum(len(t.get('Attachments', [])) for t in geschlossene_tickets)
    total_comment_attachments = sum(
        sum(len(c.get('Attachments', [])) for c in t.get('kommentare', []))
        for t in geschlossene_tickets
    )
    
    print(f"\n=== DATENSTATISTIKEN ===")
    print(f"Geschlossene Tickets: {len(geschlossene_tickets)}")
    print(f"Gesamte Kommentare: {total_comments}")
    print(f"Ticket-Anhänge: {total_attachments}")
    print(f"Kommentar-Anhänge: {total_comment_attachments}")
    
    # 4. JSON-Export
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    filename = f'JitBit_relevante_Tickets.json'
    
    print(f"\nExportiere nach: {filename}")
    
    export_data = {
        'export_info': {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_closed_tickets': len(geschlossene_tickets),
            'total_comments': total_comments,
            'total_ticket_attachments': total_attachments,
            'total_comment_attachments': total_comment_attachments,
            'export_duration_seconds': total_time,
            'filter_criteria': f'Nur geschlossene Tickets mit Kategorien: {ERLAUBTE_KATEGORIEN}',
            'api_base_url': jitbit_url
        },
        'tickets': geschlossene_tickets
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        
        file_size = len(json.dumps(export_data, default=str))
        print(f"✅ Export erfolgreich!")
        print(f"Dateigröße: {file_size:,} Zeichen ({file_size/1024/1024:.1f} MB)")
        
        # Beispiel-Ticket anzeigen
        if geschlossene_tickets:
            beispiel = geschlossene_tickets[0]
            print(f"\nBeispiel-Ticket (ID {beispiel['ticket_id']}):")
            print(f"  Subject: {beispiel['Subject']}")
            print(f"  Kategorie: {beispiel['CategoryName']}")
            print(f"  Kommentare: {len(beispiel['kommentare'])}")
            print(f"  Anhänge: {len(beispiel['Attachments'])}")
        
    except Exception as e:
        print(f"❌ Fehler beim JSON-Export: {e}")

# Test-Funktion für einzelne Tickets
def teste_einzelticket(ticket_id):
    """Testet die Extraktion für ein einzelnes Ticket"""
    print(f"=== TEST RELEVANTE FELDER FÜR TICKET {ticket_id} ===\n")
    
    # Echte TicketID auflösen, falls eine IssueID übergeben wurde
    basis = hole_ticket_basis_daten(ticket_id)
    echte_ticket_id = ticket_id
    if isinstance(basis, dict):
        echte_ticket_id = basis.get('TicketID') or ticket_id
    if echte_ticket_id != ticket_id:
        print(f"Hinweis: übergebene ID {ticket_id} ist vermutlich IssueID; verwende TicketID {echte_ticket_id} für Kommentare/Anhänge.")
    daten = extrahiere_relevante_daten(echte_ticket_id)
    
    if daten:
        print("✅ Geschlossenes Ticket gefunden!")
        print(f"Subject: {daten['Subject']}")
        print(f"Kategorie: {daten['CategoryName']}")
        print(f"Status: {daten['Status']}")
        print(f"Kommentare: {len(daten['kommentare'])}")
        total_comment_atts = sum(len((c.get('Attachments') or [])) for c in daten['kommentare'])
        print(f"Anhänge (Ticket): {len(daten['Attachments'])}")
        print(f"Anhänge (Kommentare): {total_comment_atts}")
        
        # JSON-Export
        filename = f'ticket_{ticket_id}_relevant.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(daten, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n✅ Exportiert nach: {filename}")
        
        return daten
    else:
        print("ℹ️ Ticket ist nicht geschlossen oder konnte nicht geladen werden.")
        return None

if __name__ == "__main__":
    print("=== JITBIT RELEVANTE FELDER EXPORT ===")
    print("Filter: Nur geschlossene Tickets")
    print("Felder: ticket_id, CategoryName, IssueDate, Subject, Body, Attachments, Status, kommentare\n")
    
    try:
        # CLI non-interactive flags
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--all', dest='cli_all', action='store_true', help='Alle Tickets prüfen (geschlossene exportieren)')
        parser.add_argument('--first', dest='cli_first', type=int, help='Nur die ersten N Tickets prüfen')
        parser.add_argument('--start-id', dest='cli_start_id', type=int, help='Ab bestimmter Ticket-ID beginnen')
        parser.add_argument('--yes', dest='cli_yes', action='store_true', help='Bestätigt die Ausführung ohne Rückfrage')
        args, _unknown = parser.parse_known_args()

        # If any non-interactive scope flag is provided, run export directly and exit
        if args.cli_all or (args.cli_first is not None) or (args.cli_start_id is not None):
            if args.cli_all:
                exportiere_relevante_tickets(scope_mode='all', auto_confirm=args.cli_yes)
            elif args.cli_first is not None:
                exportiere_relevante_tickets(scope_mode='first', first_n=args.cli_first, auto_confirm=args.cli_yes)
            elif args.cli_start_id is not None:
                exportiere_relevante_tickets(scope_mode='start', start_ticket_id=args.cli_start_id, auto_confirm=args.cli_yes)
            raise SystemExit(0)

        print("Optionen:")
        print("1) Alle verfügbaren Tickets prüfen und geschlossene exportieren")
        print("2) Einzelnes Ticket testen (ID 23480)")
        print("3) Einzelnes Ticket testen (ID 22596)")
        print("4) Benutzerdefinierte Ticket-ID testen")
        print("5) DEBUG: Anhänge prüfen (Ticket 23480)")
        print("6) DEBUG: Anhänge prüfen (benutzerdefinierte Ticket-ID)")
        print("\nHinweis: Nach Option 1 folgt eine zweite Auswahl (1–4) für den Umfang.")
        print("Wählen Sie dort 1 für alle Tickets oder 3 für einen schnellen Test, und bestätigen Sie anschließend mit 'j', damit die JSON-Datei geschrieben wird.")
        
        wahl = input("Ihre Wahl (1-6): ").strip()
        
        if wahl == '1':
            exportiere_relevante_tickets()
        elif wahl == '2':
            teste_einzelticket(23480)
        elif wahl == '3':
            teste_einzelticket(22596)
        elif wahl == '4':
            ticket_id = input("Ticket-ID eingeben: ").strip()
            if ticket_id.isdigit():
                teste_einzelticket(int(ticket_id))
            else:
                print("Ungültige Ticket-ID.")
        elif wahl == '5':
            debug_attachments(23480)
        elif wahl == '6':
            ticket_id = input("Ticket-ID für Debug eingeben: ").strip()
            if ticket_id.isdigit():
                debug_attachments(int(ticket_id))
            else:
                print("Ungültige Ticket-ID.")
        else:
            print("Ungültige Wahl.")
            
    except KeyboardInterrupt:
        print("\n\nVorgang abgebrochen.")
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
