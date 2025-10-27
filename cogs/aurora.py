import time
import datetime as dt
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds


class Aurora(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="aurora_tip", description="Get a motivational tip based on your recent activity")
    async def aurora_tip(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        xp = int(user.get("xp", 0))
        streak = int(user.get("streak", 0))
        pomos = int(user.get("pomos_completed", 0))
        last_focus = int(user.get("last_focus_ts", 0))
        now = int(time.time())
        hour = dt.datetime.fromtimestamp(now).hour
        logs: List[int] = list(user.get("focus_log", []))

        parts: List[str] = []
        if hour < 9:
            parts.append("Early start sets the tone. Try a short 25/5 to build momentum.")
        elif 12 <= hour < 14:
            parts.append("Post-lunch dip? Keep focus light. One cycle is enough to regain rhythm.")
        elif hour >= 20:
            parts.append("Evening focus can be powerful—protect your sleep with a hard stop time.")

        if streak >= 7:
            parts.append(f"Your {streak}-day streak is paying off. Keep consistency the priority.")
        elif streak >= 3:
            parts.append("Great streak forming. Small daily wins beat long sprints.")

        if pomos < 10:
            parts.append("Focus on finishing, not perfection. One more Pomodoro today.")
        else:
            parts.append("Increase challenge slightly—try adding a review Pomodoro after work.")

        if last_focus and now - last_focus > 4 * 3600:
            parts.append("It’s been a while. Start a fresh 25/5 to reset.")

        if logs:
            hours = [dt.datetime.fromtimestamp(int(ts)).hour for ts in logs]
            peak = max(range(24), key=lambda h: hours.count(h))
            parts.append(f"You tend to finish most around {peak:02d}:00—schedule a block then.")

        msg = " \n• ".join([parts[0]] + parts[1:]) if parts else "Let’s begin with a single 25/5. You’ve got this."
        await interaction.edit_original_response(embed=embeds.base("Aurora · Tip", f"• {msg}"))

    @app_commands.command(name="weekly_reflection", description="Summary of your last 7 days")
    async def weekly_reflection(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        logs: List[int] = list(user.get("focus_log", []))
        if not logs:
            await interaction.edit_original_response(embed=embeds.warn("No data yet. Try finishing a Pomodoro."))
            return
        now = int(time.time())
        start = now - 6 * 86400
        per_day = [0] * 7
        for ts in logs:
            if ts < start:
                continue
            idx = int((ts - start) // 86400)
            if 0 <= idx < 7:
                per_day[idx] += 1
        total = sum(per_day)
        best = max(range(7), key=lambda i: per_day[i])
        best_day = (dt.datetime.fromtimestamp(start) + dt.timedelta(days=best)).strftime("%A")
        lines = [
            f"Total Pomodoros: {total}",
            f"Best day: {best_day} ({per_day[best]})",
            "Focus plan: aim for 1 more Pomodoro on weaker days to smooth consistency.",
        ]
        await interaction.edit_original_response(embed=embeds.base("Aurora · Weekly Reflection", "\n".join(lines)))

    @app_commands.command(name="aurora_goal", description="Get a suggested daily Pomodoro goal based on your trends")
    async def aurora_goal(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        logs: List[int] = list(user.get("focus_log", []))
        if not logs:
            await interaction.edit_original_response(embed=embeds.base("Aurora · Goal", "Start with 3 Pomodoros today."))
            return
        now = int(time.time())
        start = now - 14 * 86400
        recent = [ts for ts in logs if ts >= start]
        days = max(1, int((now - start) // 86400))
        avg = len(recent) / days
        goal = max(3, int(round(avg + 1)))
        await interaction.edit_original_response(embed=embeds.base("Aurora · Goal", f"Target {goal} Pomodoros today. Adjust if you finish early."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Aurora(bot))
