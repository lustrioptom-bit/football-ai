# bot.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import json
import requests
import time
import logging
import os
from datetime import datetime, timedelta

# Настройка
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ТВОЙ API-КЛЮЧ ===
RAPIDAPI_KEY = "95f7d440379e618f7b4a78b7b51d245d"

# Конфиг Telegram
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

# === Список топ-лиг ===
TOP_LEAGUES = [
    "Premier League",     # Англия
    "La Liga",            # Испания
    "Bundesliga",         # Германия
    "Serie A",            # Италия
    "Ligue 1"             # Франция
]

# === Загрузка предстоящих матчей из топ-лиг ===
def get_upcoming_matches():
    now = datetime.now()
    from_time = int(now.timestamp())
    to_time = int((now + timedelta(hours=2)).timestamp())  # На 2 часа вперёд

    url = f"https://v3.football.api-sports.io/fixtures?league=39,140,78,135,61&from={now.strftime('%Y-%m-%d')}&to={now.strftime('%Y-%m-%d')}"
    headers = {
        'x-rapidapi-host': 'v3.football.api-sports.io',
        'x-rapidapi-key': RAPIDAPI_KEY
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            matches = []
            for event in data['response']:
                try:
                    fixture = event['fixture']
                    teams = event['teams']
                    league_name = event['league']['name']
                    if league_name not in TOP_LEAGUES:
                        continue

                    match_time = datetime.fromtimestamp(fixture['timestamp'])
                    time_diff = match_time - now

                    # Только если матч начнётся через 25–35 минут
                    if timedelta(minutes=25) < time_diff <= timedelta(minutes=35):
                        match_data = {
                            'home': teams['home']['name'],
                            'away': teams['away']['name'],
                            'start_time': match_time.strftime('%H:%M'),
                            'league': league_name,
                            'status': fixture['status']['short']
                        }
                        # Коэффициенты (B365)
                        if 'bookmakers' in event.get('odds', {}):
                            for bookmaker in event['odds']['bookmakers']:
                                if bookmaker['id'] == 8:  # Bet365
                                    for bet in bookmaker['bets']:
                                        if bet['name'] == 'Match Winner':
                                            odds = bet['values']
                                            match_data['odds_home'] = odds[0]['odd']
                                            match_data['odds_draw'] = odds[1]['odd']
                                            match_data['odds_away'] = odds[2]['odd']
                        matches.append(match_data)
                except Exception as e:
                    logger.warning(f"Пропущен матч: {e}")
                    continue
            return matches
        else:
            logger.error(f"❌ Ошибка API-Football: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"❌ Ошибка запроса: {e}")
        return []

# === Прогноз до матча ===
def predict_pre_match(home, away):
    # Имитация xG на основе команд (в реальности — из статистики)
    xG_home = round(1.2 + (hash(home) % 100) / 100, 2)
    xG_away = round(1.0 + (hash(away) % 100) / 100, 2)
    total_xG = xG_home + xG_away

    if xG_home > xG_away + 0.3:
        winner = home
        confidence = "Высокая"
    elif xG_away > xG_home + 0.3:
        winner = away
        confidence = "Высокая"
    else:
        winner = "Ничья"
        confidence = "Средняя"

    total_pred = "Over 2.5" if total_xG > 2.6 else "Under 2.5"
    return {
        'xG_home': xG_home,
        'xG_away': xG_away,
        'total_xG': total_xG,
        'winner': winner,
        'confidence': confidence,
        'total_pred': total_pred
    }

# === Сравнение AI и коэффициентов ===
def compare_ai_vs_odds(ai_probs, odds_home, odds_draw, odds_away):
    implied = {
        'H': 1 / float(odds_home),
        'D': 1 / float(odds_draw),
        'A': 1 / float(odds_away)
    }
    total = sum(implied.values())
    bookie_probs = {k: v / total for k, v in implied.items()}
    edge = {k: ai_probs[k] - bookie_probs[k] for k in ai_probs}
    return bookie_probs, edge

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

# === Проверка предстоящих матчей (за 30 мин до старта) ===
def check_upcoming_matches(roi_tracker):
    matches = get_upcoming_matches()
    for match in matches:
        pred = predict_pre_match(match['home'], match['away'])
        message = (
            f"⏰ *ПРЕДМАТЧЕВЫЙ ПРОГНОЗ*\n"
            f"🔥 {match['home']} vs {match['away']}\n"
            f"🏆 {match['league']}\n"
            f"⏱️ Начало: {match['start_time']}\n"
            f"🎯 xG: {pred['xG_home']} — {pred['xG_away']}\n"
        )
        if 'odds_home' in match:
            message += f"📘 B365: H{match['odds_home']} D{match['odds_draw']} A{match['odds_away']}\n"

        # Сигналы
        if 'odds_home' in match:
            ai_probs = {'H': 0.55, 'D': 0.25, 'A': 0.20}
            bookie, edge = compare_ai_vs_odds(ai_probs, match['odds_home'], match['odds_draw'], match['odds_away'])
            signals = [k for k, v in edge.items() if v > 0.10]
            if signals:
                signal_str = " | ".join([{'H': match['home'], 'D': 'Ничья', 'A': match['away']}[s] for s in signals])
                message += f"\n💥 *СИГНАЛ НА СТАВКУ!* 🔥\n🎯 {signal_str}"
                # Симуляция ставки
                odds = {'H': match['odds_home'], 'D': match['odds_draw'], 'A': match['odds_away']}[signals[0]]
                roi_tracker.place_bet(amount=10, odds=float(odds), win=True, match=f"{match['home']} vs {match['away']}")

        message += (
            f"\n🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
            f"📈 Тотал: *{pred['total_pred']}*"
        )
        send_message(MAIN_CHAT_ID, message, parse_mode='Markdown')
        logger.info(f"🔔 Предматч: {match['home']} vs {match['away']}")

# === Основной цикл бота ===
def run_bot():
    logger.info("✅ Бот запущен — ожидаем команды...")
    offset = None
    roi_tracker = ROI_Tracker()

    while True:
        try:
            # Проверка каждые 5 минут
            if datetime.now().minute % 5 == 0:
                check_upcoming_matches(roi_tracker)
                time.sleep(60)
            else:
                time.sleep(30)

            # Обработка команд
            data = get_updates(offset)
            if data.get("ok") and data.get("result"):
                for item in data["result"]:
                    offset = item["update_id"] + 1
                    msg = item["message"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")

                    if text == "/start":
                        add_push_subscriber(chat_id)
                        send_message(chat_id, "👋 Привет! Предматчевые прогнозы за 30 минут до старта активны.")

                    elif text == "/upcoming":
                        matches = get_upcoming_matches()
                        if not matches:
                            send_message(chat_id, "📅 Нет предстоящих матчей в ближайшие 30 минут.")
                        else:
                            for match in matches:
                                pred = predict_pre_match(match['home'], match['away'])
                                message = (
                                    f"⏰ *{match['home']} vs {match['away']}*\n"
                                    f"🏆 {match['league']}\n"
                                    f"⏱️ {match['start_time']}\n"
                                    f"🎯 xG: {pred['xG_home']} — {pred['xG_away']}\n"
                                    f"🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
                                    f"📈 Тотал: *{pred['total_pred']}*"
                                )
                                if 'odds_home' in match:
                                    message += f"\n📘 B365: H{match['odds_home']} D{match['odds_draw']} A{match['odds_away']}"
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

        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер для Render ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>AI Football Analyst — Предматчевые прогнозы активны</h1>".encode("utf-8"))

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
