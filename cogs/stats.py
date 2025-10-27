from typing import List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds
from utils import gamify


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="profile", description="Show your profile")
    async def profile(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        xp = user.get("xp", 0)
        streak = user.get("streak", 0)
        level, base_xp, next_total = gamify.xp_to_level(int(xp))
        to_next = max(0, int(next_total) - int(xp))
        pomos = int(user.get("pomos_completed", 0))
        ach = len(user.get("achievements", []))
        desc = (
            f"Level: {level}\n"
            f"XP: {xp} (next in {to_next})\n"
            f"Streak: {streak} days\n"
            f"Pomodoros: {pomos}\n"
            f"Achievements: {ach}"
        )
        await interaction.edit_original_response(embed=embeds.base("Your Profile", desc))

    @app_commands.command(name="leaderboard", description="Leaderboard by XP")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Load all users
        from pathlib import Path
        import json
        users_path = (Path(__file__).resolve().parent.parent / "data" / "users.json")
        try:
            users = json.loads(users_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            users = {}
        items: List[Tuple[str, int]] = []
        for uid, u in users.items():
            items.append((uid, int(u.get("xp", 0))))
        items.sort(key=lambda x: x[1], reverse=True)
        lines = []
        for rank, (uid, xp) in enumerate(items[:10], start=1):
            member = interaction.guild.get_member(int(uid)) if interaction.guild else None
            name = member.display_name if member else f"User {uid}"
            lines.append(f"#{rank} {name} — {xp} XP")
        if not lines:
            await interaction.edit_original_response(embed=embeds.warn("No data yet."))
            return
        await interaction.edit_original_response(embed=embeds.base("XP Leaderboard", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
