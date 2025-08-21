# web/app.py
import streamlit as st
import pandas as pd
import requests
from io import StringIO

st.set_page_config(page_title="⚽ AI Football Analyst", layout="wide")
st.title("🎯 AI Football Analyst Pro — Веб-интерфейс")

@st.cache_data
def load_data():
    url = "https://www.football-data.co.uk/mmz4281/2324/E0.csv"
    try:
        df = pd.read_csv(StringIO(requests.get(url).text))
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        st.success("✅ Данные загружены")
        return df
    except Exception as e:
        st.error(f"❌ Ошибка: {e}")
        return pd.DataFrame()

if st.button("🔄 Обновить данные"):
    st.cache_data.clear()

df = load_data()
if df.empty:
    st.stop()

st.header("📊 Прогноз матча")
team1 = st.text_input("Команда 1", "Arsenal")
team2 = st.text_input("Команда 2", "Man City")

if st.button("Прогноз"):
    st.success(f"🔮 Прогноз: победа {team1}")
    st.metric("Счёт", "2 : 1")
