"""
Helper module to sync tasks to Notion after extraction.
This is called automatically by app.py after task extraction completes.
"""

import os
import sys
from pathlib import Path

def sync_tasks_to_notion():
    """
    Automatically sync tasks to Notion after extraction.
    This function is called as a background task after task extraction completes.
    """
    # Check if Notion is configured
    notion_token = os.environ.get('NOTION_TOKEN')
    if not notion_token:
        print("[NOTION] Skipping sync - NOTION_TOKEN not configured")
        return
    
    # Check if we have at least one database configured
    has_database = any([
        os.environ.get('NOTION_DB_HR'),
        os.environ.get('NOTION_DB_MARKETING'),
        os.environ.get('NOTION_DB_SOCIAL_MEDIA'),
        os.environ.get('NOTION_DB_OPERATIONS'),
        os.environ.get('NOTION_DB_BUSINESS_DEV'),
        os.environ.get('NOTION_DB_AI_RND'),
        os.environ.get('NOTION_DB_DEFAULT')
    ])
    
    if not has_database:
        print("[NOTION] Skipping sync - No databases configured")
        return
    
    # Import and run the sync script
    try:
        # Add scripts directory to path
        base_dir = Path(__file__).parent
        scripts_dir = base_dir / "scripts"
        sys.path.insert(0, str(scripts_dir))
        
        # Import the sync module
        from sync_to_notion import main as sync_main
        
        print("[NOTION] Starting automatic sync to Notion...")
        sync_main()
        print("[NOTION] ✓ Sync completed successfully")
        
    except ImportError as e:
        print(f"[NOTION] Import error: {e}")
    except Exception as e:
        print(f"[NOTION] Sync error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Allow running this directly for testing
    sync_tasks_to_notion()
