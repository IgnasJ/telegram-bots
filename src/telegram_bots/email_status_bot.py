import json
import logging
import os
import ssl
from dataclasses import dataclass
from email.header import decode_header
from email.utils import parsedate_to_datetime
from imaplib import IMAP4_SSL
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class InboxConfig:
    name: str
    email: str
    password: str
    imap_server: str
    imap_port: int = 993
    mailbox: str = "INBOX"


def load_inboxes() -> list[InboxConfig]:
    raw_config = os.getenv("INBOX_CONFIGS_JSON", "").strip()
    if not raw_config:
        raise ValueError("INBOX_CONFIGS_JSON is required.")

    try:
        parsed = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise ValueError("INBOX_CONFIGS_JSON must be valid JSON.") from exc

    if not isinstance(parsed, list) or not parsed:
        raise ValueError("INBOX_CONFIGS_JSON must be a non-empty JSON array.")

    inboxes: list[InboxConfig] = []
    for index, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Account #{index} must be a JSON object.")

        try:
            inboxes.append(
                InboxConfig(
                    name=item["name"],
                    email=item["email"],
                    password=item["password"],
                    imap_server=item["imap_server"],
                    imap_port=int(item.get("imap_port", 993)),
                    mailbox=item.get("mailbox", "INBOX"),
                )
            )
        except KeyError as exc:
            raise ValueError(f"Missing required key {exc!s} in account #{index}.") from exc

    return inboxes


def decode_mime_value(value: bytes | str | None) -> str:
    if value is None:
        return "(no value)"

    decoded_parts = decode_header(value)
    chunks: list[str] = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            chunks.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            chunks.append(part)
    return "".join(chunks).strip() or "(empty)"


def fetch_unseen_messages(config: InboxConfig) -> dict[str, Any]:
    logger.info("Checking inbox %s", config.name)
    ssl_context = ssl.create_default_context()

    with IMAP4_SSL(config.imap_server, config.imap_port, ssl_context=ssl_context) as client:
        client.login(config.email, config.password)

        status, _ = client.select(config.mailbox, readonly=True)
        if status != "OK":
            raise RuntimeError(f"Unable to select mailbox {config.mailbox}.")

        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("Unable to search for unseen emails.")

        message_ids = [item for item in data[0].split() if item]
        previews: list[str] = []

        for message_id in message_ids[:3]:
            status, fetched = client.fetch(message_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not fetched or not fetched[0]:
                continue

            header_bytes = fetched[0][1]
            if not isinstance(header_bytes, bytes):
                continue

            from email import message_from_bytes

            message = message_from_bytes(header_bytes)
            sender = decode_mime_value(message.get("From"))
            subject = decode_mime_value(message.get("Subject"))
            date_raw = message.get("Date")
            try:
                date_text = parsedate_to_datetime(date_raw).strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_text = date_raw or "unknown date"

            previews.append(f"- {subject} | {sender} | {date_text}")

        return {
            "name": config.name,
            "count": len(message_ids),
            "previews": previews,
            "status": "ok",
        }


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    payload = urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = Request(
        url=f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response.read()
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(response_body)
            description = parsed.get("description") or response_body
        except json.JSONDecodeError:
            description = response_body or "no error details returned"
        raise RuntimeError(f"Telegram API returned HTTP {exc.code}: {description}") from exc
    except URLError as exc:
        raise RuntimeError("Unable to reach Telegram API.") from exc


def build_message(results: list[dict[str, Any]]) -> str:
    lines = ["Email status report"]

    for result in results:
        if result["status"] == "error":
            lines.append("")
            lines.append(f"{result['name']}: ERROR")
            lines.append(result["error"])
            continue

        count = result["count"]
        lines.append("")
        lines.append(f"{result['name']}: {count} unread email(s)")
        if count == 0:
            lines.append("No new unread emails.")
            continue

        lines.extend(result["previews"] or ["Unread emails found, but preview could not be loaded."])
        remaining = count - len(result["previews"])
        if remaining > 0:
            lines.append(f"...and {remaining} more unread email(s).")

    return "\n".join(lines)


def main() -> int:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required.")
    if not telegram_chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is required.")

    inboxes = load_inboxes()
    results: list[dict[str, Any]] = []

    for inbox in inboxes:
        try:
            results.append(fetch_unseen_messages(inbox))
        except Exception as exc:
            logger.exception("Failed to process inbox %s", inbox.name)
            results.append(
                {
                    "name": inbox.name,
                    "status": "error",
                    "error": str(exc),
                }
            )

    message = build_message(results)
    send_telegram_message(telegram_token, telegram_chat_id, message)
    logger.info("Telegram notification sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
