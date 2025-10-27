import datetime as dt
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds


def _format_top(top: List[dict], guild: Optional[discord.Guild]) -> str:
    if not top:
        return "No data."
    lines = []
    for i, r in enumerate(top, start=1):
        uid = r.get("user_id")
        name = f"<@{uid}>"
        if guild:
            m = guild.get_member(int(uid))
            if m:
                name = m.display_name
        lines.append(f"{i}. {name} — {r.get('monthly_xp', 0)} XP")
    return "\n".join(lines)


class Seasons(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="theme_set", description="Set your embed theme")
    @app_commands.describe(theme="Choose a theme")
    @app_commands.choices(theme=[
        app_commands.Choice(name="aurora", value="aurora"),
        app_commands.Choice(name="midnight", value="midnight"),
        app_commands.Choice(name="solar", value="solar"),
    ])
    async def theme_set(self, interaction: discord.Interaction, theme: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        user["theme"] = theme.value
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success(f"Theme set to {theme.value}."))

    @app_commands.command(name="season_stats", description="Your season (monthly) XP and top 10")
    async def season_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        import json
        from pathlib import Path
        users_path = (Path(__file__).resolve().parent.parent / "data" / "users.json")
        try:
            users = json.loads(users_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            users = {}
        # Rank
        ranking = []
        for uid, u in users.items():
            ranking.append({"user_id": int(uid), "monthly_xp": int(u.get("monthly_xp", 0)), "xp": int(u.get("xp", 0))})
        ranking.sort(key=lambda r: (-r["monthly_xp"], -r["xp"]))
        top10 = ranking[:10]
        # Find user rank
        rank = next((i + 1 for i, r in enumerate(ranking) if r["user_id"] == interaction.user.id), None)
        you = next((r for r in ranking if r["user_id"] == interaction.user.id), {"monthly_xp": 0})
        desc = [
            f"Your monthly XP: {you.get('monthly_xp', 0)}",
            f"Rank: {rank or 'N/A'}",
            "",
            "Top 10:",
            _format_top(top10, interaction.guild),
        ]
        await interaction.edit_original_response(embed=embeds.base("Season Stats", "\n".join(desc)))

    @app_commands.command(name="hall_of_fame", description="View a past month's top performers")
    @app_commands.describe(month="Month label YYYY-MM (default: previous month)")
    async def hall_of_fame(self, interaction: discord.Interaction, month: Optional[str] = None):
        await interaction.response.defer(ephemeral=True)
        now = dt.datetime.utcnow()
        if not month:
            first = now.replace(day=1)
            prev = first - dt.timedelta(days=1)
            month = prev.strftime("%Y-%m")
        hof = await db.get_hof()
        top = hof.get(month, [])
        if not top:
            await interaction.edit_original_response(embed=embeds.warn("No snapshot for that month yet."))
            return
        await interaction.edit_original_response(embed=embeds.base(f"Hall of Fame — {month}", _format_top(top, interaction.guild)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Seasons(bot))
