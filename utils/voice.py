from __future__ import annotations

import os
from typing import Optional

import discord
from discord.ext import commands

from . import database as db


async def ensure_voice_client(guild: discord.Guild, channel_id: int) -> Optional[discord.VoiceClient]:
    if not guild or not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return None
    vc: Optional[discord.VoiceClient] = guild.voice_client
    try:
        if vc and vc.channel and vc.channel.id == channel.id:
            return vc
        if vc and vc.is_connected():
            await vc.move_to(channel)
            return vc
        return await channel.connect()
    except Exception:
        return None


async def play_for_user(bot: commands.Bot, guild: discord.Guild, user_id: int, key: str) -> bool:
    try:
        user = await db.get_user(user_id)
        prefs = user.get("voice", {})
        if not prefs.get("enabled"):
            return False
        channel_id = int(prefs.get("voice_channel_id", 0))
        sounds = prefs.get("sounds", {})
        path = sounds.get(key)
        if not path or not os.path.exists(path):
            return False
        vc = await ensure_voice_client(guild, channel_id)
        if not vc:
            return False
        if vc.is_playing():
            vc.stop()
        cfg = getattr(bot, "config", {}) if hasattr(bot, "config") else {}
        ffmpeg_exec = cfg.get("ffmpeg_path") or "ffmpeg"
        source = discord.FFmpegPCMAudio(path, executable=ffmpeg_exec)
        vc.play(source)
        return True
    except Exception:
        return False
