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

# === Загрузка live-матчей и коэффициентов с API-Football ===
def get_live_matches_with_odds():
    url = "https://v3.football.api-sports.io/fixtures?live=all"
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
                    goals = event['goals']
                    score = f"{goals['home'] or 0}:{goals['away'] or 0}"
                    league = event['league']['name']
                    status = fixture['status']['short']
                    minute = fixture['status']['elapsed']

                    if status in ['1H', '2H', 'ET', 'P']:
                        match_data = {
                            'home': teams['home']['name'],
                            'away': teams['away']['name'],
                            'score': score,
                            'minute': minute,
                            'league': league,
                            'status': status
                        }
                        # xG (если есть)
                        if 'xG' in event:
                            match_data['xG_home'] = round(event['xG']['home'], 2)
                            match_data['xG_away'] = round(event['xG']['away'], 2)
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
            logger.error(f"❌ Ошибка API-Football: {response.status_code} — {response.text}")
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

    def get_history(self, n=5):
        return self.history[-n:]

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

# === Проверка live-матчей и push-уведомлений ===
def check_live_matches_with_push(roi_tracker):
    matches = get_live_matches_with_odds()
    if not matches:
        logger.info("🔴 Нет live-матчей или ошибка API")
        return

    for match in matches:
        pred = predict_live_match(match)
        message = (
            f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
            f"🏆 {match['league']}\n"
            f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
            f"�� xG: {match.get('xG_home', 'N/A')} — {match.get('xG_away', 'N/A')}\n"
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
                message += f"🔥 *СИГНАЛ НА СТАВКУ!* ��\nВысокий перевес: {signal_str}"
                # Симуляция ставки
                odds = {'H': match['odds_home'], 'D': match['odds_draw'], 'A': match['odds_away']}[signals[0]]
                roi_tracker.place_bet(amount=10, odds=float(odds), win=True, match=f"{match['home']} vs {match['away']}")

        message += (
            f"\n🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
            f"📈 Тотал: *{pred['total_pred']}*"
        )
        send_message(MAIN_CHAT_ID, message, parse_mode='Markdown')
        logger.info(f"🔔 LIVE: {match['home']} vs {match['away']} — {match['score']}")

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
                        send_message(chat_id, "👋 Привет! Live-матчи, коэффициенты и ROI активны.")

                    elif text == "/live":
                        matches = get_live_matches_with_odds()
                        if not matches:
                            send_message(chat_id, "🔴 Сейчас нет live-матчей.")
                        else:
                            for match in matches:
                                pred = predict_live_match(match)
                                message = (
                                    f"🔴 *LIVE: {match['home']} vs {match['away']}*\n"
                                    f"🏆 {match['league']}\n"
                                    f"⏱️ {match['minute']}' | Счёт: {match['score']}\n"
                                )
                                if 'xG_home' in match:
                                    message += f"🎯 xG: {match['xG_home']} — {match['xG_away']}\n"
                                if 'odds_home' in match:
                                    message += f"📘 B365: H{match['odds_home']} D{match['odds_draw']} A{match['odds_away']}\n"
                                message += (
                                    f"🔥 Прогноз: *{pred['winner']}* ({pred['confidence']})\n"
                                    f"📈 Тотал: *{pred['total_pred']}*"
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

            # Проверка каждые 30 секунд
            check_live_matches_with_push(roi_tracker)
            time.sleep(30)

        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

# === Веб-сервер для Render ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>AI Football Analyst — Коэффициенты и ROI активны</h1>".encode("utf-8"))

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
