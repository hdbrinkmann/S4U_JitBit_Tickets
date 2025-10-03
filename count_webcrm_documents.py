#!/usr/bin/env python3
"""
Script to count documents available in webcrm API
"""

import os
import requests
from dotenv import load_dotenv

def count_webcrm_documents():
    """Count documents available in webcrm API"""
    
    # Load environment variables
    load_dotenv()
    
    api_key = os.getenv('WEBCRM_API_KEY')
    
    if not api_key:
        print("❌ Error: WEBCRM_API_KEY not found in .env file")
        return
    
    print(f"✓ API Key loaded: {api_key[:8]}...{api_key[-4:]}")
    
    # Set up the API base URL
    base_url = "https://api.webcrm.com"
    
    # Set up headers with Bearer token authentication
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Try different possible document endpoints
    # Note: /Documents supports pagination via ?Page=1&Size=100
    document_endpoints = [
        "/Documents?Page=1&Size=100",
        "/Documents",
        "/api/v1/documents",
        "/api/v1/files",
        "/api/v1/attachments",
        "/api/v2/documents",
        "/api/v2/files"
    ]
    
    print("\n🔍 Searching for document endpoints...")
    
    for endpoint in document_endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n📡 Testing: {endpoint}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            print(f"   Status Code: {response.status_code}")
            
            if response.status_code == 200:
                print(f"   ✅ Found documents endpoint!")
                
                try:
                    data = response.json()
                    
                    if isinstance(data, list):
                        print(f"   📄 Total documents: {len(data)}")
                        
                        # Show first few document details
                        if len(data) > 0:
                            print(f"\n   Sample document structure:")
                            sample = data[0]
                            for key, value in list(sample.items())[:10]:
                                print(f"      {key}: {value}")
                            
                            if len(data) > 3:
                                print(f"\n   First 3 documents:")
                                for i, doc in enumerate(data[:3], 1):
                                    doc_id = doc.get('Id') or doc.get('id') or doc.get('DocumentId')
                                    doc_name = doc.get('Name') or doc.get('name') or doc.get('FileName') or 'N/A'
                                    print(f"      {i}. ID: {doc_id}, Name: {doc_name}")
                        
                        return endpoint, len(data)
                        
                    elif isinstance(data, dict):
                        # Might be paginated response
                        if 'data' in data:
                            docs = data['data']
                            total = data.get('total', len(docs))
                            print(f"   📄 Total documents: {total}")
                            print(f"   📄 Documents in current page: {len(docs)}")
                            return endpoint, total
                        elif 'items' in data:
                            docs = data['items']
                            total = data.get('total', len(docs))
                            print(f"   📄 Total documents: {total}")
                            print(f"   📄 Documents in current page: {len(docs)}")
                            return endpoint, total
                        else:
                            print(f"   Response keys: {list(data.keys())}")
                            print(f"   Response preview: {str(data)[:300]}...")
                            
                except ValueError:
                    print(f"   Response is not JSON")
                    print(f"   Response preview: {response.text[:200]}...")
                    
            elif response.status_code == 404:
                print(f"   ℹ️  Not found")
            elif response.status_code == 401:
                print(f"   ❌ Authentication failed")
            elif response.status_code == 403:
                print(f"   ❌ Forbidden - no access")
            else:
                print(f"   Response: {response.text[:200]}")
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Error: {str(e)}")
    
    # Try to get swagger/openapi spec
    print("\n\n🔍 Checking API documentation endpoints...")
    spec_endpoints = [
        "/swagger.json",
        "/api-docs",
        "/openapi.json",
        "/swagger/v1/swagger.json"
    ]
    
    for endpoint in spec_endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n📡 Testing: {endpoint}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                print(f"   ✅ Found API spec!")
                try:
                    spec = response.json()
                    # Look for document-related paths
                    if 'paths' in spec:
                        doc_paths = [p for p in spec['paths'].keys() if 'document' in p.lower() or 'file' in p.lower()]
                        if doc_paths:
                            print(f"   📄 Document-related endpoints found:")
                            for path in doc_paths:
                                print(f"      {path}")
                except:
                    pass
        except:
            pass
    
    print("\n\n❌ Could not find documents endpoint automatically")
    print("💡 Tip: Check the webcrm API documentation for the correct endpoint")
    return None, 0

if __name__ == "__main__":
    print("=" * 60)
    print("WebCRM Documents Counter")
    print("=" * 60)
    
    result = count_webcrm_documents()
    
    print("\n" + "=" * 60)
    if result and result[1] > 0:
        print(f"✅ Found {result[1]} documents at endpoint: {result[0]}")
    else:
        print("⚠️  Could not determine document count")
    print("=" * 60)
