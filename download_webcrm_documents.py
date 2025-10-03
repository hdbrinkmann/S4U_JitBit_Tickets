#!/usr/bin/env python3
"""
Script to download first 10 documents from webcrm API to inspect them
"""

import os
import requests
from dotenv import load_dotenv
from pathlib import Path

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

def download_documents(access_token, count=10):
    """Download first N documents"""
    
    base_url = "https://api.webcrm.com"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    print(f"\n📄 Fetching first {count} documents metadata...")
    
    # Get first page of documents
    url = f"{base_url}/Documents?Page=1&Size={count}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            documents = response.json()
            
            if isinstance(documents, list):
                print(f"   ✅ Retrieved {len(documents)} documents metadata")
                
                # Create downloads directory
                download_dir = Path("webcrm_documents_sample")
                download_dir.mkdir(exist_ok=True)
                
                print(f"\n📥 Downloading documents to: {download_dir}/")
                print("=" * 60)
                
                for i, doc in enumerate(documents[:count], 1):
                    doc_id = doc.get('DocumentId', 'N/A')
                    doc_name = doc.get('DocumentFileName', f'document_{doc_id}')
                    doc_desc = doc.get('DocumentDescription', 'N/A')
                    doc_size = doc.get('DocumentFileSize', 0)
                    doc_folder = doc.get('DocumentFolder', 'N/A')
                    doc_entity_type = doc.get('DocumentLinkedEntityType', 'N/A')
                    doc_entity_id = doc.get('DocumentEntityId', 'N/A')
                    doc_org_id = doc.get('DocumentOrganisationId', 'N/A')
                    created_at = doc.get('DocumentCreatedAt', 'N/A')
                    
                    print(f"\n{i}. Document ID: {doc_id}")
                    print(f"   File: {doc_name}")
                    print(f"   Description: {doc_desc}")
                    print(f"   Size: {doc_size} bytes")
                    print(f"   Folder: {doc_folder}")
                    print(f"   Linked to: {doc_entity_type} (ID: {doc_entity_id})")
                    print(f"   Organisation ID: {doc_org_id}")
                    print(f"   Created: {created_at}")
                    
                    # Download the actual file
                    download_url = f"{base_url}/Documents/{doc_id}/Download"
                    
                    try:
                        file_response = requests.get(download_url, headers=headers, timeout=30)
                        
                        if file_response.status_code == 200:
                            # Save file
                            file_path = download_dir / f"{i:02d}_{doc_name}"
                            
                            with open(file_path, 'wb') as f:
                                f.write(file_response.content)
                            
                            actual_size = len(file_response.content)
                            print(f"   ✅ Downloaded: {actual_size} bytes -> {file_path}")
                            
                            # Check content type
                            content_type = file_response.headers.get('Content-Type', 'N/A')
                            print(f"   Content-Type: {content_type}")
                            
                        else:
                            print(f"   ❌ Download failed: {file_response.status_code}")
                            
                    except Exception as e:
                        print(f"   ❌ Download error: {str(e)}")
                
                print("\n" + "=" * 60)
                print(f"✅ Downloaded {count} documents to: {download_dir}/")
                
                # Create summary file
                summary_path = download_dir / "SUMMARY.txt"
                with open(summary_path, 'w') as f:
                    f.write("WebCRM Documents Summary\n")
                    f.write("=" * 60 + "\n\n")
                    for i, doc in enumerate(documents[:count], 1):
                        f.write(f"{i}. ID: {doc.get('DocumentId')}\n")
                        f.write(f"   File: {doc.get('DocumentFileName')}\n")
                        f.write(f"   Description: {doc.get('DocumentDescription')}\n")
                        f.write(f"   Folder: {doc.get('DocumentFolder')}\n")
                        f.write(f"   Linked to: {doc.get('DocumentLinkedEntityType')} (ID: {doc.get('DocumentEntityId')})\n")
                        f.write(f"   Organisation: {doc.get('DocumentOrganisationId')}\n")
                        f.write(f"   Created: {doc.get('DocumentCreatedAt')}\n")
                        f.write("\n")
                
                print(f"📝 Summary saved to: {summary_path}")
                return len(documents)
                    
            else:
                print(f"   Unexpected response format: {type(documents)}")
                
        else:
            print(f"   ❌ Error: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    return 0

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
    
    # Download first 10 documents
    downloaded = download_documents(access_token, count=10)
    
    print("\n" + "=" * 60)
    if downloaded > 0:
        print(f"✅ Successfully downloaded {downloaded} documents")
        print("   Check webcrm_documents_sample/ directory for files")
    else:
        print("⚠️  Could not download documents")
    print("=" * 60)

if __name__ == "__main__":
    print("=" * 60)
    print("WebCRM Documents Downloader")
    print("=" * 60)
    
    main()
