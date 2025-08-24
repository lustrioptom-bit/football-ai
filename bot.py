# bot.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import json
import requests
import time
import logging
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
        json.dump([MAIN_CHAT_ID], f)

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

# === Загрузка live-матчей с SofaScore через прокси ===
def get_sofascore_live():
    url = "https://api-pub.sb.scoreticker.com/api/v1/sport/football/events/live"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.sofascore.com/',
        'Origin': 'https://www.sofascore.com',
        'Sec-Fetch-Site': 'same-origin',
        'Connection': 'keep-alive'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            matches = []
            for event in data.get('events', []):
                try:
                    home = event['homeTeam']['name']
                    away = event['awayTeam']['name']
                    score = f"{event['homeScore']['current']}:{event['awayScore']['current']}"
                    minute = event['minute']
                    status = event['status']['type']
                    if status in ["live", "paused"]:
                        match_data = {
                            'home': home,
                            'away': away,
                            'score': score,
                            'minute': minute,
                            'status': status
                        }
                        if 'xG' in event:
                            match_data['xG_home'] = round(event['xG']['home'], 2)
                            match_data['xG_away'] = round(event['xG']['away'], 2)
                        if 'statistics' in event:
                            for stat in event['statistics']:
                                if stat['type'] == 'possession':
                                    match_data['possession'] = f"{stat['home']}% - {stat['away']}%"
                                elif stat['type'] == 'attacks':
                                    match_data['attacks'] = f"{stat['home']} - {stat['away']}"
                                elif stat['type'] == 'dangerous_attacks':
                                    match_data['danger_attacks'] = f"{stat['home']} - {stat['away']}"
                        matches.append(match_data)
                except: continue
            return matches
        else:
            logger.error(f"❌ Ошибка SofaScore: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return []

# === Прогноз в live-матче ===
def predict_live_match(match):
    xG1 = match.get('xG_home', 0.0)
    xG2 = match.get('xG_away', 0.0)
    score1, score2 = map(int, match['score'].split(':'))
    total_xG = xG1 + xG2
    adj_xG1 = xG1 + (score1 * 0.5)
    adj_xG2 = xG2 + (score2 * 0.5)
    if adj_xG1 > adj_xG2 + 0.5:
        winner = match['home']
        confidence = "Высокая"
    elif adj_xG2 > adj_xG1 + 0.5:
        winner = match['away']
        confidence = "Высокая"
    else:
        winner = "Ничья"
        confidence = "Средняя"
    total_pred = "Over 2.5" if total_xG > 2.7 else "Under 2.5"
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
            'date': time.strftime('%d.%m %H:%M')
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

# === Проверка live-матчей ===
def check_live_matches_with_push(roi_tracker):
    matches = get_sofascore_live()
    if not matches:
        logger.info("🔴 Нет live-матчей")
        return

    for match in matches:
        pred = predict_live_match(match)
        message = (
            f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
            f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
        )
        if 'xG_home' in match:
            message += f"🎯 xG: {match['xG_home']} — {match['xG_away']}\n"
        if 'possession' in match:
            message += f"�� Владение: {match['possession']}\n"
        message += (
            f"🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
            f"📈 Тотал: *{pred['total_pred']}*"
        )
        send_message(MAIN_CHAT_ID, message, parse_mode='Markdown')

# === Основной цикл бота ===
def run_bot():
    logger.info("✅ Бот запущен — ожидаем команды...")
    offset = None
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
                        send_message(chat_id, "👋 Привет! Live-матчи с SofaScore работают.")

                    elif text == "/live":
                        matches = get_sofascore_live()
                        if not matches:
                            send_message(chat_id, "🔴 Сейчас нет live-матчей.")
                        else:
                            for match in matches:
                                pred = predict_live_match(match)
                                message = (
                                    f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
                                    f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
                                )
                                if 'xG_home' in match:
                                    message += f"🎯 xG: {match['xG_home']} — {match['xG_away']}\n"
                                if 'possession' in match:
                                    message += f"📊 Владение: {match['possession']}\n"
                                message += (
                                    f"🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
                                    f"📈 Тотал: *{pred['total_pred']}*"
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

            check_live_matches_with_push(roi_tracker)
            time.sleep(30)

        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>AI Football Analyst — Live-матчи с SofaScore</h1>".encode("utf-8"))

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
