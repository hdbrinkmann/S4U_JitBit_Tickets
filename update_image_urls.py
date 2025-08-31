#!/usr/bin/env python3
"""
Helper script to update image_urls in Ticket_Data_JIRA.JSON using attachment data
from jira_relevante_tickets.json without running expensive LLM calls.
"""

import json
from typing import List, Dict, Any

# Image file extensions (same as in process_tickets_with_llm.py)
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"]

def looks_like_image_url(url: str, filename: str = "") -> bool:
    """
    Determine if a URL points to an image based on filename and URL patterns.
    Enhanced version that works with both Jitbit and JIRA URLs.
    """
    # Check filename first if provided
    if filename:
        fn_lower = filename.lower()
        # If filename has image extension -> it's an image
        if any(fn_lower.endswith(ext) for ext in IMAGE_EXTS):
            return True
        # If filename has non-image extension -> it's not an image
        non_image_extensions = [".pdf", ".doc", ".docx", ".txt", ".xlsx", ".xls", ".zip", ".rar"]
        if any(fn_lower.endswith(ext) for ext in non_image_extensions):
            return False
    
    # For JIRA URLs, if we have filename info, trust it over URL patterns
    if "/rest/api/" in url and "/attachment/content/" in url:
        # For JIRA, if we have a filename and it's not a non-image extension, 
        # assume it could be an image
        return not filename or not any(filename.lower().endswith(ext) 
                                     for ext in [".pdf", ".doc", ".docx", ".txt", ".xlsx", ".xls", ".zip", ".rar"])
    
    # For Jitbit URLs, check the URL pattern
    if "/file/get/" in url or "/helpdesk/file/get/" in url:
        # Jitbit URLs might have image extensions in the URL
        url_lower = url.lower()
        if any(url_lower.endswith(ext) for ext in IMAGE_EXTS):
            return True
        # For Jitbit, if no extension in URL but we have filename info, use filename
        if filename:
            return any(filename.lower().endswith(ext) for ext in IMAGE_EXTS)
    
    return False

def extract_image_urls_from_attachments(attachments: List[Dict[str, Any]]) -> List[str]:
    """Extract image URLs from attachment list using enhanced image detection."""
    image_urls = []
    
    for attachment in attachments:
        url = attachment.get('Url', '')
        filename = attachment.get('FileName', '')
        
        if url and looks_like_image_url(url, filename):
            image_urls.append(url)
    
    return image_urls

def main():
    print("Loading JIRA ticket data with attachments...")
    
    # Read the original JIRA data
    try:
        with open('jira_relevante_tickets.json', 'r', encoding='utf-8') as f:
            jira_data = json.load(f)
    except FileNotFoundError:
        print("ERROR: jira_relevante_tickets.json not found!")
        return
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in jira_relevante_tickets.json: {e}")
        return

    # Read the processed ticket data
    try:
        with open('Ticket_Data_JIRA.JSON', 'r', encoding='utf-8') as f:
            processed_tickets = json.load(f)
    except FileNotFoundError:
        print("ERROR: Ticket_Data_JIRA.JSON not found!")
        return
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in Ticket_Data_JIRA.JSON: {e}")
        return

    # Create a mapping from ticket_id to attachments
    print("Creating ticket ID to attachments mapping...")
    attachment_map = {}
    for ticket in jira_data.get('tickets', []):
        ticket_id = ticket.get('ticket_id')
        attachments = ticket.get('Attachments', [])
        if ticket_id:
            attachment_map[ticket_id] = attachments
    
    print(f"Found {len(attachment_map)} tickets with potential attachments")
    
    # Remove S4U_ prefix from all tickets and update image URLs
    print("Processing tickets...")
    updated_count = 0
    total_images_found = 0
    prefix_removed_count = 0
    
    for processed_ticket in processed_tickets:
        # Remove "S4U_" prefix to match original ticket ID
        processed_id = processed_ticket.get('ticket_id', '')
        original_id = processed_id.replace('S4U_', '') if processed_id.startswith('S4U_') else processed_id
        
        # Update the ticket_id to remove S4U_ prefix for ALL tickets
        if processed_id.startswith('S4U_'):
            processed_ticket['ticket_id'] = original_id
            prefix_removed_count += 1
            print(f"  Removed S4U_ prefix: {processed_id} -> {original_id}")
        
        # Update image URLs if ticket has attachments
        if original_id in attachment_map:
            attachments = attachment_map[original_id]
            image_urls = extract_image_urls_from_attachments(attachments)
            
            if image_urls:
                processed_ticket['image_urls'] = image_urls
                updated_count += 1
                total_images_found += len(image_urls)
                print(f"  {original_id}: Found {len(image_urls)} image(s)")
                for img_url in image_urls:
                    # Find corresponding filename for this URL
                    filename = next((att.get('FileName', '') for att in attachments if att.get('Url') == img_url), '')
                    print(f"    - {filename} -> {img_url}")
    
    # Save updated data
    print(f"\nSaving updated data...")
    try:
        with open('Ticket_Data_JIRA.JSON', 'w', encoding='utf-8') as f:
            json.dump(processed_tickets, f, indent=2, ensure_ascii=False)
        print(f"✓ Successfully updated Ticket_Data_JIRA.JSON")
        print(f"✓ Updated {updated_count} tickets with {total_images_found} total images")
    except Exception as e:
        print(f"ERROR: Failed to save updated data: {e}")

if __name__ == '__main__':
    main()
