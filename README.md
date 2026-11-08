# my-ai-project — your personal AI agent

A personal AI assistant you chat with in the terminal or on Telegram. It is powered by Claude and built around you:

- **Knows you.** It reads `profile.md` (your name, goals, tone, content style) every time it starts.
- **Remembers.** It saves lasting facts you tell it ("I post reels on Tuesdays") to long-term memory and uses them in later chats.
- **Keeps you productive.** It adds, lists and completes your **tasks** and saves **notes** (ideas, drafts, captions).
- **Writes content in your voice.** It brainstorms ideas, hooks, captions and scripts based on your profile.
- **Searches the web** for recent or factual questions.

All your data (memories, tasks, notes) stays on your computer in the `data/` folder, which git ignores.

## Setup (5 minutes)

1. Install Python 3.10 or newer.
2. Get an API key at <https://platform.claude.com> (API keys page). Using the API costs money per message.
3. Install and run:

```bash
git clone https://github.com/hardikrathod0111-dev/my-ai-project.git
cd my-ai-project
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."   # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python -m agent
```

4. **Personalize it:** open `profile.md` and fill in the details about you. The more you write there, especially in "My voice", the more the agent sounds like you.

## Using it

Just talk to it:

```
you › I want to post 3 reels a week about AI tools. Remember that.
you › Give me 5 hook ideas for a reel about free AI image tools
you › Save the 2nd and 4th as a note
you › Remind me to film on Saturday
you › What's on my plate this week?
```

Commands:

| Command   | What it does                                       |
|-----------|----------------------------------------------------|
| `/tasks`  | show open tasks                                    |
| `/notes`  | list saved notes                                   |
| `/memory` | show what the agent remembers about you            |
| `/reset`  | start a fresh conversation (reloads `profile.md`)  |
| `/quit`   | exit                                               |

## Chat from your phone (Telegram)

1. In Telegram, message **@BotFather**, send `/newbot`, and follow the steps. It gives you a **bot token** like `123456:ABC...`. Keep it secret.
2. Message **@userinfobot** to get your numeric **user id** (e.g. `123456789`).
3. On your computer, run:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_ALLOWED_USERS="123456789"   # only these users can talk to the bot
python -m agent.telegram_bot
```

4. Open your bot in Telegram and send `/start`. The `/tasks`, `/notes`, `/memory` and `/reset` commands appear in the bot's menu.

Notes:
- The bot only works **while this command is running**. To keep it on 24/7, run it on an always-on computer or a small cloud server (e.g. a $5/month VPS, Railway, or Render).
- The bot ignores anyone who isn't in `TELEGRAM_ALLOWED_USERS`, because it can see your memories, tasks and notes. If someone else messages it, they're told their user id so you can add them if you want.
- The terminal and Telegram share the same memories, tasks and notes (the `data/` folder), so you can use both.

## Settings (optional environment variables)

| Variable        | Default           | Meaning                                                             |
|-----------------|-------------------|---------------------------------------------------------------------|
| `AGENT_NAME`    | `Jarvis`          | what your assistant is called                                       |
| `AGENT_EFFORT`  | `medium`          | how hard it thinks: `low` (fast, cheaper), `medium`, `high`, `xhigh`, `max` |
| `AGENT_MODEL`   | `claude-opus-5-5` | which Claude model to use                                           |
| `AGENT_DATA_DIR`| `./data`          | where memories, tasks and notes are stored                          |

## How it works

```
profile.md + memories + open tasks ──► system prompt
                                         │
you ──► agent/main.py ──► Claude API ──► reply
                              │  ▲
              tool calls      ▼  │ results
                         agent/tools.py ──► data/*.json
```

- `agent/main.py` is the chat loop. It sends your message to Claude, runs any tools Claude asks for, and repeats until Claude replies.
- `agent/telegram_bot.py` connects the same agent to Telegram (one conversation per chat).
- `agent/tools.py` holds the tools (memory, tasks, notes, clock). To give your agent a new ability, add a definition to `TOOL_DEFINITIONS` and a handler function to `_HANDLERS`.
- `agent/storage.py` saves everything as plain JSON files you can open and edit.

If Claude's safety filter declines a request, the agent automatically retries it on a recommended fallback model.
