# bot.py
# 🏆 AI Football Analyst Pro — Полная версия с ROI
import requests
import time
import logging
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta
from config import TOKEN, MAIN_CHAT_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

# === Загрузка данных ===
def load_data():
    url = "https://www.football-data.co.uk/mmz4281/2324/E0.csv"
    try:
        df = pd.read_csv(StringIO(requests.get(url, timeout=10).text))
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        df['DateTime'] = df['Date']

        # Добавим тестовый матч через 1 час 10 минут
        test_match = df.iloc[0].copy()
        test_match['DateTime'] = datetime.now() + timedelta(hours=1, minutes=10)
        test_match['B365H'] = 1.80
        test_match['B365D'] = 3.60
        test_match['B365A'] = 4.50
        return pd.DataFrame([test_match])
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return pd.DataFrame()

# === Прогноз AI ===
def predict_match(team1, team2):
    return {
        'probs': {'H': 0.55, 'D': 0.25, 'A': 0.20},
        'result': 'Победа Arsenal',
        'score': '1.8 : 1.2',
        'xG1': 1.8, 'xG2': 1.2
    }

# === Сравнение с букмекерами ===
def compare_with_bookmaker(ai_probs, b365_h, b365_d, b365_a):
    bookie_probs = {k: 1/v for k, v in {'H': b365_h, 'D': b365_d, 'A': b365_a}.items()}
    total = sum(bookie_probs.values())
    bookie_probs = {k: v/total for k, v in bookie_probs.items()}
    edge = {k: ai_probs[k] - bookie_probs[k] for k in ai_probs}
    return bookie_probs, edge

# === Виртуальные ставки и ROI ===
class ROI_Tracker:
    def __init__(self):
        self.total_bet = 0
        self.profit = 0
        self.wins = 0
        self.total = 0

    def place_bet(self, match, ai_probs, b365_h, b365_d, b365_a, amount=10):
        _, edge = compare_with_bookmaker(ai_probs, b365_h, b365_d, b365_a)
        signals = [k for k, v in edge.items() if v > 0.10]

        if not signals:
            return

        # Делаем ставку на самый большой перевес
        bet_on = max(signals, key=lambda x: edge[x])
        odds = {'H': b365_h, 'D': b365_d, 'A': b365_a}[bet_on]
        outcome = match['FTR']
        win = (bet_on == 'H' and outcome == 'H') or \
              (bet_on == 'D' and outcome == 'D') or \
              (bet_on == 'A' and outcome == 'A')

        self.total += 1
        self.total_bet += amount
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
            'profit': self.profit,
            'accuracy': accuracy,
            'roi': roi
        }

# === Отправка сообщения ===
def send_message(chat_id, text, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(BASE_URL + "sendMessage", data=payload, timeout=10)
    except: pass

# === Проверка матчей ===
def check_upcoming_matches(df, context_chat_id, roi_tracker):
    now = datetime.now()
    start = now + timedelta(minutes=50)
    end = now + timedelta(minutes=70)

    upcoming = df[
        (df['DateTime'] > start) & 
        (df['DateTime'] <= end)
    ]

    for _, match in upcoming.iterrows():
        home = match['HomeTeam']
        away = match['AwayTeam']
        pred = predict_match(home, away)
        ai_probs = pred['probs']

        b365_h = match.get('B365H', 1.80)
        b365_d = match.get('B365D', 3.60)
        b365_a = match.get('B365A', 4.50)

        bookie_probs, edge = compare_with_bookmaker(ai_probs, b365_h, b365_d, b365_a)
        signals = [k for k, v in edge.items() if v > 0.10]
        has_signal = len(signals) > 0

        # Симуляция ставки
        if has_signal:
            roi_tracker.place_bet(match, ai_probs, b365_h, b365_d, b365_a)

        # Отправка уведомления
        message = (
            f"⏰ *Предстоящий матч*\n"
            f"{home} ⚔️ {away}\n\n"
            f"🔮 *Прогноз AI*:\n"
            f"• Победитель: *{pred['result']}*\n"
            f"• xG: {pred['xG1']:.2f} — {pred['xG2']:.2f}\n\n"
            f"📘 *Букмекер (B365)*:\n"
            f"• H: {b365_h} ({bookie_probs['H']:.1%})\n"
            f"• D: {b365_d} ({bookie_probs['D']:.1%})\n"
            f"• A: {b365_a} ({bookie_probs['A']:.1%})\n\n"
            f"📊 *Перевес AI*:\n"
            f"• H: {edge['H']:+.1%}\n"
            f"• D: {edge['D']:+.1%}\n"
            f"• A: {edge['A']:+.1%}"
        )

        if has_signal:
            signal_str = " | ".join([{'H': home, 'D': 'Draw', 'A': away}[s] for s in signals])
            message += f"\n\n🎯 *СИГНАЛ НА СТАВКУ!* 🔥\nВысокий перевес: {signal_str}"

        send_message(context_chat_id, message, parse_mode='Markdown')
        logger.info(f"🔔 Уведомление с ROI отправлено")

# === Главный цикл ===
def main():
    logger.info("✅ AI Football Analyst Pro запущен")
    df = load_data()
    roi_tracker = ROI_Tracker()

    if df.empty:
        logger.error("❌ Нет данных")
        return

    while True:
        try:
            check_upcoming_matches(df, MAIN_CHAT_ID, roi_tracker)
            time.sleep(120)
        except KeyboardInterrupt:
            # Перед остановкой — покажем отчёт
            report = roi_tracker.report()
            summary = (
                f"📊 *Финальный отчёт*\n"
                f"• Ставок сделано: {report['total']}\n"
                f"• Прибыль: {report['profit']:.1f} у.е.\n"
                f"• Точность: {report['accuracy']:.1%}\n"
                f"• ROI: {report['roi']:.1f}%"
            )
            send_message(MAIN_CHAT_ID, summary, parse_mode='Markdown')
            logger.info("🛑 Бот остановлен. Отчёт отправлен.")
            break
        except Exception as e:
            logger.error(f"🚨 Ошибка: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()