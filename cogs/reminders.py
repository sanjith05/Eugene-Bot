import asyncio
import time
from pathlib import Path
import json

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import embeds


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.inactivity_check.start()

    def cog_unload(self):
        self.inactivity_check.cancel()

    @app_commands.command(name="remindme", description="Remind you after N minutes with a message")
    @app_commands.describe(minutes="Delay in minutes", message="Reminder text")
    async def remindme(self, interaction: discord.Interaction, minutes: int, message: str):
        await interaction.response.defer(ephemeral=True)
        minutes = max(1, minutes)
        await interaction.edit_original_response(embed=embeds.success(f"Okay, I'll remind you in {minutes} minutes."))
        async def task():
            await asyncio.sleep(minutes * 60)
            try:
                await interaction.user.send(f"⏰ Reminder: {message}")
            except Exception:
                pass
        self.bot.loop.create_task(task())

    # Smart reminder preferences
    @app_commands.command(name="reminder_prefs", description="Set inactivity reminder preferences")
    @app_commands.describe(enable="Enable/disable smart inactivity reminders", inactivity_hours="Hours of inactivity before a nudge (2-8)", quiet_start="Quiet hours start (0-23)", quiet_end="Quiet hours end (0-23)")
    async def reminder_prefs(self, interaction: discord.Interaction, enable: bool, inactivity_hours: int = 4, quiet_start: int = 0, quiet_end: int = 6):
        await interaction.response.defer(ephemeral=True)
        inactivity_hours = max(2, min(8, inactivity_hours))
        quiet_start = max(0, min(23, quiet_start))
        quiet_end = max(0, min(23, quiet_end))

        users_path = (Path(__file__).resolve().parent.parent / "data" / "users.json")
        try:
            data = json.loads(users_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}
        u = data.get(str(interaction.user.id), {})
        u["reminders_enabled"] = bool(enable)
        u["inactivity_hours"] = inactivity_hours
        u["quiet_start"] = quiet_start
        u["quiet_end"] = quiet_end
        data[str(interaction.user.id)] = u
        users_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        await interaction.edit_original_response(embed=embeds.success("Reminder preferences saved."))

    @tasks.loop(minutes=15)
    async def inactivity_check(self):
        await self.bot.wait_until_ready()
        users_path = (Path(__file__).resolve().parent.parent / "data" / "users.json")
        try:
            data = json.loads(users_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            data = {}
        now = int(time.time())
        for uid, u in list(data.items()):
            try:
                if not u.get("reminders_enabled", False):
                    continue
                last_focus = int(u.get("last_focus_ts", 0))
                inactivity_hours = int(u.get("inactivity_hours", 4))
                quiet_start = int(u.get("quiet_start", 0))
                quiet_end = int(u.get("quiet_end", 6))
                last_nudge = int(u.get("last_nudge_ts", 0))
                # Quiet hours window check (wrap supported)
                hour = int(time.localtime(now).tm_hour)
                in_quiet = (quiet_start <= quiet_end and quiet_start <= hour < quiet_end) or (
                    quiet_start > quiet_end and (hour >= quiet_start or hour < quiet_end)
                )
                if in_quiet:
                    continue
                if last_focus and now - last_focus < inactivity_hours * 3600:
                    continue
                if last_nudge and now - last_nudge < 3600:
                    continue
                member = None
                # Try DM via any guild the bot shares; fallback to creating a DM by ID
                for g in self.bot.guilds:
                    m = g.get_member(int(uid))
                    if m:
                        member = m
                        break
                if member is None:
                    continue
                try:
                    await member.send("👋 Haven’t seen a focus in a while — want to start a Pomodoro? Try /pomodoro or /preset_use.")
                    u["last_nudge_ts"] = now
                    data[uid] = u
                except Exception:
                    pass
            except Exception:
                pass
        try:
            users_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
