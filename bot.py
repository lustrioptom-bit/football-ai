# bot.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import json
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import logging
import time
import os

# Настройка
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфиг
TOKEN = "8304903389:AAGRyWP4Ez97aoA-yLTYzYLQHuKbutTfcy4"
MAIN_CHAT_ID = "8431596511"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# === Подписчики на push-уведомления ===
PUSH_SUBSCRIBERS_FILE = "push_subscribers.json"
if not os.path.exists(PUSH_SUBSCRIBERS_FILE):
    with open(PUSH_SUBSCRIBERS_FILE, "w") as f:
        json.dump([MAIN_CHAT_ID], f)  # По умолчанию — главный чат

def load_push_subscribers():
    try:
        with open(PUSH_SUBSCRIBERS_FILE, "r") as f:
            return json.load(f)
    except:
        return [MAIN_CHAT_ID]

def add_push_subscriber(chat_id):
    subs = load_push_subscribers()
    if str(chat_id) not in [str(c) for c in subs]:
        subs.append(str(chat_id))
        with open(PUSH_SUBSCRIBERS_FILE, "w") as f:
            json.dump(subs, f)
        return True
    return False

# === Live-матчи (симуляция) ===
def get_live_matches():
    return [
        {
            'home': 'Arsenal',
            'away': 'Man City',
            'score': '1:1',
            'minute': 67,
            'possession': '52% - 48%',
            'shots': '12 - 9',
            'shots_on_target': '5 - 4',
            'xG': '1.8 - 1.5',
            'danger_attacks': '65 - 58',
            'yellow_cards': '2 - 3',
            'red_cards': '0 - 1',
            'status': 'LIVE',
            'events': []  # События: голы, карточки
        }
    ]

# === Прогноз в live-матче ===
def predict_live_match(match):
    xG1 = float(match['xG'].split(' - ')[0])
    xG2 = float(match['xG'].split(' - ')[1])
    score1, score2 = map(int, match['score'].split(':'))
    time_left = 90 - match['minute']

    adj_xG1 = xG1 + (score1 * 0.5)
    adj_xG2 = xG2 + (score2 * 0.5)

    total_xG = adj_xG1 + adj_xG2
    total_pred = "Over 2.5" if total_xG > 3.0 else "Under 2.5"

    if adj_xG1 > adj_xG2 + 0.5:
        winner = match['home']
        confidence = "Высокая"
    elif adj_xG2 > adj_xG1 + 0.5:
        winner = match['away']
        confidence = "Высокая"
    else:
        winner = "Ничья"
        confidence = "Средняя"

    return {
        'winner': winner,
        'confidence': confidence,
        'total_pred': total_pred,
        'adj_xG': f"{adj_xG1:.2f} — {adj_xG2:.2f}"
    }

# === Отправка сообщения ===
def send_message(chat_id, text, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(BASE_URL + "sendMessage", data=payload, timeout=10)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")

# === Получение обновлений ===
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

# === Генерация событий (для симуляции) ===
def generate_random_event(match):
    import random
    events = ["goal", "yellow", "red", "penalty", "shot_on_target"]
    if random.random() < 0.05:  # 5% шанс события
        return random.choice(events)
    return None

# === Отправка push-уведомления ===
def send_push_notification(message):
    subscribers = load_push_subscribers()
    for chat_id in subscribers:
        send_message(chat_id, message, parse_mode='Markdown')
        logger.info(f"🔔 Push отправлен в {chat_id}")

# === Проверка live-матчей и push-уведомлений ===
def check_live_matches_with_push():
    matches = get_live_matches()
    for match in matches:
        event = generate_random_event(match)
        message = None

        if event == "goal":
            team = match['home'] if random.choice([True, False]) else match['away']
            match['score'] = f"{eval(match['score'].split(':')[0]) + 1}:{match['score'].split(':')[1]}" if team == match['home'] else f"{match['score'].split(':')[0]}:{eval(match['score'].split(':')[1]) + 1}"
            message = f"⚽ *ГОЛ!* {team} забил! Счёт: {match['score']} (мин: {match['minute']})"
        elif event == "yellow":
            team = match['home'] if random.choice([True, False]) else match['away']
            message = f"🟨 *ЖЁЛТАЯ КАРТОЧКА* для игрока {team} (мин: {match['minute']})"
        elif event == "red":
            team = match['home'] if random.choice([True, False]) else match['away']
            message = f"🟥 *КРАСНАЯ КАРТОЧКА* для игрока {team}! {team} остаётся в меньшинстве (мин: {match['minute']})"
        elif event == "penalty":
            team = match['home'] if random.choice([True, False]) else match['away']
            message = f"🎯 *ПЕНАЛЬТИ* для {team}! (мин: {match['minute']})"
        elif event == "shot_on_target":
            team = match['home'] if random.choice([True, False]) else match['away']
            message = f"💥 *УДАР В СТОР! {team}* создаёт момент! (мин: {match['minute']})"

        if message:
            send_push_notification(message)

        # Прогноз каждые 30 секунд
        if datetime.now().second % 30 == 0:
            pred = predict_live_match(match)
            message = (
                f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
                f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
                f"📊 Владение: {match['possession']}\n"
                f"🎯 xG: {match['xG']}\n"
                f"🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
                f"📈 Тотал: {pred['total_pred']}"
            )
            send_push_notification(message)

# === Основной цикл бота ===
def run_bot():
    logger.info("✅ Бот запущен — ожидаем команды...")
    offset = None
    subscribers = load_push_subscribers()

    while True:
        try:
            data = get_updates(offset)
            if data.get("ok") and data.get("result"):
                for item in data["result"]:
                    offset = item["update_id"] + 1
                    msg = item["message"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")

                    if text == "/start":
                        add_push_subscriber(chat_id)
                        send_message(chat_id, "👋 Привет! Ты подписан на push-уведомления.")

                    elif text == "/live":
                        matches = get_live_matches()
                        for match in matches:
                            pred = predict_live_match(match)
                            message = (
                                f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
                                f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
                                f"📊 Владение: {match['possession']}\n"
                                f"🎯 xG: {match['xG']}\n"
                                f"🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
                                f"📈 Тотал: {pred['total_pred']}"
                            )
                            send_message(chat_id, message, parse_mode='Markdown')

                    elif text == "/subscribe_push":
                        if add_push_subscriber(chat_id):
                            send_message(chat_id, "✅ Ты подписан на push-уведомления о матчах!")
                        else:
                            send_message(chat_id, "❌ Ты уже подписан.")

            # Проверка матчей каждые 15 секунд
            check_live_matches_with_push()
            time.sleep(15)

        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>AI Football Analyst — LIVE и Push активны</h1>".encode("utf-8"))

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('', port), Handler)
    logger.info(f"🌍 Веб-сервер запущен на порту {port}")
    server.serve_forever()

# === Запуск ===
if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    run_bot()
