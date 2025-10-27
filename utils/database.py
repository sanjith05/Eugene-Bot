import json
import asyncio
from pathlib import Path
from typing import Any, Dict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USERS_PATH = DATA_DIR / "users.json"
SESSIONS_PATH = DATA_DIR / "sessions.json"
CHALLENGES_PATH = DATA_DIR / "challenges.json"
PARTNERS_PATH = DATA_DIR / "partners.json"
SHOP_PATH = DATA_DIR / "shop.json"
HOF_PATH = DATA_DIR / "hall_of_fame.json"
SEASON_STATE_PATH = DATA_DIR / "season.json"

_lock = asyncio.Lock()


def _ensure_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_PATH.exists():
        USERS_PATH.write_text("{}", encoding="utf-8")
    if not SESSIONS_PATH.exists():
        SESSIONS_PATH.write_text("{}", encoding="utf-8")
    if not CHALLENGES_PATH.exists():
        CHALLENGES_PATH.write_text(json.dumps({"goal": 0, "progress": 0}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not PARTNERS_PATH.exists():
        PARTNERS_PATH.write_text("{}", encoding="utf-8")
    if not SHOP_PATH.exists():
        SHOP_PATH.write_text(json.dumps({"color_roles": [], "specials": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not HOF_PATH.exists():
        HOF_PATH.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")
    if not SEASON_STATE_PATH.exists():
        SEASON_STATE_PATH.write_text(json.dumps({"last_rollover": ""}, ensure_ascii=False, indent=2), encoding="utf-8")


async def _read(path: Path) -> Dict[str, Any]:
    _ensure_files()
    async with _lock:
        try:
            return json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            return {}


async def _write(path: Path, data: Dict[str, Any]) -> None:
    _ensure_files()
    async with _lock:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# Users
async def get_user(user_id: int) -> Dict[str, Any]:
    data = await _read(USERS_PATH)
    base = {
        "xp": 0,
        "streak": 0,
        "todos": [],
        "pomos_completed": 0,
        "achievements": [],
        "presets": [],
        "focus_log": [],
        "coins": 0,
        "monthly_xp": 0,
        "theme": "aurora",
        "voice": {
            "enabled": False,
            "voice_channel_id": 0,
            "sounds": {
                "session_start": str(DATA_DIR.parent / "music" / "session _start.mp3"),
                "focus_start": str(DATA_DIR.parent / "music" / "session _start.mp3"),
                "break_start": str(DATA_DIR.parent / "music" / "Break_start.mp3"),
                "session_end": str(DATA_DIR.parent / "music" / "session_end.mp3"),
                "react_warning": str(DATA_DIR.parent / "music" / "react_warning.mp3"),
            },
        },
        "afk_strikes": 0,
        "pending_ack": {},
    }
    stored = data.get(str(user_id))
    if not stored:
        return base
    # Backfill missing keys for older users
    for k, v in base.items():
        stored.setdefault(k, v if not isinstance(v, list) else list(v))
    return stored


async def set_user(user_id: int, payload: Dict[str, Any]) -> None:
    data = await _read(USERS_PATH)
    data[str(user_id)] = payload
    await _write(USERS_PATH, data)


async def update_user(user_id: int, patch: Dict[str, Any]) -> Dict[str, Any]:
    user = await get_user(user_id)
    user.update(patch)
    await set_user(user_id, user)
    return user


# Sessions (Pomodoro)
async def get_session(channel_id: int) -> Dict[str, Any]:
    data = await _read(SESSIONS_PATH)
    return data.get(str(channel_id), {})


async def set_session(channel_id: int, payload: Dict[str, Any]) -> None:
    data = await _read(SESSIONS_PATH)
    data[str(channel_id)] = payload
    await _write(SESSIONS_PATH, data)


async def delete_session(channel_id: int) -> None:
    data = await _read(SESSIONS_PATH)
    if str(channel_id) in data:
        del data[str(channel_id)]
        await _write(SESSIONS_PATH, data)


# Challenges (weekly server goal - simplified global for now)
async def get_challenge() -> Dict[str, Any]:
    return await _read(CHALLENGES_PATH)


async def set_challenge(payload: Dict[str, Any]) -> None:
    await _write(CHALLENGES_PATH, payload)


async def increment_challenge(delta: int = 1) -> Dict[str, Any]:
    ch = await get_challenge()
    ch["progress"] = int(ch.get("progress", 0)) + int(delta)
    await set_challenge(ch)
    return ch


# Partners (pairing users)
async def get_partners() -> Dict[str, Any]:
    return await _read(PARTNERS_PATH)


async def set_partner(user_id: int, partner_id: int) -> None:
    data = await _read(PARTNERS_PATH)
    data[str(user_id)] = int(partner_id)
    data[str(partner_id)] = int(user_id)
    await _write(PARTNERS_PATH, data)


async def clear_partner(user_id: int) -> None:
    data = await _read(PARTNERS_PATH)
    pid = data.get(str(user_id))
    if pid is not None:
        data.pop(str(user_id), None)
        data.pop(str(pid), None)
        await _write(PARTNERS_PATH, data)


async def find_partner(user_id: int) -> int:
    data = await _read(PARTNERS_PATH)
    return int(data.get(str(user_id), 0))


# Shop
async def get_shop() -> Dict[str, Any]:
    return await _read(SHOP_PATH)


async def set_shop(payload: Dict[str, Any]) -> None:
    await _write(SHOP_PATH, payload)


# Hall of Fame and Season
async def get_hof() -> Dict[str, Any]:
    return await _read(HOF_PATH)


async def set_hof(payload: Dict[str, Any]) -> None:
    await _write(HOF_PATH, payload)


async def get_season_state() -> Dict[str, Any]:
    return await _read(SEASON_STATE_PATH)


async def set_season_state(payload: Dict[str, Any]) -> None:
    await _write(SEASON_STATE_PATH, payload)
