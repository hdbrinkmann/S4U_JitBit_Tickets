import requests
import json
import time

# API-Token
api_token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOjQsImFkZCI6IjI1MkQ2N0M4MDkzNEE5NTlDMEUxQzRDMTZDNDlFQUExNEU5NTVFN0EyQjc5Q0YxMzNDRkM4NTA0MjU0MkY4RjUifQ.Tw_dFNCqB3wU_zDFDIw9XwXPoF9kQM8asc235pnP0yo'

# URL Ihrer Jitbit-Installation
jitbit_url = 'https://support.4plan.de'

# Header mit API-Token  
headers = {
    'Authorization': f'Bearer {api_token}'
}

def hole_alle_ticket_ids():
    """Sammelt alle verfügbaren echten TicketIDs"""
    print("Sammle alle verfügbaren Ticket-IDs...")
    
    response = requests.get(f'{jitbit_url}/helpdesk/api/Tickets', headers=headers, params={'count': 300})
    
    if response.status_code == 200:
        tickets = response.json()
        echte_ticket_ids = []
        
        print(f"Analysiere {len(tickets)} Tickets aus der Listen-API...")
        
        for i, ticket in enumerate(tickets):
            if i % 50 == 0:
                print(f"Fortschritt: {i}/{len(tickets)}")
            
            issue_id = ticket.get('IssueID')
            if issue_id:
                # Lade das Einzelticket um die echte TicketID zu bekommen
                einzelticket = hole_ticket_basis_daten(issue_id)
                if einzelticket:
                    ticket_id = einzelticket.get('TicketID')
                    if ticket_id:
                        echte_ticket_ids.append(ticket_id)
            
            time.sleep(0.02)  # API schonen
        
        echte_ticket_ids.sort()
        print(f"Gefundene Ticket-IDs: {len(echte_ticket_ids)}")
        return echte_ticket_ids
    else:
        print(f"Fehler beim Laden der Ticket-Liste: {response.status_code}")
        return []

def hole_ticket_basis_daten(ticket_id):
    """Lädt die Basis-Daten eines Tickets"""
    url = f'{jitbit_url}/helpdesk/api/Ticket/{ticket_id}'
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except:
        return None

def hole_ticket_kommentare(ticket_id):
    """Lädt alle Kommentare/Konversation eines Tickets"""
    url = f'{jitbit_url}/helpdesk/api/Comments/{ticket_id}'
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except:
        return []

def hole_ticket_anhange(ticket_id):
    """Lädt alle Anhänge eines Tickets"""
    url = f'{jitbit_url}/helpdesk/api/Attachments/{ticket_id}'
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return []
    except:
        return []

