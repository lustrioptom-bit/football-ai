# web/app.py
import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from io import StringIO
from datetime import datetime, timedelta

# Настройка страницы
st.set_page_config(
    page_title="⚽ AI Football Analyst Pro",
    page_icon="⚽",
    layout="wide"
)

# Стиль
st.markdown("""
<style>
    .big-font {
        font-size:20px !important;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

st.title("🎯 AI Football Analyst Pro — Умный анализ футбола")

# === Загрузка данных ===
@st.cache_data
def load_data():
    url = "https://www.football-data.co.uk/mmz4281/2324/E0.csv"
    try:
        df = pd.read_csv(StringIO(requests.get(url).text))
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce', dayfirst=True)
        df['League'] = 'Premier League'
        st.success("✅ Данные АПЛ 2023/24 загружены")
        return df
    except Exception as e:
        st.error(f"❌ Не удалось загрузить данные: {e}")
        return pd.DataFrame()

# Кнопка обновления
if st.button("🔄 Обновить данные"):
    st.cache_data.clear()
    st.rerun()

df = load_data()
if df.empty:
    st.stop()

# === Вкладки ===
tab1, tab2, tab3, tab4 = st.tabs([
    "🔮 Прогноз", 
    "🏆 Таблица", 
    "📅 Календарь", 
    "📊 ROI & Сигналы"
])

# === 1. Прогноз матча ===
with tab1:
    st.header("Сделай прогноз")

    col1, col2 = st.columns(2)
    with col1:
        team1 = st.selectbox("Домашняя команда", df['HomeTeam'].unique(), key="home")
    with col2:
        team2 = st.selectbox("Гостевая команда", df['AwayTeam'].unique(), key="away")

    if st.button("📊 Прогнозировать"):
        # Простая модель xG
        home_stats = df[df['HomeTeam'] == team1]
        away_stats = df[df['AwayTeam'] == team2]

        xG1 = round(home_stats['FTHG'].mean() if len(home_stats) > 0 else 1.5, 2)
        xG2 = round(away_stats['FTAG'].mean() if len(away_stats) > 0 else 1.2, 2)

        if xG1 > xG2 + 0.3:
            result = f"Победа {team1}"
            color = "green"
        elif xG2 > xG1 + 0.3:
            result = f"Победа {team2}"
            color = "green"
        else:
            result = "Ничья"
            color = "orange"

        # Отображение
        st.markdown(f"<p class='big-font' style='color:{color}'>Прогноз: {result}</p>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Ожидаемые голы (xG)", f"{xG1} : {xG2}")
        with col2:
            st.metric("Счёт", f"{round(xG1)} : {round(xG2)}")

        # График
        xg_data = pd.DataFrame({
            'Команда': [team1, team2],
            'xG': [xG1, xG2]
        })
        fig = px.bar(xg_data, x='Команда', y='xG', title="Сравнение xG", color='Команда')
        st.plotly_chart(fig, use_container_width=True)

# === 2. Таблица лиги ===
with tab2:
    st.header("🏆 Таблица АПЛ")

    def get_table(df):
        table = {}
        for _, row in df.iterrows():
            h, a = row['HomeTeam'], row['AwayTeam']
            for team, is_home in [(h, True), (a, False)]:
                if team not in table:
                    table[team] = {'И': 0, 'В': 0, 'Н': 0, 'П': 0, 'РГ': 0, 'О': 0}
                table[team]['И'] += 1
                if is_home:
                    if row['FTR'] == 'H':
                        table[team]['В'] += 1
                        table[team]['О'] += 3
                    elif row['FTR'] == 'D':
                        table[team]['Н'] += 1
                        table[team]['О'] += 1
                    else:
                        table[team]['П'] += 1
                    table[team]['РГ'] += row['FTHG'] - row['FTAG']
                else:
                    if row['FTR'] == 'A':
                        table[team]['В'] += 1
                        table[team]['О'] += 3
                    elif row['FTR'] == 'D':
                        table[team]['Н'] += 1
                        table[team]['О'] += 1
                    else:
                        table[team]['П'] += 1
                    table[team]['РГ'] += row['FTAG'] - row['FTHG']
        return pd.DataFrame([
            {'Команда': t, **v} for t, v in sorted(table.items(), key=lambda x: -x[1]['О'])
        ])

    league_table = get_table(df)
    st.dataframe(league_table, use_container_width=True)

# === 3. Календарь матчей ===
with tab3:
    st.header("📅 Предстоящие матчи")

    if 'Date' in df.columns:
        now = pd.Timestamp.now()
        future = df[df['Date'] >= now].copy()
        future = future[['Date', 'HomeTeam', 'AwayTeam', 'League']].head(15)
        future['Date'] = future['Date'].dt.strftime('%d.%m %H:%M')
        future = future.rename(columns={
            'Date': 'Дата',
            'HomeTeam': 'Дома',
            'AwayTeam': 'В гостях',
            'League': 'Лига'
        })
        st.dataframe(future, use_container_width=True)
    else:
        st.warning("Нет данных о датах")

# === 4. ROI и сигналы ===
with tab4:
    st.header("📊 Виртуальные ставки и сигналы")

    # Симуляция ROI
    total_bets = 8
    wins = 5
    profit = 22.4
    accuracy = wins / total_bets
    roi = (profit / (total_bets * 10)) * 100

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Ставок", total_bets)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Точность", f"{accuracy:.1%}")
        st.markdown('</div>', unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Прибыль", f"{profit} у.е.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("ROI", f"{roi:.1f}%")
        st.markdown('</div>', unsafe_allow_html=True)

    # Сигналы
    st.subheader("🎯 Последние сигналы")
    signals = pd.DataFrame([
        {"Матч": "Arsenal vs Man City", "Сигнал": "Победа Arsenal", "Edge": "+12%", "Дата": "10.08"},
        {"Матч": "Liverpool vs Chelsea", "Сигнал": "Ничья", "Edge": "+15%", "Дата": "11.08"},
    ])
    st.dataframe(signals, use_container_width=True)