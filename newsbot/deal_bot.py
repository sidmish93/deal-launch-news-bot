"""Telegram bot for ECM news: IPO, QIP, blocks, rights, preferential, and related deals.

Run:  python -m newsbot.deal_bot
The token is read from DEAL_BOT_TOKEN in the project .env file.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

from newsbot.feeds import IST, Deal, polish_headline, press_deals

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "newsbot", "state", "deals.json")
POLL_SECONDS = 180
BACKFILL_HOURS = 36
BACKFILL_CAP = 20

WELCOME = (
    "ECM news bot is on.\n"
    "I post IPO, QIP, OFS, rights, preferential, buyback, and block-deal "
    "headlines from CNBC TV18, Moneycontrol, NDTV Profit, Economic Times, "
    "Business Standard, and Mint.\n"
    "Commands: /latest  /status"
)
SHORT_DESCRIPTION = "IPO, QIP, OFS, rights, preferential, and block-deal launches."
DESCRIPTION = (
    "Posts IPO, QIP, OFS, rights, preferential, buyback, and block-deal "
    "headlines from CNBC TV18, Moneycontrol, NDTV Profit, Economic Times, "
    "Business Standard, and Mint."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="poll feeds once and exit")
    parser.add_argument("--dry-run", action="store_true", help="print matches, send nothing")
    parser.add_argument("--day", default="", help="resend one IST day, YYYY-MM-DD, without changing seen")
    args = parser.parse_args()
    token = _load_token()
    if args.dry_run:
        _print_deals()
        return
    state = _load_state()
    _ensure_env_chat(state)
    if args.day:
        _replay_day(token, state, args.day)
        return
    if args.once:
        try:
            _learn_groups(
                token,
                state,
                "This group is connected. New ECM headlines will be posted here.",
            )
        except Exception as exc:
            print("groups skipped: " + _redact(exc, token), flush=True)
        _poll(token, state)
        _save_state(state)
        return
    _configure_bot(token)
    print("ECM news bot running. Open the bot and tap Start.", flush=True)
    socket.setdefaulttimeout(20)
    next_poll = 0.0
    while True:
        try:
            _within(lambda: _read_updates(token, state), 20)
        except Exception as exc:
            print("updates error: " + _redact(exc, token), flush=True)
        try:
            _deliver_pending(token, state)
            if time.time() >= next_poll:
                print("checking feeds", flush=True)
                _poll(token, state)
                next_poll = time.time() + POLL_SECONDS
        except Exception as exc:
            print("poll error: " + _redact(exc, token), flush=True)
        _save_state(state)
        time.sleep(2)


def _print_deals() -> None:
    deals, _rejected = press_deals()
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=BACKFILL_HOURS)
    recent = [d for d in deals if d.published and d.published >= cutoff]
    print(f"{len(deals)} classified, {len(recent)} in the last {BACKFILL_HOURS}h")
    for deal in recent[:BACKFILL_CAP]:
        print("---")
        print(deal.format())


def _replay_day(token: str, state: dict, day: str) -> None:
    """Send one day's headlines again. The seen list stays as it is."""
    try:
        wanted = datetime.date.fromisoformat(day)
    except ValueError:
        sys.exit("day must be YYYY-MM-DD")
    listed, _rejected = press_deals()
    deals = [
        deal
        for deal in listed
        if deal.published and deal.published.astimezone(IST).date() == wanted
    ]
    deals.sort(key=lambda deal: deal.published or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
    sent = 0
    for deal in deals:
        polished = polish_headline(deal)
        if polished is None:
            continue
        _broadcast(token, state, polished.format())
        sent += 1
    print(f"replay {wanted.isoformat()}: {sent} deals, {len(state['chats'])} chats", flush=True)


def _poll(token: str, state: dict) -> None:
    try:
        deals, rejected = press_deals(_sent_urls(state), state.get("held") or {})
    except Exception as exc:
        print("feed error: " + _redact(exc, token), flush=True)
        return
    if not state["primed"]:
        _prime(token, state, deals, rejected)
        return
    chosen = _choose(deals, rejected, state)
    sent = 0
    for deal in chosen:
        polished = polish_headline(deal)
        if polished is None:
            state["held"][deal.url] = deal.company
            continue
        text = polished.format()
        if not _broadcast(token, state, text):
            continue
        state["seen"] = _trim(state["seen"] + [deal.id])
        state["held"].pop(deal.url, None)
        state["recent"].append({"text": text, "id": deal.id})
        sent += 1
    state["recent"] = state["recent"][-30:]
    print(f"{sent} new deals, {len(state['chats'])} chats", flush=True)


def _sent_urls(state: dict) -> set[str]:
    urls = set()
    for item_id in state.get("seen", []):
        if isinstance(item_id, str) and item_id.startswith("press:"):
            urls.add(item_id[len("press:"):])
    return urls


def _choose(deals: list[Deal], rejected: list[tuple[str, str]], state: dict, now=None) -> list[Deal]:
    """What to send now. A url is remembered with the title that was judged.

    The first run only sends the last 36 hours, so the lists already on disk
    are not dumped into the group. After that, a url is sent when it first
    appears, including when the paper lists it late. A title the paper changes
    is judged again. Nothing is marked sent until Telegram accepts it.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=BACKFILL_HOURS)
    ancient = now - datetime.timedelta(days=7)
    watching = bool(state.get("watching"))
    held = state.setdefault("held", {})
    seen = set(state.get("seen", []))
    chosen = []
    for deal in deals:
        if deal.id in seen or held.get(deal.url) == deal.company:
            continue
        stale = deal.published is None or deal.published < (cutoff if not watching else ancient)
        if stale:
            held[deal.url] = deal.company
            continue
        chosen.append(deal)
    for url, title in rejected:
        held[url] = title
    state["watching"] = True
    if len(held) > 3000:
        for key in list(held)[: len(held) - 3000]:
            del held[key]
    state["held"] = held
    return chosen


def _prime(token: str, state: dict, deals: list[Deal], rejected: list[tuple[str, str]]) -> None:
    seen = set(state["seen"])
    fresh = [d for d in deals if d.id not in seen]
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=BACKFILL_HOURS)
    to_send = [d for d in fresh if d.published is None or d.published >= cutoff]
    to_send.sort(key=lambda d: d.published or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))
    overflow = max(0, len(to_send) - BACKFILL_CAP)
    to_send = to_send[-BACKFILL_CAP:]
    state["primed"] = True
    state["watching"] = True
    sent_ids = []
    for deal in to_send:
        polished = polish_headline(deal)
        if polished is None:
            continue
        text = polished.format()
        if not _broadcast(token, state, text):
            continue
        sent_ids.append(deal.id)
        state["recent"].append({"text": text, "id": deal.id})
    state["seen"] = _trim(state["seen"] + sent_ids)
    held = state.setdefault("held", {})
    sent = set(sent_ids)
    attempted = {deal.id for deal in to_send}
    for deal in deals:
        if deal.id in attempted and deal.id not in sent:
            continue
        if deal.id not in sent and deal.id not in set(state["seen"]):
            held[deal.url] = deal.company
    for url, title in rejected:
        held[url] = title
    state["held"] = held
    state["recent"] = state["recent"][-30:]
    if overflow and state["chats"]:
        _broadcast(token, state, f"{overflow} older deals from the last day were skipped.")
    print(f"{len(sent_ids)} new deals, {len(state['chats'])} chats", flush=True)


def _within(loader, seconds: int):
    box: dict = {}

    def run():
        try:
            box["value"] = loader()
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise TimeoutError(f"no reply in {seconds}s")
    if "error" in box:
        raise box["error"]
    return box.get("value", [])


def _read_updates(token: str, state: dict) -> None:
    payload = {"timeout": 0, "offset": state["offset"], "allowed_updates": ["message", "my_chat_member"]}
    updates = _api(token, "getUpdates", payload, timeout=20)
    for update in updates:
        state["offset"] = update["update_id"] + 1
        if "my_chat_member" in update:
            member = update["my_chat_member"]
            chat_id = member["chat"]["id"]
            status = member["new_chat_member"]["status"]
            if status in ("member", "administrator"):
                _add_chat(token, state, chat_id)
            elif status in ("left", "kicked"):
                state["chats"] = [c for c in state["chats"] if c != chat_id]
            continue
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        text = (message.get("text") or "").strip()
        command = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""
        if command in ("/start", "/help"):
            _add_chat(token, state, chat_id)
        elif command == "/latest":
            _add_chat(token, state, chat_id, welcome=False)
            recent = state["recent"][-8:]
            body = "\n\n".join(item["text"] for item in recent) or "Nothing posted yet."
            _send(token, chat_id, body)
        elif command == "/status":
            _add_chat(token, state, chat_id, welcome=False)
            _send(
                token,
                chat_id,
                "Watching CNBC TV18, Moneycontrol, NDTV Profit, Economic Times, "
                "Business Standard, and Mint for IPO, QIP, block, rights, "
                "preferential, and other ECM headlines.",
            )
        elif chat.get("type") == "private":
            _add_chat(token, state, chat_id)


def _group_event(update: dict) -> tuple[str, int] | None:
    """A group join or leave. Private chats are left to the saved chat id."""
    member = update.get("my_chat_member")
    if member:
        chat = member.get("chat") or {}
        if chat.get("type") not in ("group", "supergroup"):
            return None
        chat_id = chat.get("id")
        status = (member.get("new_chat_member") or {}).get("status")
        if not isinstance(chat_id, int):
            return None
        if status in ("member", "administrator", "creator"):
            return ("join", chat_id)
        if status in ("left", "kicked"):
            return ("leave", chat_id)
        return None
    chat = (update.get("message") or {}).get("chat") or {}
    chat_id = chat.get("id")
    if chat.get("type") in ("group", "supergroup") and isinstance(chat_id, int):
        return ("join", chat_id)
    return None


def _apply_group_event(state: dict, event: tuple[str, int]) -> str:
    kind, chat_id = event
    welcomed = state.setdefault("welcomed", [])
    if kind == "join":
        added = chat_id not in state["chats"]
        if added:
            state["chats"].append(chat_id)
        if chat_id not in welcomed:
            welcomed.append(chat_id)
        return "added" if added else "kept"
    removed = chat_id in state["chats"]
    state["chats"] = [item for item in state["chats"] if item != chat_id]
    state["welcomed"] = [item for item in welcomed if item != chat_id]
    return "removed" if removed else "kept"


def _migrated_chat_id(exc: BaseException) -> int | None:
    text = str(exc)
    key = '"migrate_to_chat_id":'
    start = text.find(key)
    if start < 0:
        return None
    raw = []
    for char in text[start + len(key):].lstrip():
        if char == "-" or char.isdigit():
            raw.append(char)
        else:
            break
    if not raw or raw == ["-"]:
        return None
    return int("".join(raw))


def _replace_chat(state: dict, old_id: int, new_id: int) -> None:
    def swap(items: list) -> list:
        result = []
        for item in items:
            item = new_id if item == old_id else item
            if item not in result:
                result.append(item)
        return result

    state["chats"] = swap(state.get("chats", []))
    state["welcomed"] = swap(state.get("welcomed", []))


def _note_group(token: str, state: dict, chat_id: int, note: str) -> None:
    print(f"group {chat_id}", flush=True)
    try:
        _send(token, chat_id, note)
    except RuntimeError as exc:
        moved = _migrated_chat_id(exc)
        if moved is None:
            print(f"send to {chat_id} failed: {_redact(exc, token)}", flush=True)
            return
        already = moved in state["chats"]
        _replace_chat(state, chat_id, moved)
        print(f"group {chat_id} moved to {moved}", flush=True)
        if already:
            return
        try:
            _send(token, moved, note)
        except RuntimeError as exc2:
            print(f"send to {moved} failed: {_redact(exc2, token)}", flush=True)


def _settle_groups(token: str, state: dict) -> None:
    """Drop a basic group id after Telegram upgrades that group to a supergroup."""
    for chat_id in list(state["chats"]):
        if chat_id >= 0 or str(chat_id).startswith("-100"):
            continue
        try:
            _api(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except RuntimeError as exc:
            moved = _migrated_chat_id(exc)
            if moved is None:
                print(f"group {chat_id} skipped: {_redact(exc, token)}", flush=True)
                continue
            _replace_chat(state, chat_id, moved)
            print(f"group {chat_id} moved to {moved}", flush=True)


def _learn_groups(token: str, state: dict, note: str) -> None:
    """Remember a group the bot was added to, without replaying old headlines."""
    _settle_groups(token, state)
    for _ in range(10):
        updates = _api(
            token,
            "getUpdates",
            {
                "timeout": 0,
                "offset": state.get("offset", 0),
                "allowed_updates": ["message", "my_chat_member"],
            },
            timeout=20,
        )
        if not updates:
            return
        for update in updates:
            state["offset"] = int(update["update_id"]) + 1
            event = _group_event(update)
            if event is None:
                continue
            result = _apply_group_event(state, event)
            if result == "added":
                _note_group(token, state, event[1], note)
            elif result == "removed":
                print(f"left {event[1]}", flush=True)


def _deliver_pending(token: str, state: dict) -> None:
    for chat_id in list(state["chats"]):
        if chat_id not in state["welcomed"]:
            _add_chat(token, state, chat_id)


def _add_chat(token: str, state: dict, chat_id: int, welcome: bool = True) -> None:
    if chat_id >= 0:
        return
    if chat_id not in state["chats"]:
        state["chats"].append(chat_id)
        print(f"chat {chat_id}", flush=True)
    if welcome and chat_id not in state["welcomed"]:
        _send(token, chat_id, WELCOME)
        for item in state["recent"][-20:]:
            _send(token, chat_id, item["text"])
        state["welcomed"].append(chat_id)
        print(f"delivered {len(state['recent'][-20:])} to {chat_id}", flush=True)


def _broadcast(token: str, state: dict, text: str) -> bool:
    """True when at least one group accepted the message."""
    _groups_only(state)
    delivered = False
    for chat_id in list(state["chats"]):
        if chat_id not in state["chats"]:
            continue
        target = chat_id
        try:
            _send(token, target, text)
            delivered = True
        except RuntimeError as exc:
            moved = _migrated_chat_id(exc)
            if moved is None:
                print(f"send to {chat_id} failed: {_redact(exc, token)}", flush=True)
                continue
            already = moved in state["chats"]
            _replace_chat(state, chat_id, moved)
            print(f"group {chat_id} moved to {moved}", flush=True)
            if already:
                continue
            try:
                _send(token, moved, text)
                delivered = True
            except RuntimeError as exc2:
                print(f"send to {moved} failed: {_redact(exc2, token)}", flush=True)
    return delivered


def _configure_bot(token: str) -> None:
    me = _api(token, "getMe")
    print(f"connected as @{me.get('username')}", flush=True)
    optional = (
        ("deleteWebhook", None),
        ("setMyShortDescription", {"short_description": SHORT_DESCRIPTION}),
        ("setMyDescription", {"description": DESCRIPTION}),
        (
            "setMyCommands",
            {
                "commands": [
                    {"command": "latest", "description": "Show the latest deals"},
                    {"command": "status", "description": "Which sources are watched"},
                ]
            },
        ),
    )
    for method, payload in optional:
        try:
            _api(token, method, payload)
        except RuntimeError as exc:
            print(f"{method} skipped: {_redact(exc, token)}", flush=True)


def _send(token: str, chat_id: int, text: str) -> None:
    payload = {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": False}
    try:
        _api(token, "sendMessage", payload)
    except RuntimeError as exc:
        if "429" not in str(exc):
            raise
        time.sleep(3)
        _api(token, "sendMessage", payload)
    time.sleep(0.4)


def _api(
    token: str,
    method: str,
    payload: dict | None = None,
    timeout: int = 30,
    data: bytes | None = None,
    headers: dict | None = None,
):
    url = f"https://api.telegram.org/bot{token}/{method}"
    if data is None:
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if data else {}
    last = "no response"
    for attempt in range(5):
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode())
            if not body.get("ok"):
                raise RuntimeError(f"{method} refused")
            return body.get("result")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            last = f"{method} {exc.code} {_redact(detail, token)}"
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                break
        except Exception as exc:
            last = f"{method} {_redact(exc, token)}"
            if attempt == 4:
                break
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(last)


def _load_token() -> str:
    path = os.path.join(ROOT, ".env")
    token = os.environ.get("DEAL_BOT_TOKEN", "")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("DEAL_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"')
    if not token:
        sys.exit("DEAL_BOT_TOKEN is missing from .env")
    return token


def _groups_only(state: dict) -> None:
    """Personal chats stay off the list. Delivery is the group only."""
    state["chats"] = [chat_id for chat_id in state.get("chats", []) if isinstance(chat_id, int) and chat_id < 0]
    state["welcomed"] = [chat_id for chat_id in state.get("welcomed", []) if isinstance(chat_id, int) and chat_id < 0]


def _ensure_env_chat(state: dict) -> None:
    _groups_only(state)
    raw = os.environ.get("DEAL_CHAT_ID", "").strip()
    if not raw:
        return
    chat_id = int(raw)
    if chat_id >= 0:
        return
    if chat_id not in state["chats"]:
        state["chats"].append(chat_id)
    if chat_id not in state["welcomed"]:
        state["welcomed"].append(chat_id)


def _load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"seen": [], "chats": [], "welcomed": [], "recent": [], "primed": False, "offset": 0}
    with open(STATE_PATH, encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("seen", [])
    state.setdefault("chats", [])
    state.setdefault("welcomed", [])
    state.setdefault("recent", [])
    state.setdefault("primed", False)
    state.setdefault("offset", 0)
    state.setdefault("held", {})
    state.setdefault("watching", False)
    return state


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True, separators=(",", ":"))
    os.replace(tmp, STATE_PATH)


def _trim(ids: list[str]) -> list[str]:
    kept = []
    seen = set()
    for item_id in ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        kept.append(item_id)
    return kept[-5000:]


def _redact(value, token: str) -> str:
    return str(value).replace(token, "<token>")


if __name__ == "__main__":
    main()
