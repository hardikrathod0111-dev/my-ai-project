"""Tools the agent can call: long-term memory, tasks, notes, and the clock."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

from .storage import memories, notes, tasks


def _obj(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_ID = {"type": "integer", "description": "The record's id."}

# Order is fixed so the tool list stays byte-identical between requests (keeps prompt caching effective).
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "remember",
        "description": (
            "Save a lasting fact about the user to long-term memory (preferences, people, goals, "
            "important dates, decisions). Use it whenever the user shares something worth knowing "
            "in future conversations. Don't save trivia or one-off details."
        ),
        "input_schema": _obj({"fact": {"type": "string", "description": "One short, self-contained fact."}}, ["fact"]),
    },
    {
        "name": "forget",
        "description": "Delete a memory that is wrong or outdated, by id. Memory ids appear in the system prompt.",
        "input_schema": _obj({"id": _ID}, ["id"]),
    },
    {
        "name": "add_task",
        "description": "Add a to-do item for the user, optionally with a due date.",
        "input_schema": _obj(
            {
                "title": {"type": "string"},
                "due": {"type": ["string", "null"], "description": "Due date as YYYY-MM-DD, or null."},
            },
            ["title", "due"],
        ),
    },
    {
        "name": "list_tasks",
        "description": "List the user's tasks.",
        "input_schema": _obj({"include_done": {"type": "boolean"}}, ["include_done"]),
    },
    {
        "name": "complete_task",
        "description": "Mark a task as done, by id.",
        "input_schema": _obj({"id": _ID}, ["id"]),
    },
    {
        "name": "delete_task",
        "description": "Delete a task entirely, by id.",
        "input_schema": _obj({"id": _ID}, ["id"]),
    },
    {
        "name": "save_note",
        "description": "Save a note (ideas, drafts, captions, scripts, meeting notes) for later.",
        "input_schema": _obj(
            {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            ["title", "body", "tags"],
        ),
    },
    {
        "name": "search_notes",
        "description": "Find saved notes whose title, body or tags contain the query (case-insensitive). Empty query lists all.",
        "input_schema": _obj({"query": {"type": "string"}}, ["query"]),
    },
    {
        "name": "delete_note",
        "description": "Delete a note by id.",
        "input_schema": _obj({"id": _ID}, ["id"]),
    },
    {
        "name": "get_current_datetime",
        "description": "Get the current local date, time and weekday. Use before reasoning about deadlines or 'today'.",
        "input_schema": _obj({}, []),
    },
]

for _tool in TOOL_DEFINITIONS:
    _tool["strict"] = True


def _remember(fact: str) -> dict:
    return {"saved": memories.add(fact=fact)}


def _forget(id: int) -> dict:
    return {"deleted": memories.delete(id)}


def _add_task(title: str, due: str | None) -> dict:
    if due:
        datetime.strptime(due, "%Y-%m-%d")  # raises ValueError on a bad date
    return {"added": tasks.add(title=title, due=due, done=False)}


def _list_tasks(include_done: bool) -> dict:
    items = [t for t in tasks.load() if include_done or not t["done"]]
    items.sort(key=lambda t: (t["done"], t.get("due") or "9999-12-31"))
    return {"tasks": items}


def _complete_task(id: int) -> dict:
    task = tasks.update(id, done=True, completed=datetime.now().astimezone().isoformat(timespec="minutes"))
    if task is None:
        raise ValueError(f"No task with id {id}")
    return {"completed": task}


def _delete_task(id: int) -> dict:
    return {"deleted": tasks.delete(id)}


def _save_note(title: str, body: str, tags: list[str]) -> dict:
    return {"saved": notes.add(title=title, body=body, tags=tags)}


def _search_notes(query: str) -> dict:
    q = query.lower().strip()
    found = [
        n for n in notes.load()
        if not q or q in n["title"].lower() or q in n["body"].lower() or any(q in t.lower() for t in n["tags"])
    ]
    return {"notes": found}


def _delete_note(id: int) -> dict:
    return {"deleted": notes.delete(id)}


def _get_current_datetime() -> dict:
    now = datetime.now().astimezone()
    return {"datetime": now.isoformat(timespec="minutes"), "weekday": now.strftime("%A")}


_HANDLERS: dict[str, Callable[..., dict]] = {
    "remember": _remember,
    "forget": _forget,
    "add_task": _add_task,
    "list_tasks": _list_tasks,
    "complete_task": _complete_task,
    "delete_task": _delete_task,
    "save_note": _save_note,
    "search_notes": _search_notes,
    "delete_note": _delete_note,
    "get_current_datetime": _get_current_datetime,
}


def run_tool(name: str, tool_input: dict) -> tuple[str, bool]:
    """Execute a tool. Returns (result_text, is_error)."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}", True
    try:
        return json.dumps(handler(**tool_input), ensure_ascii=False), False
    except (TypeError, ValueError) as e:
        return f"Error: {e}", True
