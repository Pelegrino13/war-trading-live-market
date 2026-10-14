
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="WAR TRADING LIVE MARKET",
    page_icon="⚔️",
    layout="wide"
)

st.markdown("""
<style>
.stApp {
    background: #071321;
    color: white;
}
h1, h2, h3 {
    color: #45baff !important;
}
[data-testid="stMetric"] {
    background: #112438;
    border: 1px solid #244760;
    padding: 15px;
    border-radius: 12px;
}
</style>
""", unsafe_allow_html=True)

st.title("⚔️ WAR TRADING")
st.subheader("LIVE MARKET")

agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
st.caption(
    "Horário de Brasília: "
    + agora.strftime("%d/%m/%Y %H:%M:%S")
)

ativos = {
    "NQ": "Nasdaq 100",
    "ES": "S&P 500",
    "DXY": "Índice do Dólar",
    "VIX": "Volatilidade",
    "US10Y": "Treasury 10 anos",
    "CL": "Petróleo WTI",
    "GC": "Ouro",
    "FEF2!": "Minério de Ferro"
}

st.info("Painel inicial — aguardando conexão de dados.")

for codigo, nome in ativos.items():
    with st.container(border=True):
        st.markdown(f"### {codigo}")
        st.write(nome)
        st.metric("Variação", "Aguardando dados")

st.divider()
st.caption("WAR TRADING | LIVE MARKET")
