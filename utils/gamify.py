from typing import Dict, Tuple, List

import discord
from discord.ext import commands

from . import database as db


# Simple level curve: level n requires total_xp >= 50 * n * (n + 1) / 2
# This yields L1=50, L2=150, L3=300, L4=500, ...

def xp_to_level(xp: int) -> Tuple[int, int, int]:
    """Return (level, current_level_base, next_level_xp).
    - level: computed level from xp
    - current_level_base: xp at the start of this level
    - next_level_xp: xp required to reach next level
    """
    level = 0
    required_next = 50
    total_for_next = required_next
    base = 0
    while xp >= total_for_next:
        level += 1
        base = total_for_next
        required_next += 50 * (level + 1)
        total_for_next += 50 * (level + 1)
    return level, base, total_for_next


async def grant_xp_and_check(bot: commands.Bot, user_id: int, delta: int, guild: discord.Guild = None) -> Dict:
    user = await db.get_user(user_id)
    old_xp = int(user.get("xp", 0))
    new_xp = old_xp + int(delta)
    user["xp"] = new_xp
    user["monthly_xp"] = int(user.get("monthly_xp", 0)) + int(delta)

    # Level up check
    old_level, _, _ = xp_to_level(old_xp)
    new_level, _, _ = xp_to_level(new_xp)
    leveled_up = new_level > old_level

    # Save
    await db.set_user(user_id, user)

    # Role rewards on level milestones if configured
    if leveled_up and guild is not None and guild.me and guild.me.guild_permissions.manage_roles:
        try:
            level_roles: Dict[str, str] = getattr(bot, "config", {}).get("level_roles", {})
            role_name = level_roles.get(str(new_level))
            if role_name:
                role = discord.utils.get(guild.roles, name=role_name)
                member = guild.get_member(user_id)
                if role and member:
                    await member.add_roles(role, reason=f"Level {new_level} reached")
        except Exception:
            pass

    return {"leveled_up": leveled_up, "new_level": new_level, "new_xp": new_xp}


async def record_focus_completion(user_id: int) -> Dict:
    user = await db.get_user(user_id)
    user["pomos_completed"] = int(user.get("pomos_completed", 0)) + 1
    await db.set_user(user_id, user)
    return user


async def check_basic_achievements(bot: commands.Bot, user_id: int, when_ts: float) -> List[str]:
    """Grant simple achievements: Early Bird (<=09:00), Midnight Owl (>=00:00), First 10 Pomos."""
    import datetime as dt
    user = await db.get_user(user_id)
    have: List[str] = list(user.get("achievements", []))
    granted: List[str] = []

    t = dt.datetime.fromtimestamp(when_ts)
    # Early Bird: completed focus before 9 AM
    if t.hour < 9 and "Early Bird" not in have:
        have.append("Early Bird")
        granted.append("Early Bird")
    # Midnight Owl: completed after 12 AM (0:00-3:59 window to avoid overlap)
    if t.hour < 4 and "Midnight Owl" not in have:
        have.append("Midnight Owl")
        granted.append("Midnight Owl")
    # First 10 Pomodoros
    if int(user.get("pomos_completed", 0)) >= 10 and "First 10" not in have:
        have.append("First 10")
        granted.append("First 10")

    if granted:
        user["achievements"] = have
        await db.set_user(user_id, user)
    return granted
