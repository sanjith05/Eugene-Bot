import io
import time
import datetime as dt
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db


class Analytics(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _render_bar(self, labels: List[str], values: List[int], title: str) -> bytes:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 3))
        ax.bar(labels, values, color="#7C3AED")
        ax.set_title(title)
        ax.set_ylabel("Count")
        ax.set_xlabel("")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=160)
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    @app_commands.command(name="time_of_day", description="Show your focus completions by hour of day")
    async def time_of_day(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        logs: List[int] = list(user.get("focus_log", []))
        if not logs:
            await interaction.edit_original_response(content="No focus data yet.")
            return
        # Build 24-bin histogram local time
        counts = [0] * 24
        for ts in logs:
            h = dt.datetime.fromtimestamp(int(ts)).hour
            counts[h] += 1
        labels = [f"{h:02d}" for h in range(24)]
        img = self._render_bar(labels, counts, title="Completions by Hour")
        file = discord.File(io.BytesIO(img), filename="time_of_day.png")
        await interaction.edit_original_response(content="Completions by hour", attachments=[file])

    @app_commands.command(name="weekly_report", description="Your last 7 days of Pomodoro completions")
    async def weekly_report(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        logs: List[int] = list(user.get("focus_log", []))
        if not logs:
            await interaction.edit_original_response(content="No focus data yet.")
            return
        now = int(time.time())
        start = now - 6 * 86400
        day_counts = [0] * 7
        day_labels = []
        for i in range(7):
            d = dt.datetime.fromtimestamp(start + i * 86400)
            day_labels.append(d.strftime("%a"))
        for ts in logs:
            if ts < start:
                continue
            idx = int((ts - start) // 86400)
            if 0 <= idx < 7:
                day_counts[idx] += 1
        img = self._render_bar(day_labels, day_counts, title="Last 7 Days (Pomodoro Completions)")
        total = sum(day_counts)
        file = discord.File(io.BytesIO(img), filename="weekly_report.png")
        await interaction.edit_original_response(content=f"Total this week: {total}", attachments=[file])


async def setup(bot: commands.Bot):
    await bot.add_cog(Analytics(bot))
