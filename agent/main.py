"""Terminal chat for your personal AI agent.

Run with:  python -m agent
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic

from .storage import memories, notes, tasks
from .tools import TOOL_DEFINITIONS, run_tool

MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("AGENT_EFFORT", "medium")  # low | medium | high | xhigh | max
AGENT_NAME = os.environ.get("AGENT_NAME", "Jarvis")
PROFILE_PATH = Path(os.environ.get("AGENT_PROFILE", Path(__file__).resolve().parent.parent / "profile.md"))
MAX_TOOL_ROUNDS = 25

# Server-side tool: Claude searches the web on Anthropic's side, no code needed here.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}

INSTRUCTIONS = """\
You are {agent_name}, a personal AI assistant for one person: the user described in the profile below.
You help with three things:

1. General help - answer questions, think things through, give honest opinions. Use web_search \
for anything recent or factual you're not sure of, and say where information came from.
2. Productivity - manage the user's tasks and notes with your tools. When the user mentions \
something they need to do, offer to add it as a task (or just add it if they clearly asked). \
Call get_current_datetime before working with dates like "today" or "next Friday".
3. Content and social media - brainstorm ideas, write hooks, captions, scripts and posts in the \
user's own voice as described in their profile. Offer to save drafts as notes.

Memory: you have long-term memory. When the user tells you something about themselves that will \
matter later (preferences, goals, people, routines, decisions), save it with `remember` - one \
short fact per call - and mention briefly that you've remembered it. If a memory turns out to be \
wrong or outdated, `forget` it and save the corrected version. Never store passwords, card \
numbers or other secrets.

Style: follow the user's preferences from the profile. Default to concise, friendly, practical \
answers in plain text that reads well in a terminal or chat app (short paragraphs, simple bullet lists, no tables or markdown headings).
"""


def build_system_prompt() -> str:
    profile = PROFILE_PATH.read_text(encoding="utf-8") if PROFILE_PATH.exists() else "(No profile yet.)"
    mem = memories.load()
    mem_text = "\n".join(f"- [id {m['id']}] {m['fact']}" for m in mem) or "(Nothing remembered yet.)"
    open_tasks = [t for t in tasks.load() if not t["done"]]
    task_text = "\n".join(
        f"- [id {t['id']}] {t['title']}" + (f" (due {t['due']})" if t.get("due") else "") for t in open_tasks
    ) or "(No open tasks.)"
    return (
        INSTRUCTIONS.format(agent_name=AGENT_NAME)
        + f"\n<user_profile>\n{profile.strip()}\n</user_profile>\n"
        + f"\n<long_term_memory>\n{mem_text}\n</long_term_memory>\n"
        + f"\n<open_tasks_at_session_start>\n{task_text}\n</open_tasks_at_session_start>\n"
    )


class Agent:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic()
        self.reset()

    def reset(self) -> None:
        # Built once per session so the prompt prefix stays identical and gets cached.
        self.system = build_system_prompt()
        self.messages: list[dict] = []

    def _call(self):
        return self.client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=self.system,
            messages=self.messages,
            tools=[*TOOL_DEFINITIONS, WEB_SEARCH_TOOL],
            output_config={"effort": EFFORT},
            cache_control={"type": "ephemeral"},
            # If a safety classifier declines, the API retries on a recommended fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )

    def send(self, user_text: str) -> str:
        """Run one user turn through the tool loop and return the reply text."""
        turn_start = len(self.messages)
        self.messages.append({"role": "user", "content": user_text})
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = self._call()

                if response.stop_reason == "refusal":
                    # Drop the whole turn so the conversation can continue cleanly.
                    del self.messages[turn_start:]
                    return "(I can't help with that one. Try rephrasing or ask something else.)"

                # Always append the full content (keeps thinking/tool blocks intact).
                self.messages.append({"role": "assistant", "content": response.content})

                for block in response.content:
                    if block.type == "fallback":
                        print(f"  [answered by fallback model {block.to.model}]")

                if response.stop_reason == "pause_turn":
                    continue  # long server-side search; resend to let it continue

                tool_uses = [b for b in response.content if b.type == "tool_use"]
                if response.stop_reason == "tool_use" and tool_uses:
                    results = []
                    for tu in tool_uses:
                        print(f"  [{tu.name}]")
                        text, is_error = run_tool(tu.name, tu.input)
                        results.append(
                            {"type": "tool_result", "tool_use_id": tu.id, "content": text, "is_error": is_error}
                        )
                    self.messages.append({"role": "user", "content": results})
                    continue

                reply = "".join(b.text for b in response.content if b.type == "text").strip()
                if response.stop_reason == "max_tokens":
                    reply += "\n(…reply was cut off — ask me to continue.)"
                return reply or "(No reply.)"

            return "(Stopped after too many tool steps. Try a more specific request.)"
        except BaseException:
            del self.messages[turn_start:]  # roll back the unfinished turn
            raise


HELP = """\
Commands:
  /tasks     show open tasks         /notes   list saved notes
  /memory    show what I remember    /reset   start a fresh conversation (reloads profile)
  /help      this help               /quit    exit
Anything else is sent to the agent."""


def run_command(cmd: str, agent: Agent) -> str:
    """Run a shared slash command (/tasks, /notes, /memory, /reset) and return its output."""
    if cmd == "/reset":
        agent.reset()
        return "Started a fresh conversation."
    if cmd == "/tasks":
        lines = [
            f"{t['id']}. {t['title']}" + (f"  (due {t['due']})" if t.get("due") else "")
            for t in tasks.load() if not t["done"]
        ]
        return "\n".join(lines) or "No open tasks."
    if cmd == "/notes":
        lines = [
            f"{n['id']}. {n['title']}" + (f"  #{' #'.join(n['tags'])}" if n["tags"] else "")
            for n in notes.load()
        ]
        return "\n".join(lines) or "No notes yet."
    if cmd == "/memory":
        return "\n".join(f"{m['id']}. {m['fact']}" for m in memories.load()) or "Nothing remembered yet."
    return f"Unknown command {cmd}. Type /help."


def handle_command(cmd: str, agent: Agent) -> bool:
    """Handle a slash command in the terminal. Returns False to quit."""
    if cmd in ("/quit", "/exit"):
        return False
    output = HELP if cmd == "/help" else run_command(cmd, agent)
    print("\n".join(f"  {line}" for line in output.splitlines()))
    return True


def main() -> None:
    try:
        agent = Agent()
    except anthropic.AnthropicError as e:
        sys.exit(f"Could not start: {e}\nSet ANTHROPIC_API_KEY (see README.md).")

    print(f"{AGENT_NAME} is ready. Type /help for commands, /quit to exit.\n")
    while True:
        try:
            user_text = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text.startswith("/"):
            if not handle_command(user_text.split()[0].lower(), agent):
                break
            continue

        print(f"{AGENT_NAME.lower()} is thinking…")
        try:
            reply = agent.send(user_text)
        except KeyboardInterrupt:
            print("\n(Interrupted.)")
            continue
        except anthropic.AuthenticationError:
            sys.exit("Your ANTHROPIC_API_KEY is invalid. Check it and try again.")
        except anthropic.RateLimitError:
            print("Rate limited by the API — wait a moment and try again.")
            continue
        except anthropic.APIStatusError as e:
            print(f"API error ({e.status_code}): {e.message}")
            continue
        except anthropic.APIConnectionError:
            print("Network error — check your internet connection.")
            continue
        print(f"\n{AGENT_NAME.lower()} › {reply}\n")


if __name__ == "__main__":
    main()
