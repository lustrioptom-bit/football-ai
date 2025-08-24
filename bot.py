# bot.py
from config import TOKEN, MAIN_CHAT_ID
import requests
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

def send_message(chat_id, text):
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(BASE_URL + "sendMessage", data=payload, timeout=10)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

def get_updates(offset=None):
    url = BASE_URL + "getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    try:
        response = requests.get(url, params=params, timeout=35)
        return response.json()
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return {"ok": False}

def main():
    logger.info("✅ Бот запущен...")
    offset = None

    while True:
        try:
            data = get_updates(offset)
            if not data["ok"] or not data["result"]:
                time.sleep(1)
                continue

            for item in data["result"]:
                offset = item["update_id"] + 1
                msg = item["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")

                if text == "/start":
                    send_message(chat_id, "👋 Привет! Бот работает 24/7!")

                elif text == "/test":
                    send_message(chat_id, "✅ Бот в облаке работает!")

            time.sleep(1)

        except KeyboardInterrupt:
            logger.info("🛑 Остановлен")
            break
        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
