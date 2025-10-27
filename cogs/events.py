import asyncio
import datetime as dt

from discord.ext import commands, tasks

from utils import database as db


class Events(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_reset.start()
        self.weekly_reset.start()
        self.monthly_rollover.start()

    def cog_unload(self):
        self.daily_reset.cancel()
        self.weekly_reset.cancel()
        self.monthly_rollover.cancel()

    @tasks.loop(hours=24)
    async def daily_reset(self):
        # Placeholder: increment streak for users who had activity; simple demo adds 1 to everyone with xp>0
        # In future: track check-ins or focus session completions per user per day
        from pathlib import Path
        import json
        users_path = (Path(__file__).resolve().parent.parent / "data" / "users.json")
        try:
            users = json.loads(users_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            users = {}
        changed = False
        for uid, u in users.items():
            if int(u.get("xp", 0)) > 0:
                u["streak"] = int(u.get("streak", 0)) + 1
                changed = True
        if changed:
            users_path.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

    @tasks.loop(hours=168)
    async def weekly_reset(self):
        # Placeholder: could grant weekly rewards or decay xp
        pass

    @tasks.loop(hours=24)
    async def monthly_rollover(self):
        # Run once a day; will only trigger actual rollover at month change
        import json
        now = dt.datetime.utcnow()
        ym = now.strftime("%Y-%m")
        state = await db.get_season_state()
        last = state.get("last_rollover", "")
        if last == ym:
            return
        # Compute previous month label
        first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_last_day = first_of_month - dt.timedelta(days=1)
        label = prev_last_day.strftime("%Y-%m")
        # Load users and compute rankings by monthly_xp
        from pathlib import Path
        users_path = (Path(__file__).resolve().parent.parent / "data" / "users.json")
        try:
            users = json.loads(users_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            users = {}
        ranking = []
        for uid, u in users.items():
            ranking.append({"user_id": int(uid), "monthly_xp": int(u.get("monthly_xp", 0)), "xp": int(u.get("xp", 0))})
        ranking.sort(key=lambda r: (-r["monthly_xp"], -r["xp"]))
        top10 = ranking[:10]
        # Save to Hall of Fame
        hof = await db.get_hof()
        hof[label] = top10
        await db.set_hof(hof)
        # Reset monthly_xp
        changed = False
        for uid, u in users.items():
            if int(u.get("monthly_xp", 0)) != 0:
                u["monthly_xp"] = 0
                changed = True
        if changed:
            users_path.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
        # Update state
        state["last_rollover"] = ym
        await db.set_season_state(state)

    @daily_reset.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()
        # Sleep until next local midnight
        now = dt.datetime.now()
        tomorrow = (now + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        await asyncio.sleep((tomorrow - now).total_seconds())

    @weekly_reset.before_loop
    async def before_weekly(self):
        await self.bot.wait_until_ready()

    @monthly_rollover.before_loop
    async def before_monthly(self):
        await self.bot.wait_until_ready()
        # Sleep until just after next month boundary (UTC)
        now = dt.datetime.utcnow()
        # Compute first day of next month
        y = now.year + (now.month // 12)
        m = (now.month % 12) + 1
        next_month = dt.datetime(y, m, 1)
        await asyncio.sleep((next_month - now).total_seconds() + 5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Events(bot))
