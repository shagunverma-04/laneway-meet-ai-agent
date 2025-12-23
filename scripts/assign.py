# Simple assignment engine: maps tasks to employees based on role keywords and participant presence.
import argparse, json, datetime, sys

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('tasks', help='tasks.json')
    parser.add_argument('employees', help='employees.json')
    args = parser.parse_args()
    with open(args.tasks) as f:
        tasks = json.load(f)
    with open(args.employees) as f:
        employees = json.load(f)

    assignments = []
    for t in tasks:
        assigned = None
        # 1) If assignee present, try to match by name/email
        assignee = t.get('assignee')
        if assignee:
            for e in employees:
                if assignee.lower() in (e.get('email','').lower() or '') or assignee.lower() in e.get('name','').lower():
                    assigned = e
                    break
        # 2) Else try role match
        if not assigned and t.get('role'):
            for e in employees:
                if t['role'].lower() in ' '.join(e.get('roles',[])).lower():
                    assigned = e
                    break
        # 3) Fallback: pick participant or first employee with matching skill keyword
        if not assigned:
            text = t.get('text','').lower()
            for e in employees:
                # participant bonus if name appears
                if e.get('name','').lower() in text or e.get('email','').split('@')[0].lower() in text:
                    assigned = e
                    break
        if not assigned and employees:
            assigned = employees[0]  # default fallback

        assignments.append({
            "task": t,
            "assignee": assigned
        })
    with open('assignments.json','w') as f:
        json.dump(assignments, f, indent=2, default=str)
    print("Wrote assignments.json with", len(assignments), "entries")
