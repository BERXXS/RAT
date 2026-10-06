import os
import sqlite3
import shutil
import tempfile
from datetime import datetime, date, time, timedelta

CHROME_EPOCH = datetime(1601, 1, 1)


def _chrome_time_to_datetime(value):
    try:
        return CHROME_EPOCH + timedelta(microseconds=int(value))
    except Exception:
        return None


def _datetime_to_chrome_time(value):
    return int((value - CHROME_EPOCH).total_seconds() * 1_000_000)


def _iter_browser_history_files():
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")

    candidates = []

    chrome_user_data = os.path.join(local, "Google", "Chrome", "User Data")
    if os.path.isdir(chrome_user_data):
        for profile in os.listdir(chrome_user_data):
            history_path = os.path.join(chrome_user_data, profile, "History")
            if os.path.isfile(history_path):
                candidates.append(("Google Chrome", profile, history_path))

    opera_paths = [
        ("Opera", "Default", os.path.join(roaming, "Opera Software", "Opera Stable", "History")),
        ("Opera GX", "Default", os.path.join(roaming, "Opera Software", "Opera GX Stable", "History")),
    ]
    for browser, profile, history_path in opera_paths:
        if os.path.isfile(history_path):
            candidates.append((browser, profile, history_path))

    return candidates


def _copy_history_db(source_path):
    fd, temp_path = tempfile.mkstemp(prefix="browser_history_", suffix=".db")
    os.close(fd)
    shutil.copy2(source_path, temp_path)
    return temp_path


def get_browser_history(target_date=None, browser_filter="ALL", limit=10000):
    start_chrome = None
    end_chrome = None

    if target_date:
        day = datetime.strptime(target_date, "%Y-%m-%d").date()
        start_dt = datetime.combine(day, time.min)
        end_dt = start_dt + timedelta(days=1)
        start_chrome = _datetime_to_chrome_time(start_dt)
        end_chrome = _datetime_to_chrome_time(end_dt)

    browser_filter = (browser_filter or "ALL").upper()
    entries = []
    errors = []

    for browser, profile, history_path in _iter_browser_history_files():
        browser_key = "CHROME" if "Chrome" in browser else "OPERA"
        if browser_filter != "ALL" and browser_filter != browser_key:
            continue

        temp_db = None
        try:
            temp_db = _copy_history_db(history_path)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            params = []
            where = ""
            if start_chrome is not None and end_chrome is not None:
                where = "WHERE urls.last_visit_time >= ? AND urls.last_visit_time < ?"
                params.extend([start_chrome, end_chrome])

            query = f"""
                SELECT
                    urls.url,
                    COALESCE(urls.title, ''),
                    urls.last_visit_time,
                    COALESCE(urls.visit_count, 0)
                FROM urls
                {where}
                ORDER BY urls.last_visit_time DESC
                LIMIT ?
            """
            params.append(int(limit))
            cursor.execute(query, params)

            for url, title, last_visit_time, visit_count in cursor.fetchall():
                visit_dt = _chrome_time_to_datetime(last_visit_time)
                if not visit_dt:
                    continue
                entries.append({
                    "browser": browser,
                    "profile": profile,
                    "datetime": visit_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "title": title or "",
                    "url": url or "",
                    "visit_count": int(visit_count or 0),
                })

            conn.close()
        except Exception as exc:
            errors.append(f"{browser} / {profile}: {exc}")
        finally:
            if temp_db and os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass

    entries.sort(key=lambda item: item.get("datetime", ""), reverse=True)
    return {"entries": entries, "errors": errors}


def format_browser_history(target_date=None, browser_filter="ALL"):
    data = get_browser_history(target_date=target_date, browser_filter=browser_filter)
    lines = []
    for item in data["entries"]:
        lines.append(
            f"[{item['datetime']}] [{item['browser']} / {item['profile']}] "
            f"{item['title']} - {item['url']}"
        )
    if data["errors"]:
        lines.append("\nОшибки чтения:")
        lines.extend(data["errors"])
    return "\n".join(lines) if lines else "Записи в истории не найдены."


def get_chrome_history():
    return format_browser_history(browser_filter="CHROME")


if __name__ == '__main__':
    print(format_browser_history())
