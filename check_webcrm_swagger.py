#!/usr/bin/env python3
"""
Script to examine webcrm API swagger spec for documents endpoint details
"""

import os
import json
import requests
from dotenv import load_dotenv

def check_swagger_spec():
    """Check swagger specification for document endpoint details"""
    
    # Load environment variables
    load_dotenv()
    
    api_key = os.getenv('WEBCRM_API_KEY')
    
    if not api_key:
        print("❌ Error: WEBCRM_API_KEY not found in .env file")
        return
    
    print(f"✓ API Key loaded: {api_key[:8]}...{api_key[-4:]}")
    
    # Set up the API base URL
    base_url = "https://api.webcrm.com"
    
    # Set up headers
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    print("\n🔍 Fetching API specification...")
    
    url = f"{base_url}/swagger/v1/swagger.json"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("✅ Successfully fetched swagger spec")
            spec = response.json()
            
            # Check if Documents endpoint exists
            if 'paths' in spec and '/Documents' in spec['paths']:
                print("\n📄 Found /Documents endpoint in spec!")
                doc_endpoint = spec['paths']['/Documents']
                
                print("\n   Available methods:")
                for method, details in doc_endpoint.items():
                    print(f"   - {method.upper()}")
                    if 'summary' in details:
                        print(f"     Summary: {details['summary']}")
                    if 'parameters' in details:
                        print(f"     Parameters: {len(details['parameters'])}")
                        for param in details['parameters']:
                            print(f"       - {param.get('name', 'N/A')}: {param.get('type', 'N/A')} ({param.get('in', 'N/A')})")
                
                # Check security requirements
                if 'get' in doc_endpoint:
                    get_details = doc_endpoint['get']
                    if 'security' in get_details:
                        print(f"\n   Security requirements: {get_details['security']}")
                    
                    # Check responses
                    if 'responses' in get_details:
                        print("\n   Expected responses:")
                        for code, resp in get_details['responses'].items():
                            print(f"     - {code}: {resp.get('description', 'N/A')}")
            
            # Check security definitions
            if 'securityDefinitions' in spec:
                print("\n🔒 Security definitions found:")
                for name, details in spec['securityDefinitions'].items():
                    print(f"   - {name}:")
                    print(f"     Type: {details.get('type', 'N/A')}")
                    print(f"     In: {details.get('in', 'N/A')}")
                    print(f"     Name: {details.get('name', 'N/A')}")
            
            # Check base path
            if 'basePath' in spec:
                print(f"\n📍 Base Path: {spec['basePath']}")
            
            if 'host' in spec:
                print(f"📍 Host: {spec['host']}")
            
            # List all document-related endpoints
            print("\n📋 All document-related endpoints:")
            doc_paths = {k: v for k, v in spec['paths'].items() if 'document' in k.lower()}
            for path, methods in doc_paths.items():
                print(f"\n   {path}")
                for method in methods.keys():
                    print(f"      - {method.upper()}")
            
            # Save full spec for reference
            with open('webcrm_swagger_spec.json', 'w') as f:
                json.dump(spec, f, indent=2)
            print("\n💾 Full spec saved to: webcrm_swagger_spec.json")
            
        else:
            print(f"❌ Failed to fetch swagger spec: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    print("=" * 60)
    print("WebCRM Swagger Specification Inspector")
    print("=" * 60)
    
    check_swagger_spec()
    
    print("\n" + "=" * 60)
