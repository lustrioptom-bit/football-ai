# bot.py
from config import TOKEN, MAIN_CHAT_ID
import requests
import time
import logging
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

def load_data():
    url = "https://www.football-data.co.uk/mmz4281/2324/E0.csv"
    try:
        response = requests.get(url, timeout=10)
        df = pd.read_csv(StringIO(response.text))
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df['DateTime'] = df['Date']
        logger.info(f"✅ Данные загружены: {len(df)} матчей")
        return df
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return pd.DataFrame()

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

def send_message(chat_id, text, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(BASE_URL + "sendMessage", data=payload, timeout=10)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")

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

def check_upcoming_matches(df, context_chat_id):
    now = datetime.now()
    one_hour_later = now + timedelta(hours=1)
    window_start = one_hour_later - timedelta(minutes=5)
    window_end = one_hour_later + timedelta(minutes=5)
    test_match = df.iloc[0].copy()
    test_match['DateTime'] = now + timedelta(hours=1, minutes=10)
    if (test_match['DateTime'] > window_start) and (test_match['DateTime'] <= window_end):
        home = test_match['HomeTeam']
        away = test_match['AwayTeam']
        pred = predict_match(home, away, df)
        message = (
            f"⏰ *Предстоящий матч*\n"
            f"{home} ⚔️ {away}\n\n"
            f"🔮 *Прогноз AI*:\n"
            f"• Победитель: *{pred['result']}*\n"
            f"• Счёт: {pred['score']}\n"
            f"• xG: {pred['xG1']} — {pred['xG2']}"
        )
        send_message(context_chat_id, message, parse_mode='Markdown')
        logger.info(f"🔔 Уведомление: {home} vs {away}")

def main():
    logger.info("✅ Бот запущен — ожидаем команды...")
    offset = None
    df = load_data()
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
                        send_message(chat_id, "👋 Привет! Используй /predict Arsenal Man City")
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
            if datetime.now().minute % 5 == 0:
                if not df.empty:
                    check_upcoming_matches(df, MAIN_CHAT_ID)
                time.sleep(60)
            else:
                time.sleep(30)
        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен")
            break
        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
