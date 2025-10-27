import asyncio
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds
from utils.timeutils import progress_bar, format_duration
from utils import gamify


class Pomodoro(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_interval = int(getattr(bot, "config", {}).get("update_interval_sec", 5))

    async def _start_session(self, target_channel: discord.abc.Messageable, owner: discord.User,
                             focus: int, short_break: int, long_break: int, cycles: int) -> discord.Message:
        channel_id = target_channel.id  # threads and text channels both have id
        session = {
            "phase": "focus",
            "focus": int(focus),
            "short_break": int(short_break),
            "long_break": int(long_break),
            "cycles": int(cycles),
            "current_cycle": 1,
            "started_at": time.time(),
            "ends_at": time.time() + int(focus) * 60,
            "paused": False,
            "owner_id": owner.id,
        }
        await db.set_session(channel_id, session)

        try:
            await db.update_user(owner.id, {"afk_strikes": 0})
        except Exception:
            pass

        # Send initial message
        msg = await target_channel.send(embed=self._build_embed(session))
        self.bot.loop.create_task(self._ticker(msg, channel_id))
        return msg

    @app_commands.command(name="pomodoro", description="Start a Pomodoro session in this channel")
    @app_commands.describe(
        focus="Focus minutes",
        short_break="Short break minutes",
        long_break="Long break minutes",
        cycles="Number of focus cycles before a long break",
    )
    async def pomodoro(self, interaction: discord.Interaction, focus: Optional[int] = None,
                       short_break: Optional[int] = None, long_break: Optional[int] = None,
                       cycles: Optional[int] = None):
        await interaction.response.defer(thinking=False, ephemeral=True)
        cfg = getattr(self.bot, "config", {})
        defaults = cfg.get("default_pomodoro", {"focus": 25, "short_break": 5, "long_break": 15, "cycles": 4})
        focus = focus or defaults["focus"]
        short_break = short_break or defaults["short_break"]
        long_break = long_break or defaults["long_break"]
        cycles = cycles or defaults["cycles"]

        channel_id = interaction.channel_id
        existing = await db.get_session(channel_id)
        target_channel = interaction.channel
        if existing:
            # Create a thread to allow parallel sessions
            try:
                base_name = f"Pomodoro · {focus}/{short_break} ×{cycles} · {interaction.user.display_name}"
                thread = await interaction.channel.create_thread(name=base_name, auto_archive_duration=60)
                target_channel = thread
            except Exception:
                await interaction.edit_original_response(embed=embeds.warn("A session is running here and I couldn't create a thread. Try another channel/thread."))
                return
        await self._start_session(target_channel, interaction.user, focus, short_break, long_break, cycles)
        await interaction.edit_original_response(embed=embeds.success(f"Started in {'thread' if isinstance(target_channel, discord.Thread) else 'channel'}: {getattr(target_channel, 'name', '')}"))

    @app_commands.command(name="pomodoro_quick", description="Quick start with common presets (spawns thread if needed)")
    @app_commands.describe(preset="Choose focus/break pair", cycles="Cycles before a long break")
    @app_commands.choices(preset=[
        app_commands.Choice(name="25/5", value="25/5/15"),
        app_commands.Choice(name="50/10", value="50/10/15"),
        app_commands.Choice(name="75/25", value="75/25/20"),
        app_commands.Choice(name="90/30", value="90/30/20"),
    ])
    async def pomodoro_quick(self, interaction: discord.Interaction, preset: app_commands.Choice[str], cycles: Optional[int] = 4):
        await interaction.response.defer(ephemeral=True)
        try:
            focus_s, sb_s, lb_s = preset.value.split("/")
            focus = int(focus_s)
            short_break = int(sb_s)
            long_break = int(lb_s)
        except Exception:
            await interaction.edit_original_response(embed=embeds.error("Invalid preset."))
            return
        # Reuse main logic: thread if occupied
        existing = await db.get_session(interaction.channel_id)
        target_channel = interaction.channel
        if existing:
            try:
                name = f"Pomodoro · {focus}/{short_break} ×{cycles} · {interaction.user.display_name}"
                thread = await interaction.channel.create_thread(name=name, auto_archive_duration=60)
                target_channel = thread
            except Exception:
                await interaction.edit_original_response(embed=embeds.warn("A session is running here and I couldn't create a thread. Try another channel/thread."))
                return
        await self._start_session(target_channel, interaction.user, focus, short_break, long_break, cycles or 4)
        await interaction.edit_original_response(embed=embeds.success(f"Started in {'thread' if isinstance(target_channel, discord.Thread) else 'channel'}: {getattr(target_channel, 'name', '')}"))

    async def _ticker(self, message: discord.Message, channel_id: int):
        try:
            while True:
                session = await db.get_session(channel_id)
                if not session:
                    break
                if session.get("paused"):
                    try:
                        await message.edit(embed=self._build_embed(session))
                    except discord.HTTPException:
                        pass
                    await asyncio.sleep(self.update_interval)
                    continue

                now = time.time()
                remaining = int(session["ends_at"] - now)
                if remaining <= 0:
                    # Focus completed -> grant XP and track pomo
                    completed_focus = (session.get("phase") == "focus")
                    owner_id = session.get("owner_id")
                    channel = message.channel if hasattr(message, "channel") else None
                    guild = channel.guild if channel and hasattr(channel, "guild") else None

                    prev_phase = session.get("phase")
                    session = await self._advance_phase(session)
                    await db.set_session(channel_id, session)
                    if completed_focus and owner_id:
                        try:
                            await gamify.record_focus_completion(int(owner_id))
                            try:
                                await db.update_user(int(owner_id), {"last_focus_ts": int(now)})
                            except Exception:
                                pass
                            # Append to focus_log (bounded)
                            try:
                                user = await db.get_user(int(owner_id))
                                log = list(user.get("focus_log", []))
                                log.append(int(now))
                                if len(log) > 1000:
                                    log = log[-1000:]
                                user["focus_log"] = log
                                await db.set_user(int(owner_id), user)
                            except Exception:
                                pass
                            res = await gamify.grant_xp_and_check(self.bot, int(owner_id), delta=15, guild=guild)
                            granted = await gamify.check_basic_achievements(self.bot, int(owner_id), when_ts=now)
                            # Coins reward
                            try:
                                u = await db.get_user(int(owner_id))
                                u["coins"] = int(u.get("coins", 0)) + 5
                                await db.set_user(int(owner_id), u)
                            except Exception:
                                pass
                            # Increment server challenge progress
                            try:
                                await db.increment_challenge(1)
                            except Exception:
                                pass
                            # Partner notification
                            try:
                                partner_id = await db.find_partner(int(owner_id))
                                if partner_id and channel:
                                    member = channel.guild.get_member(partner_id) if guild else None
                                    if member:
                                        await channel.send(f"🤝 Partner update: {member.mention}, your buddy just completed a focus session!")
                            except Exception:
                                pass
                            # Announce level-up or achievements
                            texts = []
                            if res.get("leveled_up"):
                                texts.append(f"🎉 Level Up! You reached Level {res.get('new_level')}.")
                            if granted:
                                texts.append("Achievements: " + ", ".join(granted))
                            if texts and channel:
                                try:
                                    await channel.send(" ".join(texts))
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    # AFK check at end of phase that ends the whole session
                    if session.get("phase") not in ("short_break", "long_break") and owner_id and channel:
                        try:
                            prompt = await channel.send(f"{message.author.mention if hasattr(message, 'author') else ''} <@{owner_id}> session ended. React with ✅ within 30s to confirm.")
                            try:
                                await prompt.add_reaction("✅")
                            except Exception:
                                pass
                            def check(reaction, user):
                                return reaction.message.id == prompt.id and str(reaction.emoji) == "✅" and user and user.id == owner_id
                            reacted = False
                            try:
                                reaction, user = await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
                                reacted = True
                            except asyncio.TimeoutError:
                                reacted = False
                            u = await db.get_user(int(owner_id))
                            strikes = int(u.get("afk_strikes", 0))
                            if reacted:
                                strikes = 0
                            else:
                                strikes += 1
                            u["afk_strikes"] = strikes
                            await db.set_user(int(owner_id), u)
                            if not reacted and strikes >= 3:
                                # Disconnect from VC if present
                                try:
                                    if guild:
                                        member = guild.get_member(int(owner_id))
                                        if member and member.voice and member.voice.channel:
                                            await member.move_to(None, reason="AFK strikes reached")
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    await asyncio.sleep(1)
                else:
                    try:
                        await message.edit(embed=self._build_embed(session))
                    except discord.HTTPException:
                        pass
                    await asyncio.sleep(self.update_interval)
        finally:
            # Try clean up embed when session ends
            try:
                await message.edit(embed=embeds.success("Session ended."))
            except Exception:
                pass

    async def _advance_phase(self, session: dict) -> dict:
        phase = session["phase"]
        if phase == "focus":
            if session["current_cycle"] % session["cycles"] == 0:
                session["phase"] = "long_break"
                duration = session["long_break"]
            else:
                session["phase"] = "short_break"
                duration = session["short_break"]
            session["ends_at"] = time.time() + duration * 60
        else:
            # break -> next focus
            if phase in ("short_break", "long_break"):
                if phase == "long_break":
                    session["current_cycle"] = 1
                else:
                    session["current_cycle"] += 1
                session["phase"] = "focus"
                duration = session["focus"]
                session["ends_at"] = time.time() + duration * 60
        return session

    def _build_embed(self, session: dict) -> discord.Embed:
        phase = session["phase"].replace("_", " ").title()
        total = session["focus"] * 60 if session["phase"] == "focus" else (
            session["short_break"] * 60 if session["phase"] == "short_break" else session["long_break"] * 60
        )
        if session.get("paused"):
            remaining = int(session.get("pause_remaining", max(0, int(session["ends_at"] - time.time()))))
        else:
            remaining = max(0, int(session["ends_at"] - time.time()))
        ratio = 1 - (remaining / total if total else 1)
        bar = progress_bar(ratio, 24)
        title = f"AuroraFocus · Cycle {session['current_cycle']}/{session['cycles']}"
        if session.get("paused"):
            title += " · Paused"
        return embeds.pomodoro(
            title=title,
            phase=phase,
            progress=bar,
            remaining=format_duration(remaining),
        )

    @app_commands.command(name="pomodoro_stop", description="Stop the current Pomodoro session in this channel")
    async def pomodoro_stop(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=False, ephemeral=True)
        session = await db.get_session(interaction.channel_id)
        if not session:
            await interaction.edit_original_response(embed=embeds.warn("No active session in this channel."))
            return
        await db.delete_session(interaction.channel_id)
        await interaction.edit_original_response(embed=embeds.success("Stopped the session."))

    @app_commands.command(name="pomodoro_pause", description="Pause the current Pomodoro session")
    async def pomodoro_pause(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        session = await db.get_session(interaction.channel_id)
        if not session:
            await interaction.edit_original_response(embed=embeds.warn("No active session."))
            return
        if session.get("paused"):
            await interaction.edit_original_response(embed=embeds.warn("Session is already paused."))
            return
        remaining = max(0, int(session["ends_at"] - time.time()))
        session["paused"] = True
        session["pause_remaining"] = remaining
        await db.set_session(interaction.channel_id, session)
        await interaction.edit_original_response(embed=embeds.success("Paused."))

    @app_commands.command(name="pomodoro_resume", description="Resume the current Pomodoro session")
    async def pomodoro_resume(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        session = await db.get_session(interaction.channel_id)
        if not session:
            await interaction.edit_original_response(embed=embeds.warn("No active session."))
            return
        if not session.get("paused"):
            await interaction.edit_original_response(embed=embeds.warn("Session is not paused."))
            return
        remaining = int(session.get("pause_remaining", 0))
        session["paused"] = False
        session.pop("pause_remaining", None)
        session["ends_at"] = time.time() + remaining
        await db.set_session(interaction.channel_id, session)
        await interaction.edit_original_response(embed=embeds.success("Resumed."))

    @app_commands.command(name="preset_create", description="Create a timer preset")
    @app_commands.describe(name="Preset name", focus="Focus minutes", short_break="Short break minutes", long_break="Long break minutes", cycles="Cycles before long break")
    async def preset_create(self, interaction: discord.Interaction, name: str, focus: int, short_break: int, long_break: int, cycles: int):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        presets = user.get("presets", [])
        name = name.strip()[:32]
        for p in presets:
            if p.get("name").lower() == name.lower():
                p.update({"focus": focus, "short_break": short_break, "long_break": long_break, "cycles": cycles})
                break
        else:
            presets.append({"name": name, "focus": focus, "short_break": short_break, "long_break": long_break, "cycles": cycles})
        user["presets"] = presets
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success(f"Preset '{name}' saved."))

    @app_commands.command(name="preset_list", description="List your presets")
    async def preset_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        presets = user.get("presets", [])
        if not presets:
            await interaction.edit_original_response(embed=embeds.warn("No presets yet. Create one with /preset_create."))
            return
        lines = []
        default_name = user.get("default_preset")
        for p in presets:
            tag = " (default)" if default_name and p.get("name") == default_name else ""
            lines.append(f"• {p['name']}{tag} — {p['focus']}/{p['short_break']}/{p['long_break']} × {p['cycles']}")
        await interaction.edit_original_response(embed=embeds.base("Your Presets", "\n".join(lines)))

    @app_commands.command(name="preset_set_default", description="Set your default preset")
    async def preset_set_default(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        presets = user.get("presets", [])
        for p in presets:
            if p.get("name").lower() == name.lower():
                user["default_preset"] = p.get("name")
                await db.set_user(interaction.user.id, user)
                await interaction.edit_original_response(embed=embeds.success(f"Default preset set to '{p.get('name')}'."))
                return
        await interaction.edit_original_response(embed=embeds.error("Preset not found."))

    @app_commands.command(name="preset_use", description="Start a session using a named preset")
    async def preset_use(self, interaction: discord.Interaction, name: Optional[str] = None):
        await interaction.response.defer(ephemeral=False)
        user = await db.get_user(interaction.user.id)
        presets = user.get("presets", [])
        target = None
        if name:
            for p in presets:
                if p.get("name").lower() == name.lower():
                    target = p
                    break
        else:
            default_name = user.get("default_preset")
            if default_name:
                for p in presets:
                    if p.get("name") == default_name:
                        target = p
                        break
        if not target:
            await interaction.edit_original_response(embed=embeds.warn("No matching preset. Use /preset_list or provide a valid name."))
            return

        channel_id = interaction.channel_id
        existing = await db.get_session(channel_id)
        if existing:
            await interaction.edit_original_response(embed=embeds.warn("A session is already running in this channel."))
            return

        session = {
            "phase": "focus",
            "focus": int(target["focus"]),
            "short_break": int(target["short_break"]),
            "long_break": int(target["long_break"]),
            "cycles": int(target["cycles"]),
            "current_cycle": 1,
            "started_at": time.time(),
            "ends_at": time.time() + int(target["focus"]) * 60,
            "paused": False,
            "owner_id": interaction.user.id,
        }
        await db.set_session(channel_id, session)
        message = await interaction.edit_original_response(embed=self._build_embed(session))
        self.bot.loop.create_task(self._ticker(message, channel_id))


async def setup(bot: commands.Bot):
    await bot.add_cog(Pomodoro(bot))
