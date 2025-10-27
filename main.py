import json
import os
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

CONFIG_PATH = Path(__file__).parent / "config.json"
DATA_DIR = Path(__file__).parent / "data"
COGS = [
    "cogs.pomodoro",
    "cogs.todos",
    "cogs.stats",
    "cogs.reminders",
    "cogs.events",
    "cogs.community",
    "cogs.analytics",
    "cogs.aurora",
    "cogs.shop",
    "cogs.seasons",
]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aurorafocus")


def load_config():
    if not CONFIG_PATH.exists():
        # Provide safe defaults when running on platforms like Render
        return {
            "guild_ids": [],
            "default_pomodoro": {"focus": 25, "short_break": 5, "long_break": 15, "cycles": 4},
            "update_interval_sec": 5,
            "prefix": "/",
        }
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def setup_bot():
    config = load_config()

    intents = discord.Intents.default()
    intents.members = True

    bot = commands.Bot(command_prefix=config.get("prefix", "/"), intents=intents)
    bot.config = config  # type: ignore[attr-defined]

    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
        # Sync slash commands
        try:
            guild_ids = config.get("guild_ids", [])
            if guild_ids:
                for gid in guild_ids:
                    guild = discord.Object(id=int(gid))
                    await bot.tree.sync(guild=guild)
                logger.info("Synced commands to development guilds")
            else:
                await bot.tree.sync()
                logger.info("Synced commands globally")
        except Exception as e:
            logger.exception("Command sync failed: %s", e)

    # Load cogs
    for ext in COGS:
        try:
            await bot.load_extension(ext)
            logger.info("Loaded extension %s", ext)
        except Exception:
            logger.exception("Failed to load extension %s", ext)

    return bot


def main():
    config = load_config()
    token = os.getenv("DISCORD_TOKEN") or config.get("token")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Discord token not set. Set DISCORD_TOKEN env var (preferred) or add 'token' in config.json.")

    async def runner():
        bot = await setup_bot()
        await bot.start(token)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
