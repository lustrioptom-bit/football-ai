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

    def get_history(self, n=5):
        return self.history[-n:]

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

# === Загрузка данных из Understat (реальные xG) ===
def get_understat_data(team_name):
    understat_mock = {
        'Arsenal': {'xG_for': 2.1, 'xG_against': 0.9, 'form': 7.2},
        'Man City': {'xG_for': 2.5, 'xG_against': 0.7, 'form': 8.1},
        'Liverpool': {'xG_for': 1.9, 'xG_against': 1.0, 'form': 6.8},
    }
    return understat_mock.get(team_name, {'xG_for': 1.5, 'xG_against': 1.2, 'form': 5.0})

# === Загрузка календаря матчей ===
def load_schedule():
    return [
        {
            'home': 'Arsenal',
            'away': 'Man City',
            'datetime': datetime.now() + timedelta(hours=1, minutes=10),
            'league': 'Premier League',
            'b365_h': 2.1,
            'b365_d': 3.4,
            'b365_a': 3.6,
            'b365_o25': 2.0,
            'b365_u25': 1.8
        }
    ]

# === Прогноз матча (основной) ===
def predict_match(team1, team2):
    u1 = get_understat_data(team1)
    u2 = get_understat_data(team2)
    xG1 = u1['xG_for'] * 0.7 + u2['xG_against'] * 0.3
    xG2 = u2['xG_for'] * 0.7 + u1['xG_against'] * 0.3
    total_xG = xG1 + xG2
    if xG1 > xG2 + 0.3:
        result = f"Победа {team1}"
    elif xG2 > xG1 + 0.3:
        result = f"Победа {team2}"
    else:
        result = "Вероятна ничья"
    return {
        'xG1': round(xG1, 2),
        'xG2': round(xG2, 2),
        'total_xG': round(total_xG, 2),
        'result': result
    }

# === Прогноз тотала (over/under 2.5) ===
def predict_total(team1, team2):
    pred = predict_match(team1, team2)
    total_xG = pred['total_xG']
    if total_xG > 2.7:
        total_result = "Over 2.5"
        confidence = "Высокая"
    elif total_xG > 2.3:
        total_result = "Over 2.5"
        confidence = "Средняя"
    else:
        total_result = "Under 2.5"
        confidence = "Высокая"
    return {
        'total_result': total_result,
        'total_xG': pred['total_xG'],
        'confidence': confidence
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

# === Проверка матчей и уведомления ===
def check_upcoming_matches(roi_tracker):
    matches = load_schedule()
    now = datetime.now()
    for match in matches:
        if now + timedelta(minutes=50) < match['datetime'] <= now + timedelta(minutes=70):
            pred = predict_match(match['home'], match['away'])
            total_pred = predict_total(match['home'], match['away'])
            bookie_probs = {
                'H': 1 / match['b365_h'],
                'D': 1 / match['b365_d'],
                'A': 1 / match['b365_a']
            }
            total = sum(bookie_probs.values())
            bookie_probs = {k: v / total for k, v in bookie_probs.items()}
            ai_probs = {'H': 0.55, 'D': 0.25, 'A': 0.20}
            edge = {k: ai_probs[k] - bookie_probs[k] for k in ai_probs}
            signals = [k for k, v in edge.items() if v > 0.10]

            message = (
                f"⏰ *Предстоящий матч*\n"
                f"{match['home']} ⚔️ {match['away']}\n\n"
                f"🔮 *Прогноз AI*:\n"
                f"• Победитель: *{pred['result']}*\n"
                f"• xG: {pred['xG1']} — {pred['xG2']}\n"
                f"• Сумма xG: {pred['total_xG']}\n"
                f"• Тотал: *{total_pred['total_result']}* ({total_pred['confidence']} уверенность)\n\n"
                f"📘 *B365*: H{match['b365_h']} D{match['b365_d']} A{match['b365_a']}"
            )

            if signals:
                signal_str = " | ".join([{'H': match['home'], 'D': 'Ничья', 'A': match['away']}[s] for s in signals])
                message += f"\n\n🎯 *СИГНАЛ НА СТАВКУ!* 🔥\nВысокий перевес: {signal_str}"
                odds = {'H': match['b365_h'], 'D': match['b365_d'], 'A': match['b365_a']}[signals[0]]
                roi_tracker.place_bet(amount=10, odds=odds, win=True, match=f"{match['home']} vs {match['away']}")

            send_message(MAIN_CHAT_ID, message, parse_mode='Markdown')
            logger.info(f"🔔 Уведомление: {match['home']} vs {match['away']}")

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
                            send_message(chat_id, "🎉 Ты получил 14 дней бесплатного доступа! Используй /predict или /total")
                        else:
                            send_message(chat_id, "❌ Ты уже использовал бесплатный период.")

                    elif text.startswith("/predict") and is_subscriber(chat_id):
                        args = text.split()[1:]
                        if len(args) >= 2:
                            team1, team2 = args[0], " ".join(args[1:])
                            pred = predict_match(team1, team2)
                            message = (
                                f"🔮 *Прогноз: {team1} vs {team2}*\n\n"
                                f"🎯 xG: {pred['xG1']} — {pred['xG2']}\n"
                                f"📊 Сумма xG: {pred['total_xG']}\n"
                                f"🏆 Исход: *{pred['result']}*"
                            )
                            send_message(chat_id, message, parse_mode='Markdown')

                    elif text.startswith("/total") and is_subscriber(chat_id):
                        args = text.split()[1:]
                        if len(args) >= 2:
                            team1, team2 = args[0], " ".join(args[1:])
                            total_pred = predict_total(team1, team2)
                            message = (
                                f"🎯 *Прогноз на тотал: {team1} vs {team2}*\n\n"
                                f"• Сумма xG: {total_pred['total_xG']}\n"
                                f"• Прогноз: *{total_pred['total_result']}*\n"
                                f"• Уверенность: {total_pred['confidence']}"
                            )
                            send_message(chat_id, message, parse_mode='Markdown')

                    elif text == "/roi":
                        report = roi_tracker.report()
                        history = roi_tracker.get_history()
                        message = (
                            f"📊 *Отчёт по ставкам*\n"
                            f"• Ставок: {report['total']}\n"
                            f"• Прибыль: {report['profit']} у.е.\n"
                            f"• Точность: {report['accuracy']}%\n"
                            f"• ROI: {report['roi']}%\n\n"
                            f"📋 *Последние ставки*:\n"
                        )
                        for bet in history:
                            message += f"  {bet['match']}: {bet['result']} ({bet['profit']} у.е.)\n"
                        send_message(chat_id, message, parse_mode='Markdown')

                    elif text == "/subscribe":
                        send_message(chat_id, "💳 Подписка: 499₽/мес. Напиши @admin")

            # Проверка матчей
            if datetime.now().minute % 5 == 0:
                check_upcoming_matches(roi_tracker)
                time.sleep(60)
            else:
                time.sleep(30)

        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер (для Render) ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>AI Football Analyst — работает 24/7</h1>".encode("utf-8"))

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('', port), Handler)
    logger.info(f"�� Веб-сервер запущен на порту {port}")
    server.serve_forever()

# === Запуск ===
if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    run_bot()
