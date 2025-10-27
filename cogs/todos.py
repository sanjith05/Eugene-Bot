from typing import List, Dict, Any, Optional
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils import database as db
from utils import embeds
from utils.timeutils import format_duration


STATUS_CHOICES = ["Pending", "In-Progress", "Done"]
CATEGORY_CHOICES = ["Study", "Work", "Personal"]
PRIORITY_CHOICES = ["low", "normal", "high"]


def _now_ts() -> int:
    return int(time.time())


def _migrate_todos(raw) -> List[Dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return raw
    # old format: list of strings
    conv: List[Dict[str, Any]] = []
    for s in raw if isinstance(raw, list) else []:
        conv.append({
            "title": str(s),
            "cat": "Personal",
            "status": "Pending",
            "priority": "normal",
            "created": _now_ts(),
            "due": None,
        })
    return conv


def _status_icon(status: str) -> str:
    return {
        "Pending": "📝",
        "In-Progress": "⏳",
        "Done": "✅",
    }.get(status, "📝")


def _priority_icon(priority: str) -> str:
    return {
        "low": "🟢",
        "normal": "🟡",
        "high": "🔴",
    }.get(priority, "🟡")


class Todos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="todo_add", description="Add a to-do item with optional category, priority, and due time")
    @app_commands.describe(
        text="Task description",
        category="Study / Work / Personal",
        priority="low / normal / high",
        due_in_hours="Due time in hours from now (optional)",
    )
    @app_commands.choices(category=[
        app_commands.Choice(name=c, value=c) for c in CATEGORY_CHOICES
    ], priority=[
        app_commands.Choice(name=p, value=p) for p in PRIORITY_CHOICES
    ])
    async def todo_add(self, interaction: discord.Interaction, text: str, category: Optional[app_commands.Choice[str]] = None,
                       priority: Optional[app_commands.Choice[str]] = None, due_in_hours: Optional[int] = None):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        todos: List[Dict[str, Any]] = _migrate_todos(user.get("todos", []))

        todo = {
            "title": text.strip(),
            "cat": (category.value if category else "Personal"),
            "status": "Pending",
            "priority": (priority.value if priority else "normal"),
            "created": _now_ts(),
            "due": (_now_ts() + int(due_in_hours) * 3600) if due_in_hours else None,
        }
        todos.append(todo)
        user["todos"] = todos
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success("Added to your to-do list."))

    @app_commands.command(name="todo_list", description="List your to-dos with optional filters")
    @app_commands.describe(status="Filter by status", category="Filter by category")
    @app_commands.choices(status=[app_commands.Choice(name=s, value=s) for s in STATUS_CHOICES],
                          category=[app_commands.Choice(name=c, value=c) for c in CATEGORY_CHOICES])
    async def todo_list(self, interaction: discord.Interaction, status: Optional[app_commands.Choice[str]] = None,
                        category: Optional[app_commands.Choice[str]] = None):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        todos: List[Dict[str, Any]] = _migrate_todos(user.get("todos", []))
        user["todos"] = todos  # persist migration
        await db.set_user(interaction.user.id, user)

        def matches(t: Dict[str, Any]) -> bool:
            if status and t.get("status") != status.value:
                return False
            if category and t.get("cat") != category.value:
                return False
            return True

        filtered = [t for t in todos if matches(t)]
        if not filtered:
            await interaction.edit_original_response(embed=embeds.warn("No tasks match your filters."))
            return

        lines: List[str] = []
        for i, t in enumerate(filtered, start=1):
            icon = _status_icon(t.get("status"))
            prio = _priority_icon(t.get("priority", "normal"))
            due = t.get("due")
            if due:
                remain = int(due - _now_ts())
                due_str = ("overdue by " + format_duration(-remain)) if remain < 0 else ("due in " + format_duration(remain))
            else:
                due_str = "no due"
            lines.append(f"{i}. {icon} {prio} {t.get('title')} — {t.get('cat')} · {t.get('status')} · {due_str}")

        await interaction.edit_original_response(embed=embeds.base("Your To-Dos", "\n".join(lines)))

    @app_commands.command(name="todo_set_status", description="Update the status of a to-do by its number")
    @app_commands.describe(index="Item number from /todo_list", status="New status")
    @app_commands.choices(status=[app_commands.Choice(name=s, value=s) for s in STATUS_CHOICES])
    async def todo_set_status(self, interaction: discord.Interaction, index: int, status: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        todos: List[Dict[str, Any]] = _migrate_todos(user.get("todos", []))
        if not (1 <= index <= len(todos)):
            await interaction.edit_original_response(embed=embeds.error("Invalid index."))
            return
        todos[index - 1]["status"] = status.value
        user["todos"] = todos
        await db.set_user(interaction.user.id, user)
        await interaction.edit_original_response(embed=embeds.success("Status updated."))

    @app_commands.command(name="todo_complete", description="Complete a to-do by its number and earn XP")
    @app_commands.describe(index="Item number from /todo_list")
    async def todo_complete(self, interaction: discord.Interaction, index: int):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        todos: List[Dict[str, Any]] = _migrate_todos(user.get("todos", []))
        if not (1 <= index <= len(todos)):
            await interaction.edit_original_response(embed=embeds.error("Invalid index."))
            return

        t = todos[index - 1]
        t["status"] = "Done"
        now = _now_ts()
        due = t.get("due")
        on_time = (due is None) or (now <= int(due))
        xp_gain = 10 if on_time else 5
        user["xp"] = int(user.get("xp", 0)) + xp_gain
        user["todos"] = todos
        await db.set_user(interaction.user.id, user)
        msg = "Completed! +10 XP" if on_time else "Completed (overdue). +5 XP"
        await interaction.edit_original_response(embed=embeds.success(msg))

    @app_commands.command(name="todo_stats", description="Show counts by status/category and overdue tasks")
    async def todo_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = await db.get_user(interaction.user.id)
        todos: List[Dict[str, Any]] = _migrate_todos(user.get("todos", []))
        if not todos:
            await interaction.edit_original_response(embed=embeds.warn("No tasks yet."))
            return
        # Counts
        by_status = {s: 0 for s in STATUS_CHOICES}
        by_cat = {c: 0 for c in CATEGORY_CHOICES}
        overdue = 0
        now = _now_ts()
        for t in todos:
            by_status[t.get("status", "Pending")] = by_status.get(t.get("status", "Pending"), 0) + 1
            by_cat[t.get("cat", "Personal")] = by_cat.get(t.get("cat", "Personal"), 0) + 1
            due = t.get("due")
            if due and int(due) < now and t.get("status") != "Done":
                overdue += 1

        desc_lines = [
            f"Status — Pending: {by_status.get('Pending',0)}, In-Progress: {by_status.get('In-Progress',0)}, Done: {by_status.get('Done',0)}",
            f"Categories — Study: {by_cat.get('Study',0)}, Work: {by_cat.get('Work',0)}, Personal: {by_cat.get('Personal',0)}",
            f"Overdue (open): {overdue}",
        ]
        await interaction.edit_original_response(embed=embeds.base("To-Do Stats", "\n".join(desc_lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Todos(bot))
