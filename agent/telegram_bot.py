"""Telegram front end for your personal AI agent.

Run with:  python -m agent.telegram_bot

Needs TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_ALLOWED_USERS
(your numeric Telegram user id; comma-separate several). The bot ignores
everyone else, because it has access to your memories, tasks and notes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import anthropic
from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .main import AGENT_NAME, Agent, run_command

TELEGRAM_LIMIT = 4096  # max characters in one Telegram message

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log request URLs (they contain the token)
log = logging.getLogger("agent.telegram")


def _allowed_users() -> set[int]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    try:
        return {int(x) for x in raw.replace(" ", "").split(",") if x}
    except ValueError:
        sys.exit("TELEGRAM_ALLOWED_USERS must be numeric Telegram user ids, comma-separated.")


ALLOWED_USERS = _allowed_users()

# One conversation per chat; a lock per chat so messages are answered one at a time.
_agents: dict[int, Agent] = {}
_locks: dict[int, asyncio.Lock] = {}


def _agent_for(chat_id: int) -> Agent:
    if chat_id not in _agents:
        _agents[chat_id] = Agent()
        _locks[chat_id] = asyncio.Lock()
    return _agents[chat_id]


def _split(text: str) -> list[str]:
    """Split a long reply into Telegram-sized chunks, preferring line breaks."""
    chunks = []
    while len(text) > TELEGRAM_LIMIT:
        cut = text.rfind("\n", 0, TELEGRAM_LIMIT)
        if cut <= 0:
            cut = TELEGRAM_LIMIT
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    return chunks


async def _authorized(update: Update) -> bool:
    user = update.effective_user
    if user and user.id in ALLOWED_USERS:
        return True
    if update.effective_message:
        await update.effective_message.reply_text(
            "Sorry, this is a private assistant.\n"
            f"(Your Telegram user id is {user.id if user else 'unknown'} — the owner can add it to "
            "TELEGRAM_ALLOWED_USERS.)"
        )
    log.warning("Ignored message from unauthorized user %s", user.id if user else None)
    return False


async def _keep_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    # Telegram's "typing…" indicator lasts ~5s, so refresh it while the agent works.
    while True:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(4)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    chat_id = update.effective_chat.id
    agent = _agent_for(chat_id)
    async with _locks[chat_id]:
        typing = asyncio.create_task(_keep_typing(context, chat_id))
        try:
            reply = await asyncio.to_thread(agent.send, update.message.text)
        except anthropic.AuthenticationError:
            reply = "My ANTHROPIC_API_KEY is invalid. Check it on the computer running the bot."
        except anthropic.RateLimitError:
            reply = "I'm being rate limited — try again in a minute."
        except anthropic.APIStatusError as e:
            log.error("API error %s: %s", e.status_code, e.message)
            reply = f"API error ({e.status_code}). Try again in a moment."
        except anthropic.APIConnectionError:
            reply = "I can't reach the Claude API right now — check the internet connection."
        finally:
            typing.cancel()
    for chunk in _split(reply):
        await update.message.reply_text(chunk)


async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _authorized(update):
        return
    cmd = update.message.text.split()[0].split("@")[0].lower()  # "/tasks@MyBot" -> "/tasks"
    if cmd in ("/start", "/help"):
        text = (
            f"Hi! I'm {AGENT_NAME}, your personal assistant. Just send me a message.\n\n"
            "/tasks – open tasks\n/notes – saved notes\n/memory – what I remember\n"
            "/reset – start a fresh conversation"
        )
    else:
        chat_id = update.effective_chat.id
        agent = _agent_for(chat_id)
        async with _locks[chat_id]:
            text = run_command(cmd, agent)
    for chunk in _split(text):
        await update.message.reply_text(chunk)


async def _set_menu(app: Application) -> None:
    await app.bot.set_my_commands([
        BotCommand("tasks", "Show open tasks"),
        BotCommand("notes", "List saved notes"),
        BotCommand("memory", "What I remember about you"),
        BotCommand("reset", "Start a fresh conversation"),
        BotCommand("help", "How to use me"),
    ])


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Set TELEGRAM_BOT_TOKEN (get one from @BotFather on Telegram). See README.md.")
    if not ALLOWED_USERS:
        sys.exit(
            "Set TELEGRAM_ALLOWED_USERS to your numeric Telegram user id so only you can use the bot.\n"
            "Get your id by messaging @userinfobot on Telegram. See README.md."
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY is not set — replies will fail unless another credential is configured.")

    app = Application.builder().token(token).post_init(_set_menu).build()
    app.add_handler(CommandHandler(["start", "help", "tasks", "notes", "memory", "reset"], on_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    log.info("%s is running on Telegram. Press Ctrl+C to stop.", AGENT_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
