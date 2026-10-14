import streamlit as st
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(page_title="WAR TRADING — LIVE MARKET", page_icon="⚔️", layout="wide")

st.markdown("""
<style>
.stApp { background: #071321; color: #f2f7ff; }
h1, h2, h3 { color: #45baff !important; }
[data-testid="stMetric"] { background: #112438; border: 1px solid #244760; padding: 15px; border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

st.title("⚔️ WAR TRADING")
st.subheader("LIVE MARKET")
st.caption("Horário de Brasília: " + datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S"))
st.caption("Primeiro teste: cotação do Nasdaq Futuro (NQ) via Yahoo Finance. Dados podem ter atraso.")

@st.cache_data(ttl=60, show_spinner=False)
def consultar_nq():
    dados = yf.Ticker("NQ=F").history(period="5d", interval="1m", auto_adjust=False)
    if dados.empty:
        return None, "A fonte não retornou cotações."
    dados = dados.dropna(subset=["Close"])
    if dados.empty:
        return None, "A fonte não retornou preços válidos."
    ultima_linha = dados.iloc[-1]
    ultimo = float(ultima_linha["Close"])
    data_ultima = dados.index[-1]
    data_local = data_ultima.tz_convert("America/Sao_Paulo") if data_ultima.tzinfo else data_ultima
    # Comparar com o fechamento do pregão anterior, se fornecido pelo Yahoo.
    info = yf.Ticker("NQ=F").fast_info
    anterior = info.get("previous_close")
    if not anterior or anterior <= 0:
        return {"preco": ultimo, "variacao": None, "hora": data_local.strftime("%d/%m/%Y %H:%M")}, None
    variacao = (ultimo / float(anterior) - 1) * 100
    return {"preco": ultimo, "variacao": variacao, "hora": data_local.strftime("%d/%m/%Y %H:%M")}, None

ativos = [
    ("NQ", "Nasdaq Futuro"),
    ("ES", "S&P 500 Futuro"),
    ("DXY", "Índice do Dólar"),
    ("VIX", "Volatilidade"),
    ("US10Y", "Treasury 10 anos"),
    ("CL", "Petróleo WTI"),
    ("GC", "Ouro"),
    ("FERRO", "Minério de Ferro DLN (referência Moscca)"),
]

if st.button("🔄 Consultar NQ agora"):
    consultar_nq.clear()

for codigo, nome in ativos:
    with st.container(border=True):
        st.markdown(f"### {codigo}")
        st.write(nome)
        if codigo == "NQ":
            try:
                resultado, erro = consultar_nq()
                if erro:
                    st.warning(erro)
                elif resultado:
                    st.metric("Último preço", f"{resultado['preco']:,.2f}")
                    if resultado["variacao"] is None:
                        st.info("Variação indisponível: fechamento anterior não informado pela fonte.")
                    else:
                        st.metric("Variação versus fechamento anterior", f"{resultado['variacao']:+.2f}%")
                    st.caption("Horário da cotação (Brasília): " + resultado["hora"])
            except Exception as exc:
                st.warning("Não foi possível consultar o NQ agora. A fonte pode estar indisponível ou limitar consultas.")
                st.caption(f"Detalhe técnico: {type(exc).__name__}")
        else:
            st.metric("Variação", "Aguardando integração")

st.divider()
st.caption("WAR TRADING | LIVE MARKET — Dados informativos, sujeitos a atrasos e indisponibilidade.")
