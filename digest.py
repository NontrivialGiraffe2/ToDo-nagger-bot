"""
Daily to-do digest.

Pulls today's + overdue tasks from Todoist, asks Claude to group and
prioritize them, and sends the result to you as a Telegram message.

Runs on a schedule via GitHub Actions (see .github/workflows/digest.yml).
Reads all credentials from environment variables — never hard-code them.
"""

import os
import datetime
import requests
from anthropic import Anthropic

# --- Credentials (set as GitHub Actions secrets) ---
TODOIST_TOKEN = os.environ["TODOIST_TOKEN"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]
anthropic = Anthropic()  # reads ANTHROPIC_API_KEY from the environment

TODOIST_BASE = "https://api.todoist.com/api/v1"


def get_tasks():
    """Fetch all active tasks, following cursor-based pagination."""
    tasks, cursor = [], None
    while True:
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = requests.get(
            f"{TODOIST_BASE}/tasks",
            headers={"Authorization": f"Bearer {TODOIST_TOKEN}"},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        tasks += data["results"]
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return tasks


def due_today_or_overdue(tasks):
    """Keep only tasks whose due date is today or earlier."""
    today = datetime.date.today().isoformat()
    out = []
    for t in tasks:
        due = (t.get("due") or {}).get("date")  # "YYYY-MM-DD" or full datetime
        if due and due[:10] <= today:
            out.append(t)
    return out


def prioritize(tasks):
    """Ask Claude to group and prioritize the day's tasks."""
    # Todoist priority: 4 = highest (p1 in the app), 1 = normal (p4).
    lines = [
        f"- {t['content']} (priority {t['priority']}, due {(t.get('due') or {}).get('date', '?')})"
        for t in tasks
    ]
    prompt = (
        "My tasks for today are below. Todoist priority is 4=highest, 1=normal.\n"
        "Group them into 'Do first', 'Then', and 'If time'. Be terse. "
        "Flag anything overdue.\n\n" + "\n".join(lines)
    )
    msg = anthropic.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def notify(text):
    """Send a plain-text Telegram message to yourself."""
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT_ID, "text": text},
        timeout=30,
    )
    r.raise_for_status()


def main():
    tasks = due_today_or_overdue(get_tasks())
    notify(prioritize(tasks) if tasks else "Nothing due today. \U0001F389")


if __name__ == "__main__":
    main()
