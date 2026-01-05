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
        self.existing_tasks_cache = {}  # Cache of existing tasks per database
        
        # Fetch existing tasks from all databases for duplicate detection
        self._fetch_existing_tasks()
        
    def _fetch_existing_tasks(self):
        """
        Fetch existing tasks from all databases to prevent duplicates.
        Stores task names (titles) in a set for quick lookup.
        """
        print("\nFetching existing tasks from Notion databases...")
        
        for dept, db_id in self.department_databases.items():
            try:
                # Query all pages in this database
                response = self.client.databases.query(database_id=db_id)
                
                # Extract task names (titles)
                task_names = set()
                for page in response.get('results', []):
                    # Get the Name property (title)
                    name_prop = page.get('properties', {}).get('Name', {})
                    title_array = name_prop.get('title', [])
                    
                    if title_array:
                        # Get the text content from the first title element
                        task_name = title_array[0].get('text', {}).get('content', '')
                        if task_name:
                            task_names.add(task_name.strip().lower())
                
                self.existing_tasks_cache[dept] = task_names
                print(f"  ✓ {dept}: Found {len(task_names)} existing tasks")
                
            except Exception as e:
                print(f"  ⚠️  {dept}: Could not fetch existing tasks - {e}")
                self.existing_tasks_cache[dept] = set()
        
        total_existing = sum(len(tasks) for tasks in self.existing_tasks_cache.values())
        print(f"\nTotal existing tasks across all databases: {total_existing}")


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
    
    def determine_departments(self, task: Dict) -> List[str]:
        """
        Determine ALL departments a task should be visible in.
        
        For cross-department collaboration:
        - If assignee has multiple departments, task appears in all of them
        - If task mentions multiple people from different departments, appears in all
        
        Priority:
        1. If assignee is specified, use ALL their departments
        2. If role is specified, try to match to department
        3. Return empty list (will go to default/unassigned database)
        """
        departments = set()  # Use set to avoid duplicates
        
        assignee = task.get('assignee')
        role = task.get('role')
        task_text = task.get('text', '').lower()
        
        # Get departments from assignee
        if assignee:
            depts = self.get_employee_departments(assignee)
            if depts:
                departments.update(depts)
        
        # Also check if other employees are mentioned in the task text
        # This enables cross-department visibility
        for emp_name, emp_depts in self.employee_to_dept.items():
            if emp_name in task_text:
                departments.update(emp_depts)
        
        # Try role matching if no departments found yet
        if not departments and role:
            role_lower = role.lower()
            # Simple keyword matching
            if 'hr' in role_lower or 'human resources' in role_lower:
                departments.add('HR')
            elif 'marketing' in role_lower:
                departments.add('Marketing')
            elif 'social media' in role_lower:
                departments.add('Social Media')
            elif 'operations' in role_lower or 'project management' in role_lower:
                departments.add('Operations')
            elif 'business' in role_lower or 'development' in role_lower:
                departments.add('Business Development')
            elif 'ai' in role_lower or 'tech' in role_lower or 'developer' in role_lower:
                departments.add('AI Research & Development')
        
        return list(departments)
    
    def is_duplicate_task(self, task_text: str, department: str) -> bool:
        """
        Check if a task with the same text already exists in the department's database.
        
        Args:
            task_text: The task text to check
            department: Department name
            
        Returns:
            True if task already exists, False otherwise
        """
        if department not in self.existing_tasks_cache:
            return False
        
        # Normalize the task text for comparison
        normalized_text = task_text.strip().lower()
        
        # Check if this task text exists in the cache
        return normalized_text in self.existing_tasks_cache[department]
    
    
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
            # Check for duplicates first
            task_text = task.get('text', '')
            if self.is_duplicate_task(task_text, department):
                print(f"⊘ Skipping duplicate task in {department}: {task_text[:60]}...")
                return None  # None = duplicate (not an error)
            
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
            
            # Update cache to include this new task
            if department in self.existing_tasks_cache:
                self.existing_tasks_cache[department].add(task_text.strip().lower())
            
            return True
            
        except Exception as e:
            print(f"ERROR creating task in Notion: {e}")
            print(f"Task: {task.get('text', 'Unknown')[:100]}")
            return False
    
    def sync_tasks(self, tasks: List[Dict]) -> Dict[str, int]:
        """
        Sync all tasks to their appropriate Notion databases.
        Tasks involving multiple departments will be created in all relevant databases.
        
        Returns:
            Dictionary with sync statistics
        """
        stats = {
            'total': len(tasks),
            'synced': 0,
            'skipped': 0,  # Duplicates
            'failed': 0,
            'cross_department': 0,  # Tasks synced to multiple departments
            'by_department': {}
        }
        
        for task in tasks:
            # Determine ALL departments this task should appear in
            departments = self.determine_departments(task)
            
            # If no departments found, use default
            if not departments:
                if 'default' in self.department_databases:
                    departments = ['default']
                else:
                    print(f"WARNING: No department found for task and no default configured")
                    print(f"  Task: {task.get('text', 'Unknown')[:60]}...")
                    stats['failed'] += 1
                    continue
            
            # Track if this task was synced to multiple departments
            is_cross_department = len(departments) > 1
            if is_cross_department:
                stats['cross_department'] += 1
            
            # Create task in ALL relevant departments
            task_synced_count = 0
            task_skipped_count = 0
            task_failed_count = 0
            
            for dept in departments:
                # Check if we have a database ID for this department
                if dept not in self.department_databases:
                    print(f"WARNING: No database configured for department '{dept}'")
                    task_failed_count += 1
                    continue
                
                # Create task in this department's database
                # Returns: True = success, False = error, None = duplicate
                result = self.create_task_in_notion(task, dept)
                
                if result is True:
                    task_synced_count += 1
                    display_dept = 'Unassigned' if dept == 'default' else dept
                    stats['by_department'][display_dept] = stats['by_department'].get(display_dept, 0) + 1
                    
                    # Show cross-department indicator
                    cross_indicator = " [cross-dept]" if is_cross_department else ""
                    print(f"✓ Synced task to {display_dept}{cross_indicator}: {task.get('text', 'Unknown')[:60]}...")
                    
                elif result is None:
                    task_skipped_count += 1  # Duplicate in this department
                else:  # result is False
                    task_failed_count += 1
            
            # Update overall stats
            if task_synced_count > 0:
                stats['synced'] += 1  # Count task as synced if it succeeded in at least one department
            elif task_skipped_count > 0:
                stats['skipped'] += 1  # All departments had duplicates
            else:
                stats['failed'] += 1  # Failed in all departments
        
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
    print(f"Skipped (duplicates): {stats['skipped']}")
    print(f"Failed: {stats['failed']}")
    print(f"Cross-department tasks: {stats.get('cross_department', 0)}")
    print("\nBy Department:")
    for dept, count in stats['by_department'].items():
        print(f"  {dept}: {count} tasks")
    print("="*60)


