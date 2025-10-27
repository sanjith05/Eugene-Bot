from datetime import timedelta

def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    td = timedelta(seconds=seconds)
    # Format as MM:SS for < 1h, else HH:MM:SS
    total_seconds = int(td.total_seconds())
    if total_seconds < 3600:
        m, s = divmod(total_seconds, 60)
        return f"{m:02d}:{s:02d}"
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def progress_bar(ratio: float, length: int = 20) -> str:
    ratio = min(1.0, max(0.0, ratio))
    filled = int(length * ratio)
    return "█" * filled + "—" * (length - filled)
