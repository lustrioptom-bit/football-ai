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

# === Live-матчи (симуляция) ===
def get_live_matches():
    # В реальности — из API (например, SofaScore, Sportmonks)
    return [
        {
            'home': 'Arsenal',
            'away': 'Man City',
            'score': '1:1',
            'minute': 67,
            'possession': '52% - 48%',
            'shots': '12 - 9',
            'xG': '1.8 - 1.5',
            'danger_attacks': '65 - 58',
            'status': 'LIVE'
        },
        {
            'home': 'Liverpool',
            'away': 'Chelsea',
            'score': '0:0',
            'minute': 34,
            'possession': '60% - 40%',
            'shots': '7 - 4',
            'xG': '0.9 - 0.6',
            'danger_attacks': '45 - 30',
            'status': 'LIVE'
        }
    ]

# === Прогноз в live-матче ===
def predict_live_match(match):
    xG1 = float(match['xG'].split(' - ')[0])
    xG2 = float(match['xG'].split(' - ')[1])
    score1, score2 = map(int, match['score'].split(':'))
    time_left = 90 - match['minute']

    # Учитываем счёт и xG
    adj_xG1 = xG1 + (score1 * 0.5)
    adj_xG2 = xG2 + (score2 * 0.5)

    total_xG = adj_xG1 + adj_xG2
    if total_xG > 3.0:
        total_pred = "Over 2.5"
    else:
        total_pred = "Under 2.5"

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

# === ROI-трекер ===
class ROI_Tracker:
    def __init__(self):
        self.total_bet = 0
        self.profit = 0
        self.wins = 0
        self.total = 0
        self.history = []

    def place_bet(self, amount=10, odds=1.8, win=True, match="Unknown"):
        self.total += 1
        self.total_bet += amount
        result = "Выигрыш" if win else "Проигрыш"
        if win:
            self.profit += amount * (odds - 1)
            self.wins += 1
        else:
            self.profit -= amount
        self.history.append({
            'match': match,
            'amount': amount,
            'odds': odds,
            'result': result,
            'profit': round(amount * (odds - 1) if win else -amount, 2),
            'date': datetime.now().strftime('%d.%m %H:%M')
        })

    def report(self):
        accuracy = self.wins / self.total if self.total else 0
        roi = (self.profit / self.total_bet) * 100 if self.total_bet else 0
        return {
            'total': self.total,
            'profit': round(self.profit, 1),
            'accuracy': round(accuracy * 100, 1),
            'roi': round(roi, 1)
        }

# === Подписчики ===
SUBSCRIBERS_FILE = "subscribers.json"
if not os.path.exists(SUBSCRIBERS_FILE):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump({"free": [], "paid": []}, f)

def load_subscribers():
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return json.load(f)
    except:
        return {"free": [], "paid": []}

def is_subscriber(chat_id):
    subs = load_subscribers()
    return str(chat_id) in subs["paid"] or str(chat_id) in subs["free"]

def add_free_trial(chat_id):
    subs = load_subscribers()
    if str(chat_id) not in subs["free"]:
        subs["free"].append(str(chat_id))
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(subs, f)
        return True
    return False

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

# === Проверка live-матчей ===
def check_live_matches(roi_tracker):
    now = datetime.now()
    # Каждые 15 секунд обновляем live-прогнозы
    if now.second % 15 == 0:
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
            send_message(MAIN_CHAT_ID, message, parse_mode='Markdown')
            logger.info(f"🔴 Live: {match['home']} vs {match['away']} — {match['score']}")
        time.sleep(1)

# === Основной цикл бота ===
def run_bot():
    logger.info("✅ Бот запущен — ожидаем команды...")
    offset = None
    subscribers = load_subscribers()
    roi_tracker = ROI_Tracker()

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
                        if is_subscriber(chat_id):
                            send_message(chat_id, "👋 Привет! У тебя есть доступ к прогнозам.")
                        else:
                            send_message(chat_id, "👋 Привет! Напиши /trial, чтобы получить 14 дней бесплатно.")

                    elif text == "/trial":
                        if add_free_trial(chat_id):
                            send_message(chat_id, "🎉 Ты получил 14 дней бесплатного доступа! Используй /live")
                        else:
                            send_message(chat_id, "❌ Ты уже использовал бесплатный период.")

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

                    elif text == "/roi":
                        report = roi_tracker.report()
                        message = (
                            f"📊 *Отчёт по ставкам*\n"
                            f"• Ставок: {report['total']}\n"
                            f"• Прибыль: {report['profit']} у.е.\n"
                            f"• Точность: {report['accuracy']}%\n"
                            f"• ROI: {report['roi']}%"
                        )
                        send_message(chat_id, message, parse_mode='Markdown')

            # Проверка live-матчей каждые 15 секунд
            check_live_matches(roi_tracker)

        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>AI Football Analyst — LIVE-прогнозы активны</h1>".encode("utf-8"))

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
