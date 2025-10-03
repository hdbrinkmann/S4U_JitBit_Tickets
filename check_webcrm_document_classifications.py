#!/usr/bin/env python3
"""
Script to check document classifications (folders) in webcrm API
"""

import os
import requests
from dotenv import load_dotenv
from collections import Counter

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

def analyze_document_classifications(access_token):
    """Analyze document folders/classifications"""
    
    base_url = "https://api.webcrm.com"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    print(f"\n📂 Analyzing document classifications...")
    
    # Collect all folder names
    folder_counts = Counter()
    entity_type_counts = Counter()
    all_docs = []
    page = 1
    
    try:
        while True:
            url = f"{base_url}/Documents?Page={page}&Size=100"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                documents = response.json()
                
                if isinstance(documents, list) and len(documents) > 0:
                    for doc in documents:
                        folder = doc.get('DocumentFolder', '(No folder)')
                        entity_type = doc.get('DocumentLinkedEntityType', 'Undefined')
                        
                        folder_counts[folder] += 1
                        entity_type_counts[entity_type] += 1
                        all_docs.append(doc)
                    
                    print(f"   📄 Page {page}: {len(documents)} documents analyzed")
                    
                    if len(documents) < 100:
                        break
                    page += 1
                else:
                    break
            else:
                print(f"   ❌ Error on page {page}: {response.status_code}")
                break
        
        print(f"\n   ✅ Analyzed {len(all_docs)} total documents")
        
        # Display folder classifications
        print("\n" + "=" * 60)
        print(f"📂 DOCUMENT FOLDERS (Classifications):")
        print("=" * 60)
        
        for folder, count in sorted(folder_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(all_docs)) * 100
            print(f"   {folder}: {count} documents ({percentage:.1f}%)")
        
        # Display entity type classifications
        print("\n" + "=" * 60)
        print(f"🔗 LINKED ENTITY TYPES:")
        print("=" * 60)
        
        for entity_type, count in sorted(entity_type_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(all_docs)) * 100
            print(f"   {entity_type}: {count} documents ({percentage:.1f}%)")
        
        # Show some examples from each major folder
        print("\n" + "=" * 60)
        print(f"📋 SAMPLE DOCUMENTS BY FOLDER:")
        print("=" * 60)
        
        # Get top 10 folders
        top_folders = [f for f, _ in folder_counts.most_common(10)]
        
        for folder in top_folders:
            folder_docs = [d for d in all_docs if d.get('DocumentFolder') == folder][:3]
            
            print(f"\n📁 {folder} ({folder_counts[folder]} documents):")
            for doc in folder_docs:
                filename = doc.get('DocumentFileName', 'N/A')
                desc = doc.get('DocumentDescription', 'N/A')
                entity = doc.get('DocumentLinkedEntityType', 'N/A')
                print(f"   - {filename}")
                if desc != filename:
                    print(f"     Description: {desc}")
                print(f"     Linked to: {entity}")
        
        # Save detailed report
        report_path = "webcrm_document_classifications_report.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("WebCRM Document Classifications Report\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Total documents analyzed: {len(all_docs)}\n\n")
            
            f.write("FOLDERS (Classifications):\n")
            f.write("-" * 60 + "\n")
            for folder, count in sorted(folder_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(all_docs)) * 100
                f.write(f"{folder}: {count} ({percentage:.1f}%)\n")
            
            f.write("\n\nLINKED ENTITY TYPES:\n")
            f.write("-" * 60 + "\n")
            for entity_type, count in sorted(entity_type_counts.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / len(all_docs)) * 100
                f.write(f"{entity_type}: {count} ({percentage:.1f}%)\n")
            
            f.write("\n\nALL FOLDERS (Alphabetical):\n")
            f.write("-" * 60 + "\n")
            for folder in sorted(folder_counts.keys()):
                f.write(f"- {folder}\n")
        
        print(f"\n📝 Detailed report saved to: {report_path}")
        
        return folder_counts, entity_type_counts
                    
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    return None, None

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
    
    # Analyze classifications
    folder_counts, entity_counts = analyze_document_classifications(access_token)
    
    print("\n" + "=" * 60)
    if folder_counts:
        print(f"✅ Found {len(folder_counts)} different folder classifications")
        print(f"   Documents are categorized into folders and linked to entities")
    else:
        print("⚠️  Could not analyze document classifications")
    print("=" * 60)

if __name__ == "__main__":
    print("=" * 60)
    print("WebCRM Document Classifications Analyzer")
    print("=" * 60)
    
    main()
