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
            response = requests.get(url, timeout=10)
            df = pd.read_csv(StringIO(response.text))
            df['League'] = name
            df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
            all_matches.append(df)
            logger.info(f"✅ {name} загружена")
        except Exception as e:
            logger.error(f"❌ {name}: {e}")
    
    return pd.concat(all_matches, ignore_index=True) if all_matches else pd.DataFrame()

# === Таблица лиги ===
def get_league_table(df, league_name):
    league_df = df[df['League'] == league_name]
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
    future = future.sort_values('Date').head(15)
    future['Дата'] = future['Date'].dt.strftime('%d.%m %H:%M')
    return future[['Дата', 'HomeTeam', 'AwayTeam', 'League']]

# === Прогноз матча ===
def predict_match(team1, team2, df):
    home_games = df[df['HomeTeam'] == team1]
    away_games = df[df['AwayTeam'] == team2]
    xG1 = home_games['FTHG'].mean() if len(home_games) > 0 else 1.5
    xG2 = away_games['FTAG'].mean() if len(away_games) > 0 else 1.2
    result = "HomeAs Winner" if xG1 > xG2 + 0.3 else "AwayAs Winner" if xG2 > xG1 + 0.3 else "Draw"
    return f"🔮 {result}\nxG: {xG1:.2f} — {xG2:.2f}"

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

# === Основной цикл ===
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
                        send_message(
                            chat_id,
                            "👋 Добро пожаловать в AI Football Analyst!\n\n"
                            "Команды:\n"
                            "• /start — это сообщение\n"
                            "• /predict Команда1 Команда2 — прогноз\n"
                            "• /table Премьер-лига — таблица\n"
                            "• /calendar — предстоящие матчи"
                        )

                    elif text.startswith("/predict"):
                        args = text.split()[1:]
                        if len(args) < 2:
                            send_message(chat_id, "❌ /predict Arsenal Man City")
                        else:
                            team1 = args[0]
                            team2 = " ".join(args[1:])
                            if df.empty:
                                send_message(chat_id, "❌ Нет данных")
                            else:
                                pred = predict_match(team1, team2, df)
                                send_message(chat_id, pred)

                    elif text.startswith("/table"):
                        args = text.split()[1:]
                        if not args:
                            league = "Premier League"
                        else:
                            league_input = " ".join(args).lower()
                            league_map = {
                                "премьер-лига": "Premier League",
                                "бундеслига": "Bundesliga",
                                "серия": "Serie A",
                                "лига": "Ligue 1",
                                "ла лига": "La Liga"
                            }
                            league = league_map.get(league_input, "Premier League")

                        if df.empty:
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
                                    f"{row['Дата']} — {row['HomeTeam']} vs {row['AwayTeam']} ({row['League']})"
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

if __name__ == "__main__":
    main()
EOFcat > /workspaces/football-ai/bot.py << 'EOF'
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
            response = requests.get(url, timeout=10)
            df = pd.read_csv(StringIO(response.text))
            df['League'] = name
            df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
            all_matches.append(df)
            logger.info(f"✅ {name} загружена")
        except Exception as e:
            logger.error(f"❌ {name}: {e}")
    
    return pd.concat(all_matches, ignore_index=True) if all_matches else pd.DataFrame()

# === Таблица лиги ===
def get_league_table(df, league_name):
    league_df = df[df['League'] == league_name]
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
    future = future.sort_values('Date').head(15)
    future['Дата'] = future['Date'].dt.strftime('%d.%m %H:%M')
    return future[['Дата', 'HomeTeam', 'AwayTeam', 'League']]

# === Прогноз матча ===
def predict_match(team1, team2, df):
    home_games = df[df['HomeTeam'] == team1]
    away_games = df[df['AwayTeam'] == team2]
    xG1 = home_games['FTHG'].mean() if len(home_games) > 0 else 1.5
    xG2 = away_games['FTAG'].mean() if len(away_games) > 0 else 1.2
    result = "HomeAs Winner" if xG1 > xG2 + 0.3 else "AwayAs Winner" if xG2 > xG1 + 0.3 else "Draw"
    return f"🔮 {result}\nxG: {xG1:.2f} — {xG2:.2f}"

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

# === Основной цикл ===
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
                        send_message(
                            chat_id,
                            "👋 Добро пожаловать в AI Football Analyst!\n\n"
                            "Команды:\n"
                            "• /start — это сообщение\n"
                            "• /predict Команда1 Команда2 — прогноз\n"
                            "• /table Премьер-лига — таблица\n"
                            "• /calendar — предстоящие матчи"
                        )

                    elif text.startswith("/predict"):
                        args = text.split()[1:]
                        if len(args) < 2:
                            send_message(chat_id, "❌ /predict Arsenal Man City")
                        else:
                            team1 = args[0]
                            team2 = " ".join(args[1:])
                            if df.empty:
                                send_message(chat_id, "❌ Нет данных")
                            else:
                                pred = predict_match(team1, team2, df)
                                send_message(chat_id, pred)

                    elif text.startswith("/table"):
                        args = text.split()[1:]
                        if not args:
                            league = "Premier League"
                        else:
                            league_input = " ".join(args).lower()
                            league_map = {
                                "премьер-лига": "Premier League",
                                "бундеслига": "Bundesliga",
                                "серия": "Serie A",
                                "лига": "Ligue 1",
                                "ла лига": "La Liga"
                            }
                            league = league_map.get(league_input, "Premier League")

                        if df.empty:
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
                                    f"{row['Дата']} — {row['HomeTeam']} vs {row['AwayTeam']} ({row['League']})"
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

if __name__ == "__main__":
    main()
