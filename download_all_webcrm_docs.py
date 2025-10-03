#!/usr/bin/env python3
"""
Script to download all PDF, DOCX, and DOC files from webcrm API
"""

import os
import requests
from dotenv import load_dotenv
from pathlib import Path
import time

def get_access_token(api_key):
    """Get access token using API key"""
    
    base_url = "https://api.webcrm.com"
    url = f"{base_url}/Auth/ApiLogin"
    
    print("\n🔐 Authenticating with webcrm API...")
    
    data = {
        'authCode': api_key
    }
    
    try:
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            token_response = response.json()
            access_token = token_response.get('AccessToken')
            
            if access_token:
                print(f"   ✅ Authentication successful!")
                return access_token
                
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    return None

def download_all_documents(access_token):
    """Download all PDF, DOCX, and DOC files"""
    
    base_url = "https://api.webcrm.com"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # File extensions to download
    target_extensions = {'.pdf', '.docx', '.doc', '.rtf'}
    
    # Folders to download from
    target_folders = {'Contracts', 'Data Processing Agreement', 'Sales Terms'}
    
    print(f"\n📄 Fetching all documents...")
    print(f"   Target extensions: {', '.join(target_extensions)}")
    print(f"   Target folders: {', '.join(target_folders)}")
    
    # Create main download directory
    download_dir = Path("webcrm_documents")
    download_dir.mkdir(exist_ok=True)
    
    # Create subdirectories by type
    pdf_dir = download_dir / "pdf"
    word_dir = download_dir / "word"
    pdf_dir.mkdir(exist_ok=True)
    word_dir.mkdir(exist_ok=True)
    
    # Statistics
    target_docs = []
    skipped_count = 0
    page = 1
    
    # First pass: collect all target documents
    print("\n🔍 Phase 1: Scanning for PDF and Word documents...")
    
    try:
        while True:
            url = f"{base_url}/Documents?Page={page}&Size=100"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                documents = response.json()
                
                if isinstance(documents, list) and len(documents) > 0:
                    page_targets = 0
                    
                    for doc in documents:
                        file_ext = doc.get('DocumentFileExtension', '')
                        if file_ext:
                            file_ext = f".{file_ext.lower()}" if not file_ext.startswith('.') else file_ext.lower()
                        
                        folder = doc.get('DocumentFolder', '')
                        
                        # Check both extension and folder
                        if file_ext in target_extensions and folder in target_folders:
                            target_docs.append(doc)
                            page_targets += 1
                        else:
                            skipped_count += 1
                    
                    print(f"   📄 Page {page}: {len(documents)} total, {page_targets} to download")
                    
                    if len(documents) < 100:
                        break
                    page += 1
                else:
                    break
            else:
                print(f"   ❌ Error on page {page}: {response.status_code}")
                break
        
        print(f"\n   ✅ Found {len(target_docs)} documents to download")
        print(f"   ⏭️  Skipped {skipped_count} other files")
        
        # Second pass: download all target documents
        print(f"\n📥 Phase 2: Downloading {len(target_docs)} documents...")
        print("=" * 60)
        
        downloaded = 0
        failed = 0
        log_entries = []
        
        for i, doc in enumerate(target_docs, 1):
            doc_id = doc.get('DocumentId', 'N/A')
            doc_name = doc.get('DocumentFileName', f'document_{doc_id}')
            doc_ext = doc.get('DocumentFileExtension', '').lower()
            doc_folder = doc.get('DocumentFolder', 'Unknown')
            doc_entity_type = doc.get('DocumentLinkedEntityType', 'N/A')
            doc_org_id = doc.get('DocumentOrganisationId', 'N/A')
            
            # Sanitize filename
            safe_name = "".join(c for c in doc_name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
            if not safe_name:
                safe_name = f"document_{doc_id}.{doc_ext}"
            
            # Determine target directory
            if doc_ext == 'pdf':
                target_dir = pdf_dir
            else:
                target_dir = word_dir
            
            # Create unique filename if duplicate
            file_path = target_dir / safe_name
            counter = 1
            while file_path.exists():
                name_parts = safe_name.rsplit('.', 1)
                if len(name_parts) == 2:
                    file_path = target_dir / f"{name_parts[0]}_{counter}.{name_parts[1]}"
                else:
                    file_path = target_dir / f"{safe_name}_{counter}"
                counter += 1
            
            # Download the file
            download_url = f"{base_url}/Documents/{doc_id}/Download"
            
            try:
                file_response = requests.get(download_url, headers=headers, timeout=30)
                
                if file_response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(file_response.content)
                    
                    actual_size = len(file_response.content)
                    downloaded += 1
                    
                    log_entry = f"✅ {i}/{len(target_docs)}: {safe_name} ({actual_size:,} bytes)"
                    print(log_entry)
                    
                    log_entries.append({
                        'id': doc_id,
                        'filename': safe_name,
                        'size': actual_size,
                        'folder': doc_folder,
                        'linked_to': doc_entity_type,
                        'org_id': doc_org_id,
                        'path': str(file_path)
                    })
                    
                    # Rate limiting - don't exceed 250 requests per minute
                    if i % 200 == 0:
                        print(f"   ⏸️  Pausing for rate limit (30 seconds)...")
                        time.sleep(30)
                    
                else:
                    failed += 1
                    print(f"❌ {i}/{len(target_docs)}: {safe_name} - Download failed: {file_response.status_code}")
                    
            except Exception as e:
                failed += 1
                print(f"❌ {i}/{len(target_docs)}: {safe_name} - Error: {str(e)}")
        
        # Create summary log
        summary_path = download_dir / "DOWNLOAD_LOG.txt"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write("WebCRM Documents Download Log\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Total documents scanned: {len(target_docs) + skipped_count}\n")
            f.write(f"Documents downloaded: {downloaded}\n")
            f.write(f"Download failures: {failed}\n")
            f.write(f"Skipped (other formats): {skipped_count}\n\n")
            f.write("=" * 60 + "\n\n")
            
            for entry in log_entries:
                f.write(f"ID: {entry['id']}\n")
                f.write(f"File: {entry['filename']}\n")
                f.write(f"Size: {entry['size']:,} bytes\n")
                f.write(f"Folder: {entry['folder']}\n")
                f.write(f"Linked to: {entry['linked_to']}\n")
                f.write(f"Organisation: {entry['org_id']}\n")
                f.write(f"Path: {entry['path']}\n")
                f.write("\n")
        
        print("\n" + "=" * 60)
        print(f"📊 DOWNLOAD COMPLETE!")
        print(f"   ✅ Downloaded: {downloaded} files")
        print(f"   ❌ Failed: {failed} files")
        print(f"   📁 Location: {download_dir}/")
        print(f"      - PDFs: {pdf_dir}/")
        print(f"      - Word docs: {word_dir}/")
        print(f"   📝 Log: {summary_path}")
        print("=" * 60)
        
        return downloaded, failed
                    
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    return 0, 0

def main():
    """Main function"""
    
    # Load environment variables
    load_dotenv()
    
    api_key = os.getenv('WEBCRM_API_KEY')
    
    if not api_key:
        print("❌ Error: WEBCRM_API_KEY not found in .env file")
        return
    
    print(f"✓ API Key loaded: {api_key[:8]}...{api_key[-4:]}")
    
    # Get access token
    access_token = get_access_token(api_key)
    
    if not access_token:
        print("\n❌ Could not authenticate")
        return
    
    # Download all target documents
    downloaded, failed = download_all_documents(access_token)
    
    print("\n" + "=" * 60)
    if downloaded > 0:
        print(f"✅ Successfully downloaded {downloaded} documents")
        print(f"   Check webcrm_documents/ directory")
    else:
        print("⚠️  No documents were downloaded")
    print("=" * 60)

if __name__ == "__main__":
    print("=" * 60)
    print("WebCRM Documents Bulk Downloader")
    print("Downloading: PDF, DOCX, DOC, RTF files")
    print("From folders: Contracts, Data Processing Agreement, Sales Terms")
    print("=" * 60)
    
    main()
