from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds
from utils import voice as voiceutil


class Voice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="voice_enable", description="Enable voice reminders and set a voice channel")
    @app_commands.describe(channel="Voice channel for reminders (defaults to your current VC if omitted)")
    async def voice_enable(self, interaction: discord.Interaction, channel: Optional[discord.VoiceChannel] = None):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.edit_original_response(embed=embeds.error("Use in a server."))
            return
        vc = channel
        if vc is None and isinstance(interaction.user, discord.Member):
            vc = interaction.user.voice.channel if interaction.user.voice else None
        if vc is None:
            await interaction.edit_original_response(embed=embeds.warn("Join a voice channel or specify one."))
            return
        user = await db.get_user(interaction.user.id)
        user.setdefault("voice", {})
        user["voice"]["enabled"] = True
        user["voice"]["voice_channel_id"] = vc.id
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success(f"Voice reminders enabled in {vc.name}."))

    @app_commands.command(name="voice_disable", description="Disable voice reminders")
    async def voice_disable(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        user.setdefault("voice", {})
        user["voice"]["enabled"] = False
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success("Voice reminders disabled."))

    @app_commands.command(name="voice_set", description="Set a sound file for a reminder key (focus_start, break_start, session_end)")
    @app_commands.describe(key="Which sound to set", filename="Path to an mp3 on the bot host (e.g. data/voices/focus_start.mp3)")
    @app_commands.choices(key=[
        app_commands.Choice(name="focus_start", value="focus_start"),
        app_commands.Choice(name="break_start", value="break_start"),
        app_commands.Choice(name="session_end", value="session_end"),
    ])
    async def voice_set(self, interaction: discord.Interaction, key: app_commands.Choice[str], filename: str):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        user.setdefault("voice", {})
        sounds = user["voice"].setdefault("sounds", {})
        sounds[key.value] = filename
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success(f"Set {key.value} to {filename}."))

    @app_commands.command(name="voice_test", description="Test-play a voice reminder")
    @app_commands.describe(key="Which sound to play")
    @app_commands.choices(key=[
        app_commands.Choice(name="focus_start", value="focus_start"),
        app_commands.Choice(name="break_start", value="break_start"),
        app_commands.Choice(name="session_end", value="session_end"),
    ])
    async def voice_test(self, interaction: discord.Interaction, key: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        ok = await voiceutil.play_for_user(self.bot, guild, interaction.user.id, key.value)
        if ok:
            await interaction.edit_original_response(embed=embeds.success("Playing."))
        else:
            await interaction.edit_original_response(embed=embeds.warn("Could not play. Ensure voice enabled, channel set, and file exists."))

    @app_commands.command(name="voice_debug", description="Diagnose voice setup and playback readiness")
    async def voice_debug(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        import os, shutil
        guild = interaction.guild
        user = await db.get_user(interaction.user.id)
        prefs = user.get("voice", {})
        enabled = bool(prefs.get("enabled", False))
        channel_id = int(prefs.get("voice_channel_id", 0) or 0)
        sounds = prefs.get("sounds", {})
        ffmpeg = shutil.which("ffmpeg")

        ch = guild.get_channel(channel_id) if guild and channel_id else None
        perms_ok = False
        user_limit_info = "N/A"
        if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)) and guild.me:
            perms = ch.permissions_for(guild.me)
            perms_ok = perms.connect and perms.speak
            if isinstance(ch, discord.VoiceChannel) and ch.user_limit:
                user_limit_info = f"{len(ch.members)}/{ch.user_limit}"
            elif isinstance(ch, discord.VoiceChannel):
                user_limit_info = f"{len(ch.members)}/∞"

        files_status = []
        for k in ("session_start", "focus_start", "break_start", "session_end", "react_warning"):
            p = sounds.get(k)
            files_status.append(f"{k}: {'OK' if (p and os.path.exists(p)) else 'MISSING'} -> {p or '-'}")

        # Try to connect
        connected = False
        connect_error = None
        if guild and channel_id:
            vc = await voiceutil.ensure_voice_client(guild, channel_id)
            connected = vc is not None
            if not connected and isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
                try:
                    temp = await ch.connect(timeout=5)
                    connected = True
                    await temp.disconnect(force=True)
                except Exception as e:
                    connect_error = f"{type(e).__name__}: {e}"

        lines = [
            f"Enabled: {enabled}",
            f"Guild: {guild.name if guild else 'N/A'}",
            f"Channel: {getattr(ch, 'name', 'N/A')} ({channel_id or '-'})",
            f"Permissions OK (connect/speak): {perms_ok}",
            f"Channel occupancy: {user_limit_info}",
            f"FFmpeg found: {bool(ffmpeg)} ({ffmpeg or 'not found in PATH'})",
            f"Connected: {connected}",
            (f"Connect error: {connect_error}" if connect_error else ""),
            "",
            "Files:",
            *files_status,
        ]
        await interaction.edit_original_response(embed=embeds.base("Voice Debug", "\n".join([s for s in lines if s != ""])))


async def setup(bot: commands.Bot):
    await bot.add_cog(Voice(bot))
