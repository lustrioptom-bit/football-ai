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

# === Загрузка данных из football-data.co.uk ===
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
            'b365_h': 2.1,
            'b365_d': 3.4,
            'b365_a': 3.6,
            'status': 'LIVE'
        },
        {
            'home': 'Liverpool',
            'away': 'Chelsea',
            'score': '0:0',
            'minute': 34,
            'possession': '60% - 40%',
            'shots': '7 - 4',
            'shots_on_target': '3 - 2',
            'xG': '0.9 - 0.6',
            'b365_h': 1.9,
            'b365_d': 3.8,
            'b365_a': 4.2,
            'status': 'LIVE'
        }
    ]

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
        'result': result
    }

# === Прогноз тотала (over/under 2.5) ===
def predict_total(team1, team2, df):
    pred = predict_match(team1, team2, df)
    total_xG = pred['xG1'] + pred['xG2']
    if total_xG > 2.7:
        return {'total': 'Over 2.5', 'confidence': 'Высокая', 'total_xG': total_xG}
    elif total_xG > 2.3:
        return {'total': 'Over 2.5', 'confidence': 'Средняя', 'total_xG': total_xG}
    else:
        return {'total': 'Under 2.5', 'confidence': 'Высокая', 'total_xG': total_xG}

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

# === Генерация событий (для симуляции) ===
def generate_random_event(match):
    import random
    events = ["goal", "yellow", "red", "penalty", "shot_on_target"]
    if random.random() < 0.05:
        return random.choice(events)
    return None

# === Отправка push-уведомлений ===
def send_push_notification(message):
    subscribers = load_push_subscribers()
    for chat_id in subscribers:
        send_message(chat_id, message, parse_mode='Markdown')

# === Проверка live-матчей и push-уведомлений ===
def check_live_matches_with_push(df, roi_tracker):
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
            message = f"💥 *УДАР В СТОР!* {team} создаёт момент! (мин: {match['minute']})"

        if message:
            send_push_notification(message)

        # Прогноз каждые 30 секунд
        if datetime.now().second % 30 == 0:
            pred = predict_match(match['home'], match['away'], df)
            total_pred = predict_total(match['home'], match['away'], df)
            message = (
                f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
                f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
                f"📊 Владение: {match['possession']}\n"
                f"🎯 xG: {match['xG']}\n"
                f"🔥 Прогноз: *{pred['result']}*\n"
                f"📈 Тотал: *{total_pred['total']}* ({total_pred['confidence']})"
            )
            send_push_notification(message)

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
                        add_push_subscriber(chat_id)
                        send_message(chat_id, "👋 Привет! Ты подписан на push-уведомления.")

                    elif text == "/live":
                        matches = get_live_matches()
                        for match in matches:
                            pred = predict_match(match['home'], match['away'], df)
                            total_pred = predict_total(match['home'], match['away'], df)
                            message = (
                                f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
                                f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
                                f"📊 Владение: {match['possession']}\n"
                                f"🎯 xG: {match['xG']}\n"
                                f"🔥 Прогноз: *{pred['result']}*\n"
                                f"📈 Тотал: *{total_pred['total']}* ({total_pred['confidence']})"
                            )
                            send_message(chat_id, message, parse_mode='Markdown')

                    elif text.startswith("/predict"):
                        args = text.split()[1:]
                        if len(args) >= 2:
                            team1, team2 = args[0], " ".join(args[1:])
                            pred = predict_match(team1, team2, df)
                            message = (
                                f"🔮 *Прогноз: {team1} vs {team2}*\n\n"
                                f"🎯 xG: {pred['xG1']} — {pred['xG2']}\n"
                                f"🏆 Исход: *{pred['result']}*"
                            )
                            send_message(chat_id, message, parse_mode='Markdown')

                    elif text.startswith("/total"):
                        args = text.split()[1:]
                        if len(args) >= 2:
                            team1, team2 = args[0], " ".join(args[1:])
                            total_pred = predict_total(team1, team2, df)
                            message = (
                                f"🎯 *Прогноз на тотал: {team1} vs {team2}*\n\n"
                                f"• Сумма xG: {total_pred['total_xG']:.2f}\n"
                                f"• Прогноз: *{total_pred['total']}*\n"
                                f"• Уверенность: {total_pred['confidence']}"
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

            # Проверка live-матчей каждые 15 секунд
            if df is not None:
                check_live_matches_with_push(df, roi_tracker)
            time.sleep(15)

        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер для Render ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>AI Football Analyst — LIVE, Push, ROI, Тоталы, Коэффициенты</h1>".encode("utf-8"))

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('', port), Handler)
    logger.info(f"🌍 Веб-сервер запущен на порту {port}")
    server.serve_forever()

# === Запуск бота и веба ===
if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    run_bot()
