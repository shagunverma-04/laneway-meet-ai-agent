"""
Inspect Notion Database Schema
Shows what properties (columns) exist in your Notion databases
"""

import os
import sys
from dotenv import load_dotenv

try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion-client not installed. Install with: pip install notion-client")
    sys.exit(1)

load_dotenv()

def inspect_database(client, db_id, db_name):
    """Inspect a Notion database and show its properties"""
    try:
        print(f"\n{'='*60}")
        print(f"Database: {db_name}")
        print(f"ID: {db_id}")
        print(f"{'='*60}")
        
        response = client.databases.retrieve(database_id=db_id)
        
        properties = response.get('properties', {})
        
        if not properties:
            print("  ⚠️  No properties found!")
            return
        
        print(f"\nFound {len(properties)} properties:\n")
        
        for prop_name, prop_data in properties.items():
            prop_type = prop_data.get('type', 'unknown')
            
            # Show select options if it's a select property
            if prop_type == 'select':
                options = prop_data.get('select', {}).get('options', [])
                option_names = [opt.get('name') for opt in options]
                print(f"  ✓ {prop_name:20s} - {prop_type:15s} (options: {', '.join(option_names)})")
            else:
                print(f"  ✓ {prop_name:20s} - {prop_type}")
        
        # Show what's missing
        required_props = {
            'Name': 'title',
            'Assignee': 'rich_text',
            'Role': 'rich_text',
            'Priority': 'select',
            'Deadline': 'date',
            'Confidence': 'number',
            'Status': 'select'
        }
        
        missing = []
        for req_name, req_type in required_props.items():
            if req_name not in properties:
                missing.append(f"{req_name} ({req_type})")
        
        if missing:
            print(f"\n  ⚠️  MISSING PROPERTIES:")
            for m in missing:
                print(f"     - {m}")
        else:
            print(f"\n  ✅ All required properties exist!")
            
    except Exception as e:
        print(f"  ❌ ERROR: {e}")

def main():
    # Get Notion token
    notion_token = os.environ.get('NOTION_TOKEN')
    if not notion_token:
        print("ERROR: NOTION_TOKEN environment variable not set")
        sys.exit(1)
    
    # Initialize client
    client = Client(auth=notion_token, notion_version="2025-09-03")
    
    # Database IDs to inspect
    databases = {
        'HR': os.environ.get('NOTION_DB_HR', ''),
        'Marketing': os.environ.get('NOTION_DB_MARKETING', ''),
        'Social Media': os.environ.get('NOTION_DB_SOCIAL_MEDIA', ''),
        'Operations': os.environ.get('NOTION_DB_OPERATIONS', ''),
        'Business Development': os.environ.get('NOTION_DB_BUSINESS_DEV', ''),
        'AI Research & Development': os.environ.get('NOTION_DB_AI_RND', ''),
        'Default': os.environ.get('NOTION_DB_DEFAULT', '')
    }
    
    # Remove empty entries
    databases = {k: v for k, v in databases.items() if v}
    
    if not databases:
        print("ERROR: No database IDs configured in .env")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("NOTION DATABASE SCHEMA INSPECTOR")
    print("="*60)
    
    for db_name, db_id in databases.items():
        inspect_database(client, db_id, db_name)
    
    print("\n" + "="*60)
    print("\nREQUIRED PROPERTIES FOR SYNC SCRIPT:")
    print("="*60)
    print("  1. Name         - Title")
    print("  2. Assignee     - Text")
    print("  3. Role         - Text")
    print("  4. Priority     - Select (options: High, Medium, Low)")
    print("  5. Deadline     - Date")
    print("  6. Confidence   - Number")
    print("  7. Status       - Select (options: To Do, In Progress, Done)")
    print("="*60)

if __name__ == "__main__":
    main()
