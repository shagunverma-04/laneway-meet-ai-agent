# Automated Task Extraction to Notion Workflow

## Overview
The system now automatically syncs extracted tasks to Notion after processing meeting recordings. No manual intervention required!

## How It Works

### 1. **Upload & Process**
- User uploads a meeting recording (video/audio) through the web interface
- Click "Process" button

### 2. **Automatic Pipeline**
The following happens automatically:

```
Upload File
    ↓
Extract Audio (ffmpeg)
    ↓
Transcribe Audio (Whisper/OpenAI)
    ↓
Extract Tasks (AI/LLM)
    ↓
Sync to Notion ← AUTOMATIC! ✨
```

### 3. **Department Routing & Cross-Department Visibility**

Tasks are intelligently routed to Notion databases with these features:

#### Smart Routing:
- **Assignee's department** (from `employees.json`)
- **All mentioned employees** - if a task mentions multiple people from different departments, it appears in ALL their departments
- **Role mentioned** in the task
- **Default database** for unassigned tasks

#### Cross-Department Collaboration:
When a task involves employees from multiple departments, it will be created in **ALL relevant department databases**. This ensures:
- ✅ Each department sees tasks relevant to their team members
- ✅ Better visibility for cross-functional work
- ✅ No need to manually duplicate tasks

**Example:**
```
Task: "Shagun (Marketing) needs to coordinate with Devin (AI R&D) on the new feature launch"
→ Created in BOTH Marketing AND AI R&D databases
```

#### Duplicate Prevention:
- **Automatic detection**: System checks existing tasks before creating new ones
- **Smart comparison**: Matches task text to prevent duplicates
- **Per-database tracking**: Same task can exist in multiple departments (cross-dept visibility) but won't be duplicated within the same database
- **Reprocessing safe**: If you process the same video twice, duplicate tasks won't be created


## Configuration

### Required Environment Variables

```bash
# Notion Integration Token
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Department Databases (at least one required)
NOTION_DB_HR=your_hr_database_id
NOTION_DB_MARKETING=your_marketing_database_id
NOTION_DB_SOCIAL_MEDIA=your_social_media_database_id
NOTION_DB_OPERATIONS=your_operations_database_id
NOTION_DB_BUSINESS_DEV=your_business_dev_database_id
NOTION_DB_AI_RND=your_ai_rnd_database_id
NOTION_DB_DEFAULT=your_default_database_id  # Fallback for unassigned
```

### Database Properties Required

Each Notion database must have these properties (columns):

| Property Name | Type | Notes |
|--------------|------|-------|
| `Name` | Title | Task description |
| `Assignee` | Text | Employee name |
| `Role` | Text | Role/team |
| `Priority` | Select | High/Medium/Low |
| `Deadline` | Date | Due date |
| `Confidence ` | Number | AI confidence (note the trailing space!) |
| `Status ` | Select | To Do/In Progress/Done (note the trailing space!) |

⚠️ **Important**: The property names must match EXACTLY, including trailing spaces for `Confidence ` and `Status `.

## Manual Sync (Optional)

If you want to manually sync tasks to Notion:

```bash
python scripts/sync_to_notion.py
```

## Testing the Automation

1. **Upload a test recording**
2. **Check the console logs** - you should see:
   ```
   [NOTION] Starting automatic sync to Notion...
   ✓ Synced task to HR: Task description...
   ✓ Synced task to Marketing: Task description...
   [NOTION] ✓ Sync completed successfully
   ```

3. **Check your Notion databases** - tasks should appear automatically!

### Example Output

When syncing tasks, you'll see output like this:

```
[NOTION] Syncing 12 tasks to Notion...

Fetching existing tasks from Notion databases...
  ✓ HR: Found 45 existing tasks
  ✓ Marketing: Found 32 existing tasks
  ✓ AI Research & Development: Found 28 existing tasks

Total existing tasks across all databases: 105

✓ Synced task to Marketing [cross-dept]: Shagun needs to coordinate with Devin...
✓ Synced task to AI Research & Development [cross-dept]: Shagun needs to coordinate with Devin...
⊘ Skipping duplicate task in HR: Update employee handbook by Friday...
✓ Synced task to Operations: Schedule team standup for next week...

[NOTION] ✓ Sync completed:
[NOTION]   • Synced: 10
[NOTION]   • Skipped (duplicates): 2
[NOTION]   • Failed: 0
[NOTION]   • Cross-department: 3
```

**Indicators:**
- `[cross-dept]` - Task created in multiple departments
- `⊘ Skipping duplicate` - Task already exists (prevents duplicates)
- `✓ Synced` - Successfully created in Notion


## Troubleshooting

### Tasks not syncing?

1. **Check environment variables**:
   ```bash
   python -c "import os; print('Token:', bool(os.environ.get('NOTION_TOKEN')))"
   ```

2. **Verify database properties**:
   ```bash
   python scripts/check_exact_names.py
   ```

3. **Check logs** in the console for error messages

### Common Issues

- **"NOTION_TOKEN not configured"** → Set the `NOTION_TOKEN` environment variable
- **"No databases configured"** → Set at least one `NOTION_DB_*` variable
- **"Property does not exist"** → Check property names match exactly (including spaces!)
- **"No properties found"** → Make sure the integration has access to the databases

## Files Involved

- `app.py` - Main application with auto-sync integration
- `notion_sync_helper.py` - Helper module for automatic syncing
- `scripts/sync_to_notion.py` - Core Notion sync logic
- `employees.json` - Employee-to-department mapping
- `tasks.json` - Extracted tasks (auto-generated)

## Success Indicators

✅ Tasks appear in correct department databases  
✅ All task metadata is populated (assignee, priority, deadline, etc.)  
✅ Console shows successful sync messages  
✅ No manual intervention needed  

---

**Last Updated**: 2026-01-03  
**API Version**: Notion API 2022-06-28
