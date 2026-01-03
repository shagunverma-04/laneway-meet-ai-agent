"""
Notion Integration for Task Management
Automatically syncs extracted tasks to department-specific Notion databases.

Features:
- Routes tasks to correct department based on assignee
- Creates tasks with all metadata (priority, deadline, confidence)
- Supports both individual and team assignments
- Handles unassigned tasks gracefully
- Compatible with Notion API version 2022-06-28
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Try to import notion_client
try:
    from notion_client import Client
except ImportError:
    print("ERROR: notion-client not installed. Install with: pip install notion-client")
    sys.exit(1)

# Try to load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

class NotionTaskSync:
    def __init__(self, notion_token: str, department_databases: Dict[str, str]):
        """
        Initialize Notion client and department database mapping.
        
        Args:
            notion_token: Notion integration token
            department_databases: Dict mapping department names to database IDs
        """
        self.client = Client(auth=notion_token, notion_version="2022-06-28")
        self.department_databases = department_databases
        self.employees = self._load_employees()
        self.employee_to_dept = self._build_employee_dept_map()
        


    def _load_employees(self) -> List[Dict]:
        """Load employee data from employees.json"""
        base_dir = Path(__file__).parent.parent
        employees_file = base_dir / "employees.json"
        
        if not employees_file.exists():
            print(f"WARNING: employees.json not found at {employees_file}")
            return []
        
        with open(employees_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _build_employee_dept_map(self) -> Dict[str, List[str]]:
        """Build mapping of employee names to their departments"""
        mapping = {}
        for emp in self.employees:
            name = emp.get('name', '').strip()
            departments = emp.get('department', [])
            if name and departments:
                mapping[name.lower()] = departments
        return mapping
    
    def get_employee_departments(self, assignee_name: str) -> List[str]:
        """Get departments for an employee by name"""
        if not assignee_name:
            return []
        
        name_lower = assignee_name.strip().lower()
        return self.employee_to_dept.get(name_lower, [])
    
    def determine_department(self, task: Dict) -> Optional[str]:
        """
        Determine which department a task belongs to.
        
        Priority:
        1. If assignee is specified, use their department
        2. If role is specified, try to match to department
        3. Return None (will go to default/unassigned database)
        """
        assignee = task.get('assignee')
        role = task.get('role')
        
        # Try assignee first
        if assignee:
            depts = self.get_employee_departments(assignee)
            if depts:
                return depts[0]  # Use primary department
        
        # Try role matching
        if role:
            role_lower = role.lower()
            # Simple keyword matching
            if 'hr' in role_lower or 'human resources' in role_lower:
                return 'HR'
            elif 'marketing' in role_lower or 'social media' in role_lower:
                return 'Marketing'
            elif 'operations' in role_lower or 'project management' in role_lower:
                return 'Operations'
            elif 'business' in role_lower or 'development' in role_lower:
                return 'Business Development'
            elif 'ai' in role_lower or 'tech' in role_lower or 'developer' in role_lower:
                return 'AI Research & Development'
        
        return None
    
    def create_task_in_notion(self, task: Dict, department: str) -> bool:
        """
        Create a task in the specified Notion database.
        
        Args:
            task: Task dictionary with text, assignee, deadline, priority, etc.
            department: Department name to create task in
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get database ID for this department
            database_id = self.department_databases.get(department)
            if not database_id:
                print(f"ERROR: No database ID found for department: {department}")
                return False
            
            # Build properties for the Notion page
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": task.get('text', 'Untitled Task')[:2000]  # Notion limit
                            }
                        }
                    ]
                }
            }
            
            # Add assignee if present
            if task.get('assignee'):
                properties["Assignee"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": task['assignee']
                            }
                        }
                    ]
                }
            
            # Add role if present
            if task.get('role'):
                properties["Role"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": task['role']
                            }
                        }
                    ]
                }
            
            # Add priority as select
            if task.get('priority'):
                properties["Priority"] = {
                    "select": {
                        "name": task['priority']
                    }
                }
            
            # Add deadline as date
            if task.get('deadline'):
                properties["Deadline"] = {
                    "date": {
                        "start": task['deadline']
                    }
                }
            
            # Add confidence as number
            if task.get('confidence') is not None:
                properties["Confidence "] = {
                    "number": task['confidence']
                }
            
            # Add status (default to "To Do")
            properties["Status "] = {
                "select": {
                    "name": "To Do"
                }
            }
            
            # Create the page using database_id (older API version)
            self.client.pages.create(
                parent={
                    "type": "database_id",
                    "database_id": database_id
                },
                properties=properties
            )
            
            return True
            
        except Exception as e:
            print(f"ERROR creating task in Notion: {e}")
            print(f"Task: {task.get('text', 'Unknown')[:100]}")
            return False
    
    def sync_tasks(self, tasks: List[Dict]) -> Dict[str, int]:
        """
        Sync all tasks to their appropriate Notion databases.
        
        Returns:
            Dictionary with sync statistics
        """
        stats = {
            'total': len(tasks),
            'synced': 0,
            'failed': 0,
            'by_department': {}
        }
        
        for task in tasks:
            # Determine department
            dept = self.determine_department(task)
            
            # Check if we have a database ID for this department
            if dept and dept in self.department_databases:
                # Use the determined department
                pass
            elif 'default' in self.department_databases:
                # Fall back to default
                dept = 'default'
            else:
                print(f"WARNING: No database found for department '{dept}' and no default configured")
                stats['failed'] += 1
                continue
            
            # Create task in Notion (pass department name, not database ID)
            success = self.create_task_in_notion(task, dept)
            
            if success:
                stats['synced'] += 1
                display_dept = 'Unassigned' if dept == 'default' else dept
                stats['by_department'][display_dept] = stats['by_department'].get(display_dept, 0) + 1
                print(f"✓ Synced task to {display_dept}: {task.get('text', 'Unknown')[:60]}...")
            else:
                stats['failed'] += 1
        
        return stats


