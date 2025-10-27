from typing import Optional
import discord

PRIMARY = 0x7C3AED
SUCCESS = 0x22C55E
WARN = 0xF59E0B
ERROR = 0xEF4444


def base(title: str, description: str = "", color: int = PRIMARY) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    return e


def pomodoro(title: str, phase: str, progress: str, remaining: str) -> discord.Embed:
    e = base(title)
    e.add_field(name="Phase", value=phase, inline=True)
    e.add_field(name="Time Left", value=remaining, inline=True)
    e.add_field(name="Progress", value=progress, inline=False)
    return e


def success(msg: str) -> discord.Embed:
    return base("Success", msg, SUCCESS)


def warn(msg: str) -> discord.Embed:
    return base("Notice", msg, WARN)


def error(msg: str) -> discord.Embed:
    return base("Error", msg, ERROR)
