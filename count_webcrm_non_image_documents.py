#!/usr/bin/env python3
"""
Script to count non-image documents from webcrm API
"""

import os
import requests
from dotenv import load_dotenv

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

def count_non_image_documents(access_token):
    """Count non-image documents"""
    
    base_url = "https://api.webcrm.com"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Image file extensions to exclude
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tif', '.tiff'}
    
    print(f"\n📄 Fetching all documents (excluding images)...")
    print(f"   Image extensions to exclude: {', '.join(image_extensions)}")
    
    all_documents = []
    image_documents = []
    page = 1
    
    try:
        while True:
            url = f"{base_url}/Documents?Page={page}&Size=100"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                documents = response.json()
                
                if isinstance(documents, list) and len(documents) > 0:
                    # Filter documents
                    page_images = 0
                    page_non_images = 0
                    
                    for doc in documents:
                        file_ext = doc.get('DocumentFileExtension', '')
                        if file_ext:
                            file_ext = f".{file_ext.lower()}" if not file_ext.startswith('.') else file_ext.lower()
                        
                        if file_ext in image_extensions:
                            image_documents.append(doc)
                            page_images += 1
                        else:
                            all_documents.append(doc)
                            page_non_images += 1
                    
                    print(f"   📄 Page {page}: {len(documents)} total ({page_images} images, {page_non_images} non-images)")
                    
                    if len(documents) < 100:
                        break
                    page += 1
                else:
                    break
            else:
                print(f"   ❌ Error on page {page}: {response.status_code}")
                break
        
        print("\n" + "=" * 60)
        print(f"📊 SUMMARY:")
        print(f"   Total documents fetched: {len(all_documents) + len(image_documents)}")
        print(f"   Image files (excluded): {len(image_documents)}")
        print(f"   Non-image documents: {len(all_documents)}")
        print("=" * 60)
        
        # Show breakdown by file type
        if all_documents:
            print(f"\n📋 Non-image documents by type:")
            type_counts = {}
            for doc in all_documents:
                ext = doc.get('DocumentFileExtension', 'unknown').lower()
                type_counts[ext] = type_counts.get(ext, 0) + 1
            
            for ext, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"   .{ext}: {count}")
        
        # Show some examples of non-image documents
        if all_documents:
            print(f"\n📄 First 10 non-image documents:")
            for i, doc in enumerate(all_documents[:10], 1):
                doc_id = doc.get('DocumentId', 'N/A')
                doc_name = doc.get('DocumentFileName', 'N/A')
                doc_folder = doc.get('DocumentFolder', 'N/A')
                doc_ext = doc.get('DocumentFileExtension', 'N/A')
                doc_entity = doc.get('DocumentLinkedEntityType', 'N/A')
                print(f"   {i}. {doc_name} (.{doc_ext}) - Folder: {doc_folder}, Linked: {doc_entity}")
        
        return len(all_documents), len(image_documents)
                    
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
    
    # Count non-image documents
    non_image_count, image_count = count_non_image_documents(access_token)
    
    print("\n" + "=" * 60)
    print(f"✅ NON-IMAGE DOCUMENTS: {non_image_count}")
    print(f"   (Excluded {image_count} image files)")
    print("=" * 60)

if __name__ == "__main__":
    print("=" * 60)
    print("WebCRM Non-Image Documents Counter")
    print("=" * 60)
    
    main()