def load_tasks(tasks_file: Path) -> List[Dict]:
    """Load tasks from tasks.json"""
    if not tasks_file.exists():
        print(f"ERROR: Tasks file not found: {tasks_file}")
        return []
    
    with open(tasks_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    """Main execution function"""
    # Get Notion token from environment
    notion_token = os.environ.get('NOTION_TOKEN')
    if not notion_token:
        print("ERROR: NOTION_TOKEN environment variable not set")
        print("Get your token from: https://www.notion.so/my-integrations")
        sys.exit(1)
    
    # Department to Database ID mapping
    # You need to replace these with your actual Notion database IDs
    department_databases = {
        'HR': os.environ.get('NOTION_DB_HR', ''),
        'Marketing': os.environ.get('NOTION_DB_MARKETING', ''),
        'Social Media': os.environ.get('NOTION_DB_SOCIAL_MEDIA', ''),
        'Operations': os.environ.get('NOTION_DB_OPERATIONS', ''),
        'Project Management': os.environ.get('NOTION_DB_OPERATIONS', ''),  # Same as Operations
        'Business Development': os.environ.get('NOTION_DB_BUSINESS_DEV', ''),
        'AI Research & Development': os.environ.get('NOTION_DB_AI_RND', ''),
        'default': os.environ.get('NOTION_DB_DEFAULT', '')  # Fallback for unassigned tasks
    }
    
    # Remove empty database IDs
    department_databases = {k: v for k, v in department_databases.items() if v}
    
    if not department_databases:
        print("ERROR: No Notion database IDs configured")
        print("Set environment variables like: NOTION_DB_HR, NOTION_DB_MARKETING, etc.")
        sys.exit(1)
    
    print(f"Configured databases for departments: {', '.join(department_databases.keys())}")
    
    # Load tasks
    base_dir = Path(__file__).parent.parent
    tasks_file = base_dir / "tasks.json"
    tasks = load_tasks(tasks_file)
    
    if not tasks:
        print("No tasks to sync")
        return
    
    print(f"\nLoaded {len(tasks)} tasks from {tasks_file}")
    
    # Initialize sync client
    sync_client = NotionTaskSync(notion_token, department_databases)
    
    # Sync tasks
    print("\nSyncing tasks to Notion...")
    stats = sync_client.sync_tasks(tasks)
    
    # Print summary
    print("\n" + "="*60)
    print("SYNC SUMMARY")
    print("="*60)
    print(f"Total tasks: {stats['total']}")
    print(f"Successfully synced: {stats['synced']}")
    print(f"Failed: {stats['failed']}")
    print("\nBy Department:")
    for dept, count in stats['by_department'].items():
        print(f"  {dept}: {count} tasks")
    print("="*60)


if __name__ == "__main__":
    main()