def sync_tasks_to_notion() -> bool:
    """
    Helper function to sync tasks to Notion.
    Can be called from other modules (e.g., app.py).
    
    Returns:
        True if sync was successful, False otherwise
    """
    try:
        # Get Notion token from environment
        notion_token = os.environ.get('NOTION_TOKEN')
        if not notion_token:
            print("[NOTION] ERROR: NOTION_TOKEN not configured")
            return False
        
        # Department to Database ID mapping
        department_databases = {
            'HR': os.environ.get('NOTION_DB_HR', ''),
            'Marketing': os.environ.get('NOTION_DB_MARKETING', ''),
            'Social Media': os.environ.get('NOTION_DB_SOCIAL_MEDIA', ''),
            'Operations': os.environ.get('NOTION_DB_OPERATIONS', ''),
            'Project Management': os.environ.get('NOTION_DB_OPERATIONS', ''),
            'Business Development': os.environ.get('NOTION_DB_BUSINESS_DEV', ''),
            'AI Research & Development': os.environ.get('NOTION_DB_AI_RND', ''),
            'default': os.environ.get('NOTION_DB_DEFAULT', '')
        }
        
        # Remove empty database IDs
        department_databases = {k: v for k, v in department_databases.items() if v}
        
        if not department_databases:
            print("[NOTION] ERROR: No databases configured")
            return False
        
        # Load tasks
        base_dir = Path(__file__).parent.parent
        tasks_file = base_dir / "tasks.json"
        tasks = load_tasks(tasks_file)
        
        if not tasks:
            print("[NOTION] No tasks to sync")
            return True  # Not an error, just nothing to do
        
        print(f"[NOTION] Syncing {len(tasks)} tasks to Notion...")
        
        # Initialize sync client
        sync_client = NotionTaskSync(notion_token, department_databases)
        
        # Sync tasks
        stats = sync_client.sync_tasks(tasks)
        
        # Print summary
        print(f"[NOTION] ✓ Sync completed:")
        print(f"[NOTION]   • Synced: {stats['synced']}")
        print(f"[NOTION]   • Skipped (duplicates): {stats['skipped']}")
        print(f"[NOTION]   • Failed: {stats['failed']}")
        print(f"[NOTION]   • Cross-department: {stats.get('cross_department', 0)}")
        
        # Return True if at least some tasks were synced successfully
        return stats['synced'] > 0 or stats['skipped'] > 0
        
    except Exception as e:
        print(f"[NOTION] ERROR: {e}")
        return False


if __name__ == "__main__":
    main()