def sammle_vollstaendige_ticket_daten(ticket_id):
    """Sammelt alle verfügbaren Daten für ein Ticket"""
    basis_daten = hole_ticket_basis_daten(ticket_id)
    if not basis_daten:
        return None
    
    kommentare = hole_ticket_kommentare(ticket_id)
    anhange = hole_ticket_anhange(ticket_id)
    
    return {
        'ticket_id': ticket_id,
        'basis_daten': basis_daten,
        'kommentare': kommentare,
        'anhange': anhange,
        'export_timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }

def exportiere_alle_tickets():
    """Hauptfunktion: Exportiert alle Tickets mit vollständigen Daten"""
    print("=== JITBIT ALLE TICKETS VOLLSTÄNDIG EXPORTIEREN ===\n")
    
    # 1. Sammle alle Ticket-IDs
    ticket_ids = hole_alle_ticket_ids()
    if not ticket_ids:
        print("Keine Ticket-IDs gefunden!")
        return
    
    print(f"\nGefunden: {len(ticket_ids)} Tickets")
    print(f"Bereich: {min(ticket_ids)} bis {max(ticket_ids)}")
    
    # Benutzer fragen
    print("\nOptionen:")
    print(f"1) Alle {len(ticket_ids)} Tickets vollständig exportieren")
    print("2) Nur eine Teilmenge exportieren")
    print("3) Test: Nur die ersten 5 Tickets")
    
    wahl = input("\nIhre Wahl (1-3): ").strip()
    
    if wahl == '1':
        zu_exportierende_ids = ticket_ids
    elif wahl == '2':
        anzahl = input(f"Wie viele Tickets exportieren (max {len(ticket_ids)})? ")
        if anzahl.isdigit():
            anzahl = min(int(anzahl), len(ticket_ids))
            zu_exportierende_ids = ticket_ids[:anzahl]
        else:
            print("Ungültige Eingabe.")
            return
    elif wahl == '3':
        zu_exportierende_ids = ticket_ids[:5]
    else:
        print("Ungültige Wahl.")
        return
    
    print(f"\nExportiere {len(zu_exportierende_ids)} Tickets...")
    
    # Zeitschätzung
    geschaetzte_zeit = len(zu_exportierende_ids) * 0.5  # ~0.5 Sek pro Ticket
    print(f"Geschätzte Dauer: {geschaetzte_zeit/60:.1f} Minuten")
    
    if input("Fortfahren? (j/n): ").lower() not in ['j', 'ja']:
        print("Abgebrochen.")
        return
    
    # 2. Lade alle Ticket-Daten
    alle_tickets_daten = []
    fehler_count = 0
    start_time = time.time()
    
    for i, ticket_id in enumerate(zu_exportierende_ids):
        if i % 10 == 0:
            fortschritt = (i / len(zu_exportierende_ids)) * 100
            elapsed_time = time.time() - start_time
            if i > 0:
                avg_time = elapsed_time / i
                eta_seconds = (len(zu_exportierende_ids) - i) * avg_time
                eta_minutes = int(eta_seconds / 60)
                print(f"Fortschritt: {fortschritt:.1f}% - Ticket {i+1}/{len(zu_exportierende_ids)} (ID: {ticket_id}) - Geladen: {len(alle_tickets_daten)} - ETA: {eta_minutes}min")
        
        ticket_daten = sammle_vollstaendige_ticket_daten(ticket_id)
        
        if ticket_daten:
            alle_tickets_daten.append(ticket_daten)
        else:
            fehler_count += 1
        
        # API schonen
        time.sleep(0.1)
    
    total_time = time.time() - start_time
    
    print(f"\n=== LADE-ERGEBNIS ===")
    print(f"Erfolgreich geladen: {len(alle_tickets_daten)}")
    print(f"Fehler: {fehler_count}")
    print(f"Dauer: {total_time:.1f} Sekunden ({total_time/60:.1f} Minuten)")
    
    if not alle_tickets_daten:
        print("Keine Daten zum Exportieren!")
        return
    
    # 3. Datenstatistiken
    total_comments = sum(len(t.get('kommentare', [])) for t in alle_tickets_daten)
    total_attachments = sum(len(t.get('anhange', [])) for t in alle_tickets_daten)
    
    print(f"\n=== DATENSTATISTIKEN ===")
    print(f"Tickets: {len(alle_tickets_daten)}")
    print(f"Gesamte Kommentare: {total_comments}")
    print(f"Gesamte Anhänge: {total_attachments}")
    
    # 4. JSON-Export
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    filename = f'jitbit_alle_tickets_vollstaendig_{timestamp}.json'
    
    print(f"\nExportiere nach: {filename}")
    
    export_data = {
        'export_info': {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_tickets': len(alle_tickets_daten),
            'total_comments': total_comments,
            'total_attachments': total_attachments,
            'export_duration_seconds': total_time,
            'api_base_url': jitbit_url
        },
        'tickets': alle_tickets_daten
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
        
        file_size = len(json.dumps(export_data, default=str))
        print(f"✅ Export erfolgreich!")
        print(f"Dateigröße: {file_size:,} Zeichen ({file_size/1024/1024:.1f} MB)")
        
        # Beispiel-Ticket anzeigen
        if alle_tickets_daten:
            beispiel = alle_tickets_daten[0]
            print(f"\nBeispiel-Ticket (ID {beispiel['ticket_id']}):")
            print(f"  Subject: {beispiel['basis_daten'].get('Subject', 'N/A')}")
            print(f"  Status: {beispiel['basis_daten'].get('Status', 'N/A')}")
            print(f"  Kommentare: {len(beispiel.get('kommentare', []))}")
            print(f"  Anhänge: {len(beispiel.get('anhange', []))}")
        
    except Exception as e:
        print(f"❌ Fehler beim JSON-Export: {e}")

if __name__ == "__main__":
    try:
        exportiere_alle_tickets()
    except KeyboardInterrupt:
        print("\n\nVorgang durch Benutzer abgebrochen.")
    except Exception as e:
        print(f"Unerwarteter Fehler: {e}")
