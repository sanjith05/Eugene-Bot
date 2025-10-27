import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds
from utils.timeutils import progress_bar


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Focus Party (creates a temporary voice channel and a discussion thread)
    @app_commands.command(name="party_start", description="Start a Focus Party: creates a voice room and a thread")
    @app_commands.describe(name="Name for the party", minutes="Optional duration hint for title")
    async def party_start(self, interaction: discord.Interaction, name: Optional[str] = None, minutes: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.edit_original_response(embed=embeds.error("Use in a server."))
            return
        # Create a voice channel under same category if possible
        category = None
        if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            parent = getattr(interaction.channel, "category", None)
            if isinstance(parent, discord.CategoryChannel):
                category = parent
        vc_name = f"🎯 Focus Party"
        if name:
            vc_name += f" · {name[:40]}"
        if minutes:
            vc_name += f" · {int(minutes)}m"
        try:
            voice = await guild.create_voice_channel(vc_name, category=category, reason="Start Focus Party")
        except discord.Forbidden:
            await interaction.edit_original_response(embed=embeds.error("I need Manage Channels to create voice rooms."))
            return
        # Create a thread from current message context (private if in private channel not supported)
        thread = None
        if isinstance(interaction.channel, discord.TextChannel):
            try:
                starter = await interaction.channel.send(f"Party created: join {voice.mention}! Use /pomodoro to start a shared timer in this channel.")
                thread = await starter.create_thread(name=f"🧠 Focus · {name[:60] if name else 'Session'}")
            except Exception:
                thread = None
        await interaction.edit_original_response(embed=embeds.success(f"Focus Party ready: {voice.name}{' with thread' if thread else ''}."))

    # Weekly Challenge (global simple)
    @app_commands.command(name="challenge_set", description="Set the server weekly challenge goal (admin)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def challenge_set(self, interaction: discord.Interaction, goal: int):
        await interaction.response.defer(ephemeral=True)
        goal = max(0, int(goal))
        ch = await db.get_challenge()
        ch["goal"] = goal
        if ch.get("progress", 0) > goal:
            ch["progress"] = goal
        await db.set_challenge(ch)
        await interaction.edit_original_response(embed=embeds.success(f"Weekly challenge set to {goal} pomodoros."))

    @app_commands.command(name="challenge", description="Show current weekly challenge progress")
    async def challenge(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ch = await db.get_challenge()
        goal = max(1, int(ch.get("goal", 0)) or 1)
        progress = int(ch.get("progress", 0))
        ratio = min(1.0, progress / goal)
        bar = progress_bar(ratio, 24)
        desc = f"Goal: {progress}/{goal}\n{bar}"
        await interaction.edit_original_response(embed=embeds.base("Weekly Challenge", desc))

    # Partner Mode
    @app_commands.command(name="partner_set", description="Pair with another user for accountability")
    async def partner_set(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True)
        if user.id == interaction.user.id:
            await interaction.edit_original_response(embed=embeds.warn("You cannot partner with yourself."))
            return
        await db.set_partner(interaction.user.id, user.id)
        # DM the selected user about the new partnership
        dm_sent = False
        try:
            guild_name = interaction.guild.name if interaction.guild else "this server"
            initiator = interaction.user.display_name
            await user.send(f"🤝 You have been partnered with {initiator} in {guild_name}. Stay accountable and happy focusing!")
            dm_sent = True
        except Exception:
            dm_sent = False
        note = " (DM sent)" if dm_sent else " (DM could not be delivered — user may have DMs disabled)"
        await interaction.edit_original_response(embed=embeds.success(f"You are now partners with {user.display_name}.{note}"))

    @app_commands.command(name="partner_clear", description="Unpair your partner")
    async def partner_clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await db.clear_partner(interaction.user.id)
        await interaction.edit_original_response(embed=embeds.success("Partner cleared."))

    @app_commands.command(name="partner_status", description="Show your current partner (if any)")
    async def partner_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        pid = await db.find_partner(interaction.user.id)
        if not pid:
            await interaction.edit_original_response(embed=embeds.warn("No partner set."))
            return
        member = interaction.guild.get_member(pid) if interaction.guild else None
        name = member.display_name if member else f"User {pid}"
        await interaction.edit_original_response(embed=embeds.base("Partner", f"You are paired with {name}."))

    # Admin-only per-guild sync: instantly registers slash commands in this server
    @app_commands.command(name="sync_here", description="Admin: force slash command sync in this server")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def sync_here(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.edit_original_response(embed=embeds.error("Use in a server."))
            return
        try:
            await self.bot.tree.sync(guild=interaction.guild)
            await interaction.edit_original_response(embed=embeds.success("Synced commands to this server."))
        except Exception as e:
            await interaction.edit_original_response(embed=embeds.error("Sync failed."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
