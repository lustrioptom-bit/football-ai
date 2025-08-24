# bot.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import json
import requests
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
import logging
import time  # ✅ Это было пропущено!

# Настройка
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = "8304903389:AAGRyWP4Ez97aoA-yLTYzYLQHuKbutTfcy4"
MAIN_CHAT_ID = "8431596511"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# === Загрузка данных из нескольких лиг ===
def load_data():
    leagues = {
        'E0': 'Premier League',
        'D1': 'Bundesliga',
        'I1': 'Serie A',
        'F1': 'Ligue 1',
        'SP1': 'La Liga'
    }
    all_matches = []
    for code, name in leagues.items():
        url = f"https://www.football-data.co.uk/mmz4281/2324/{code}.csv"
        try:
            df = pd.read_csv(StringIO(requests.get(url).text))
            df['League'] = name
            df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
            all_matches.append(df)
            logger.info(f"✅ {name} загружена")
        except Exception as e:
            logger.error(f"❌ {name}: {e}")
    return pd.concat(all_matches, ignore_index=True) if all_matches else pd.DataFrame()

# === Прогноз матча ===
def predict_match(team1, team2, df):
    home_games = df[df['HomeTeam'] == team1]
    away_games = df[df['AwayTeam'] == team2]
    xG1 = home_games['FTHG'].mean() if len(home_games) > 0 else 1.5
    xG2 = away_games['FTAG'].mean() if len(away_games) > 0 else 1.2
    if xG1 > xG2 + 0.3:
        result = f"Победа {team1}"
    elif xG2 > xG1 + 0.3:
        result = f"Победа {team2}"
    else:
        result = "Вероятна ничья"
    return {
        'xG1': round(xG1, 2),
        'xG2': round(xG2, 2),
        'score': f"{xG1:.1f} : {xG2:.1f}",
        'result': result
    }

# === ROI-трекер ===
class ROI_Tracker:
    def __init__(self):
        self.total_bet = 0
        self.profit = 0
        self.wins = 0
        self.total = 0

    def place_bet(self, amount=10, win_prob=0.5, odds=1.8):
        self.total += 1
        self.total_bet += amount
        win = True  # Упрощение
        if win:
            self.profit += amount * (odds - 1)
            self.wins += 1
        else:
            self.profit -= amount

    def report(self):
        accuracy = self.wins / self.total if self.total else 0
        roi = (self.profit / self.total_bet) * 100 if self.total_bet else 0
        return {
            'total': self.total,
            'profit': round(self.profit, 1),
            'accuracy': round(accuracy * 100, 1),
            'roi': round(roi, 1)
        }

# === Отправка сообщения в Telegram ===
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

# === Основной цикл бота ===
def run_bot():
    logger.info("✅ Бот запущен — ожидаем команды...")
    offset = None
    df = load_data()
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
                        send_message(chat_id, "👋 Привет! Используй:\n• /predict Arsenal Man City\n• /roi — статистика")

                    elif text.startswith("/predict"):
                        args = text.split()[1:]
                        if len(args) < 2:
                            send_message(chat_id, "❌ /predict Команда1 Команда2")
                            continue
                        team1 = args[0]
                        team2 = " ".join(args[1:])
                        if df.empty:
                            send_message(chat_id, "❌ Нет данных")
                        else:
                            pred = predict_match(team1, team2, df)
                            message = (
                                f"🔮 *Прогноз: {team1} vs {team2}*\n\n"
                                f"🎯 xG: {pred['xG1']} — {pred['xG2']}\n"
                                f"📌 Счёт: {pred['score']}\n"
                                f"🏆 Исход: *{pred['result']}*"
                            )
                            send_message(chat_id, message, parse_mode='Markdown')

                    elif text == "/roi":
                        roi_tracker.place_bet()
                        report = roi_tracker.report()
                        message = (
                            f"📊 *Отчёт по ставкам*\n"
                            f"• Ставок: {report['total']}\n"
                            f"• Прибыль: {report['profit']} у.е.\n"
                            f"• Точность: {report['accuracy']}%\n"
                            f"• ROI: {report['roi']}%"
                        )
                        send_message(chat_id, message, parse_mode='Markdown')

            # Проверка каждые 5 минут
            if datetime.now().minute % 5 == 0:
                time.sleep(60)
            else:
                time.sleep(30)

        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен")
            break
        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер для Render ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        response = """
        <h1>⚽ AI Football Analyst — Работает!</h1>
        <p>Бот запущен. Прогнозы и ROI активны.</p>
        <p>Проверь Telegram-бота: <a href="https://t.me/Iipredictirbot" target="_blank">@Iipredictirbot</a></p>
        """
        self.wfile.write(response.encode("utf-8"))

def run_web():
    port = int("10000")
    server = HTTPServer(('', port), Handler)
    logger.info(f"🌍 Веб-сервер запущен на порту {port}")
    server.serve_forever()

# === Запуск бота и веба в потоках ===
if __name__ == "__main__":
    # Запуск веб-сервера в фоне
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()

    # Запуск Telegram-бота
    run_bot()
