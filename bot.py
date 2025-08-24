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

# === Словарь лиг: код → название → страна ===
LEAGUES = {
    'E0': {'name': 'Premier League', 'country': 'Англия', 'url': 'https://www.football-data.co.uk/mmz4281/2324/E0.csv'},
    'D1': {'name': 'Bundesliga', 'country': 'Германия', 'url': 'https://www.football-data.co.uk/mmz4281/2324/D1.csv'},
    'F1': {'name': 'Ligue 1', 'country': 'Франция', 'url': 'https://www.football-data.co.uk/mmz4281/2324/F1.csv'},
    'SP1': {'name': 'La Liga', 'country': 'Испания', 'url': 'https://www.football-data.co.uk/mmz4281/2324/SP1.csv'},
    'I1': {'name': 'Serie A', 'country': 'Италия', 'url': 'https://www.football-data.co.uk/mmz4281/2324/I1.csv'},
    'DED': {'name': 'Eredivisie', 'country': 'Нидерланды', 'url': 'https://www.football-data.co.uk/mmz4281/2324/DED.csv'},
    'UCL': {'name': 'Premier League Ukraine', 'country': 'Украина', 'url': 'https://www.football-data.co.uk/mmz4281/2324/UCL.csv'}  # Условная ссылка
}

# === Загрузка данных из всех лиг ===
def load_data():
    all_matches = []
    for code, info in LEAGUES.items():
        url = info['url']
        try:
            response = requests.get(url, timeout=10)
            df = pd.read_csv(StringIO(response.text))
            df['League'] = info['name']
            df['Country'] = info['country']
            df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
            all_matches.append(df)
            logger.info(f"✅ {info['country']} — {info['name']} загружена")
        except Exception as e:
            logger.error(f"❌ {info['country']}: {e}")
    return pd.concat(all_matches, ignore_index=True) if all_matches else pd.DataFrame()

# === Таблица лиги ===
def get_league_table(df, league_name):
    league_df = df[df['League'] == league_name]
    if league_df.empty:
        return pd.DataFrame()

    table = {}
    for _, row in league_df.iterrows():
        h, a = row['HomeTeam'], row['AwayTeam']
        for team, is_home in [(h, True), (a, False)]:
            if team not in table:
                table[team] = {'И': 0, 'В': 0, 'Н': 0, 'П': 0, 'РГ': 0, 'О': 0}
            table[team]['И'] += 1
            if is_home:
                if row['FTR'] == 'H': table[team]['В'] += 1; table[team]['О'] += 3
                elif row['FTR'] == 'D': table[team]['Н'] += 1; table[team]['О'] += 1
                else: table[team]['П'] += 1
                table[team]['РГ'] += row['FTHG'] - row['FTAG']
            else:
                if row['FTR'] == 'A': table[team]['В'] += 1; table[team]['О'] += 3
                elif row['FTR'] == 'D': table[team]['Н'] += 1; table[team]['О'] += 1
                else: table[team]['П'] += 1
                table[team]['РГ'] += row['FTAG'] - row['FTHAG']
    return pd.DataFrame([
        {'Команда': t, **v} for t, v in sorted(table.items(), key=lambda x: -x[1]['О'])
    ]).head(10)

# === Календарь матчей ===
def get_upcoming_matches(df, days=7):
    now = datetime.now()
    future = df[df['Date'] >= now].copy()
    future = future[future['Date'] <= now + timedelta(days=days)]
    future = future.sort_values('Date').head(20)
    future['Дата'] = future['Date'].dt.strftime('%d.%m %H:%M')
    return future[['Дата', 'HomeTeam', 'AwayTeam', 'League', 'Country']]

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

# === Основной цикл бота ===
def run_bot():
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
                        send_message(
                            chat_id,
                            "👋 Добро пожаловать в AI Football Analyst!\n\n"
                            "Команды:\n"
                            "• /start — это сообщение\n"
                            "• /leagues — список лиг\n"
                            "• /table Премьер-лига — таблица\n"
                            "• /calendar — предстоящие матчи"
                        )

                    elif text == "/leagues":
                        leagues_list = "\n".join([
                            f"• {info['name']} — {info['country']}" for info in LEAGUES.values()
                        ])
                        send_message(chat_id, f"🌍 *Доступные лиги:*\n\n{leagues_list}", parse_mode='Markdown')

                    elif text.startswith("/table"):
                        args = text.split()[1:]
                        if not args:
                            send_message(chat_id, "❌ Укажи лигу: /table Бундеслига")
                            continue

                        league_input = " ".join(args).lower()
                        league_map = {
                            "премьер-лига": "Premier League",
                            "бундеслига": "Bundesliga",
                            "лига 1": "Ligue 1",
                            "ла лига": "La Liga",
                            "серия a": "Serie A",
                            "эредивизи": "Eredivisie",
                            "украина": "Premier League Ukraine"
                        }
                        league = league_map.get(league_input, None)

                        if not league:
                            send_message(chat_id, "❌ Нет такой лиги. Используй /leagues")
                        elif df.empty:
                            send_message(chat_id, "❌ Нет данных")
                        else:
                            table_df = get_league_table(df, league)
                            if table_df.empty:
                                send_message(chat_id, f"❌ Нет данных по {league}")
                            else:
                                table_str = "\n".join([
                                    f"{i+1}. {row['Команда']} — {row['О']} очков"
                                    for i, row in table_df.iterrows()
                                ])
                                send_message(chat_id, f"🏆 Таблица: {league}\n\n{table_str}")

                    elif text == "/calendar":
                        if df.empty:
                            send_message(chat_id, "❌ Нет данных")
                        else:
                            matches = get_upcoming_matches(df)
                            if matches.empty:
                                send_message(chat_id, "📅 Нет предстоящих матчей")
                            else:
                                cal_str = "\n".join([
                                    f"{row['Дата']} — {row['HomeTeam']} vs {row['AwayTeam']} ({row['Country']})"
                                    for _, row in matches.iterrows()
                                ])
                                send_message(chat_id, f"📅 Предстоящие матчи:\n\n{cal_str}")

            time.sleep(1)

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
        self.wfile.write("<h1>AI Football Analyst — Все лиги загружены</h1>".encode("utf-8"))

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
