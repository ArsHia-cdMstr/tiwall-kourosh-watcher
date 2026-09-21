from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"
LOG_PATH = BASE_DIR / "watcher.log"


class ShowtimeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.showtimes: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id", "") or ""
        if tag == "a" and element_id.startswith("instance"):
            self._current = {
                "id": attributes.get("data-id", "") or element_id.removeprefix("instance"),
                "date": attributes.get("data-date", "") or "",
            }
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            text = " ".join(" ".join(self._text).split())
            self._current["text"] = text
            if self._current["id"] and self._current["date"]:
                self.showtimes.append(self._current)
            self._current = None
            self._text = []


def log(message: str) -> None:
    from datetime import datetime

    line = f"{datetime.now().isoformat(timespec='seconds')}  {message}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    temporary.replace(path)


def fetch_showtimes(url: str) -> list[dict[str, str]]:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as conditions
    from selenium.webdriver.support.ui import WebDriverWait

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--window-size=1280,1000")
    options.add_argument(f"--user-data-dir={BASE_DIR / '.chrome-profile'}")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        WebDriverWait(driver, 40).until(
            conditions.presence_of_element_located((By.CSS_SELECTOR, "[id^='instance']"))
        )
        body = driver.page_source
    finally:
        driver.quit()

    parser = ShowtimeParser()
    parser.feed(body)
    if not parser.showtimes:
        raise RuntimeError("No showtimes found; the page layout may have changed.")
    return parser.showtimes


def send_notification(server: str, topic: str, purchase_url: str, showtimes: list[dict[str, str]]) -> None:
    details = "\n".join(f"• {item['text']}" for item in showtimes)
    message = f"سانس جدید نمایش کورش باز شد!\n{details}\nبرای خرید سریع روی اعلان بزنید."
    endpoint = f"{server.rstrip('/')}/{topic}"
    request = urllib.request.Request(
        endpoint,
        data=message.encode("utf-8"),
        method="POST",
        headers={
            "Priority": "urgent",
            "Tags": "rotating_light,ticket",
            "Click": purchase_url,
            "Actions": f"view, Buy ticket, {purchase_url}, clear=true",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def run(test_notification: bool = False) -> int:
    config = load_json(CONFIG_PATH, {})
    config["purchase_url"] = os.environ.get(
        "PURCHASE_URL", config.get("purchase_url", "https://www.tiwall.com/s/kourosh2")
    )
    config["ntfy_server"] = os.environ.get(
        "NTFY_SERVER", config.get("ntfy_server", "https://ntfy.sh")
    )
    config["ntfy_topic"] = os.environ.get("NTFY_TOPIC", config.get("ntfy_topic", ""))
    required = ("purchase_url", "ntfy_server", "ntfy_topic")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"Missing config values: {', '.join(missing)}")

    if test_notification:
        send_notification(
            config["ntfy_server"],
            config["ntfy_topic"],
            config["purchase_url"],
            [{"id": "test", "date": "test", "text": "این یک اعلان آزمایشی است"}],
        )
        log("Test notification sent.")
        return 0

    showtimes = fetch_showtimes(config["purchase_url"])
    state = load_json(STATE_PATH, {"seen_ids": []})
    seen_ids = set(state.get("seen_ids", []))
    current_ids = {item["id"] for item in showtimes}

    if not STATE_PATH.exists():
        save_json(STATE_PATH, {"seen_ids": sorted(current_ids)})
        log(f"Baseline saved with {len(current_ids)} showtimes; no alert sent.")
        return 0

    new_showtimes = [item for item in showtimes if item["id"] not in seen_ids]
    if new_showtimes:
        send_notification(
            config["ntfy_server"], config["ntfy_topic"], config["purchase_url"], new_showtimes
        )
        log(f"Alert sent for {len(new_showtimes)} new showtime(s): {new_showtimes}")
    else:
        log(f"No change; {len(showtimes)} showtime(s) currently available.")

    save_json(STATE_PATH, {"seen_ids": sorted(seen_ids | current_ids)})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch Tiwall for new Kourosh showtimes.")
    parser.add_argument("--test-notification", action="store_true")
    args = parser.parse_args()
    try:
        return run(test_notification=args.test_notification)
    except (OSError, RuntimeError, urllib.error.URLError, json.JSONDecodeError) as error:
        log(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
