import os
import tempfile
import time
from pathlib import Path

import requests

from blockblast_solver import format_solution, solve_image


API_ROOT = "https://api.telegram.org/bot{token}/{method}"
FILE_ROOT = "https://api.telegram.org/file/bot{token}/{path}"


def api(token, method, **params):
    response = requests.post(API_ROOT.format(token=token, method=method), data=params, timeout=40)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload["result"]


def send_message(token, chat_id, text):
    return api(token, "sendMessage", chat_id=chat_id, text=text)


def send_photo(token, chat_id, photo_path, caption):
    with open(photo_path, "rb") as file:
        response = requests.post(
            API_ROOT.format(token=token, method="sendPhoto"),
            data={"chat_id": chat_id, "caption": caption[:1024]},
            files={"photo": file},
            timeout=60,
        )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload["result"]


def download_file(token, file_id, target_path):
    file_info = api(token, "getFile", file_id=file_id)
    url = FILE_ROOT.format(token=token, path=file_info["file_path"])
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    Path(target_path).write_bytes(response.content)


def handle_photo(token, message):
    chat_id = message["chat"]["id"]
    photos = message.get("photo") or []
    if not photos:
        send_message(token, chat_id, "Пришли полный скрин Block Blast как фото, я нарисую куда ставить фигуры.")
        return

    photo = max(photos, key=lambda item: item.get("file_size", 0))
    with tempfile.TemporaryDirectory(prefix="blockblast_tg_") as tmp:
        input_path = Path(tmp) / "screen.jpg"
        output_path = Path(tmp) / "solution.jpg"
        download_file(token, photo["file_id"], input_path)
        try:
            solution, pieces, _ = solve_image(input_path, output_path)
            header = "Полное решение найдено" if solution.full else "Полного решения нет, лучший частичный ход"
            caption = header + "\n" + format_solution(solution, pieces)
            send_photo(token, chat_id, output_path, caption)
        except Exception as exc:
            send_message(
                token,
                chat_id,
                "Не смог надежно распознать этот скрин.\n"
                "Пришли полный вертикальный скрин без обрезки поля и лотка фигур.\n"
                f"Технически: {exc}",
            )


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN first.")

    print("Block Blast Telegram bot is running.", flush=True)
    offset = None
    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            updates = api(token, "getUpdates", **params)
            for update in updates:
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                chat_id = message["chat"]["id"]
                if "photo" in message:
                    handle_photo(token, message)
                else:
                    send_message(token, chat_id, "Скинь фото/скрин Block Blast, а я верну картинку с ходами.")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"polling error: {exc}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
