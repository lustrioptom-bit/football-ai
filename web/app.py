# web/app.py
import streamlit as st
import requests
import pandas as pd
from io import StringIO
import threading
import time
from datetime import datetime
from config import TOKEN, MAIN_CHAT_ID

# === Загрузка данных ===
def load_data():
    url = "https://www.football-data.co.uk/mmz4281/2324/E0.csv"
    try:
        df = pd.read_csv(StringIO(requests.get(url).text))
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        return df
    except Exception as e:
        st.error(f"❌ Ошибка загрузки: {e}")
        return pd.DataFrame()

# === Прогноз матча ===
def predict_match(team1, team2, df):
    home_games = df[df['HomeTeam'] == team1]
    away_games = df[df['AwayTeam'] == team2]
    xG1 = home_games['FTHG'].mean() if len(home_games) > 0 else 1.5
    xG2 = away_games['FTAG'].mean() if len(away_games) > 0 else 1.2
    result = "HomeAs Winner" if xG1 > xG2 + 0.3 else "AwayAs Winner" if xG2 > xG1 + 0.3 else "Draw"
    return f"🔮 {result}\nxG: {xG1:.2f} — {xG2:.2f}"

# === Telegram-бот в фоне ===
def run_telegram_bot():
    BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"
    df = load_data()
    offset = None
    st.write("✅ Telegram-бот запущен в фоне...")

    while True:
        try:
            params = {"timeout": 30}
            if offset:
                params["offset"] = offset

            response = requests.get(BASE_URL + "getUpdates", params=params, timeout=35)
            data = response.json()

            if not data["ok"] or not data["result"]:
                time.sleep(1)
                continue

            for item in data["result"]:
                offset = item["update_id"] + 1
                msg = item["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")

                if text == "/start":
                    requests.post(BASE_URL + "sendMessage", data={
                        "chat_id": chat_id,
                        "text": "👋 Привет! Я — AI Football Analyst 🏆\n\nИспользуй:\n• /predict Arsenal Man City"
                    })

                elif text.startswith("/predict"):
                    args = text.split()[1:]
                    if len(args) < 2:
                        requests.post(BASE_URL + "sendMessage", data={
                            "chat_id": chat_id,
                            "text": "❌ Формат: /predict Команда1 Команда2"
                        })
                    else:
                        team1 = args[0]
                        team2 = " ".join(args[1:])
                        if df.empty:
                            requests.post(BASE_URL + "sendMessage", data={
                                "chat_id": chat_id,
                                "text": "❌ Нет данных"
                            })
                        else:
                            pred = predict_match(team1, team2, df)
                            requests.post(BASE_URL + "sendMessage", data={
                                "chat_id": chat_id,
                                "text": pred
                            })

            time.sleep(1)

        except Exception as e:
            print(f"Telegram error: {e}")
            time.sleep(5)

# === Запуск бота в потоке (один раз) ===
if 'bot_thread_started' not in st.session_state:
    st.session_state.bot_thread_started = True
    thread = threading.Thread(target=run_telegram_bot, daemon=True)
    thread.start()

# === Веб-интерфейс ===
st.set_page_config(page_title="⚽ AI Football Analyst", layout="wide")
st.title("🎯 AI Football Analyst Pro")

df = load_data()
if df.empty:
    st.warning("❌ Не удалось загрузить данные")
else:
    st.success("✅ Данные загружены")

st.header("📊 Прогноз матча")
team1 = st.text_input("Команда 1", "Arsenal")
team2 = st.text_input("Команда 2", "Man City")

if st.button("Прогнозировать"):
    if df.empty:
        st.error("❌ Нет данных")
    else:
        pred = predict_match(team1, team2, df)
        st.success(pred)
