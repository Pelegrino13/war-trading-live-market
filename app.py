import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
from email.utils import parsedate_to_datetime
import html
import re

st.set_page_config(page_title='WAR TRADING — LIVE MARKET 2.4', page_icon='📈', layout='wide', initial_sidebar_state='collapsed')
BRT = ZoneInfo('America/Sao_Paulo')
NOW = datetime.now(BRT)

# Para instrumentos que fecharam recentemente, aceitamos até 3h de atraso.
# Para instrumentos negociados continuamente, exigimos cotação mais recente.
CONTINUOUS = {'NQ=F', 'ES=F', 'DX-Y.NYB'}

# Os quatro componentes abaixo são referências configuráveis, não seleção automática.
# Atualize periodicamente de acordo com os pesos oficiais do Nasdaq-100.
STOCKS = [
    ('NVDA', 'Nvidia', 8.31), ('AAPL', 'Apple', 7.51),
    ('MSFT', 'Microsoft', 6.09), ('MU', 'Micron', 4.48),
]
ASSETS = [
    ('NQ', 'Nasdaq Futuro', 'NQ=F'), ('ES', 'S&P 500 Futuro', 'ES=F'),
    ('SOX', 'Semicondutores', '^SOX'), ('US10Y', 'Treasury 10 anos', '^TNX'),
    ('DXY', 'Índice do Dólar', 'DX-Y.NYB'), ('VIX', 'Volatilidade S&P 500', '^VIX'),
    ('VXN', 'Volatilidade Nasdaq', '^VXN'), ('XLK', 'ETF Tecnologia', 'XLK'),
]
# Cada grupo de risco tem peso próprio; os sinais correlacionados dentro dele são
# combinados ANTES de somar. Não somamos o score das ações ao do setor de tecnologia.
GROUP_WEIGHTS = {'mercado': 0.30, 'tecnologia': 0.25, 'juros_dolar': 0.25, 'volatilidade': 0.20}

st.markdown('''<style>
#MainMenu, footer {visibility:hidden}
header[data-testid="stHeader"] {background:transparent}
.stApp {background:#030d19;color:#edf6ff}
.block-container {padding:.65rem .65rem 1.5rem;max-width:1150px}
.war-panel {background:linear-gradient(135deg,#071a2d,#061423);border:1px solid #0876b3;border-radius:12px;padding:12px;margin-bottom:9px;box-shadow:inset 0 0 15px #0079bf13}
.brand {font-weight:900;font-size:clamp(26px,5vw,45px);letter-spacing:2px;color:#48bcff;line-height:1.1}
.subbrand {color:#8bd7ff;letter-spacing:3px;font-size:11px}
.section {font-size:clamp(15px,2.5vw,22px);font-weight:900;color:#37baff;margin:4px 0 8px}
.status {font-size:clamp(20px,3.4vw,29px);font-weight:900;color:#18db9e}
.muted {color:#a3bed0;font-size:12px}.tiny {color:#87a9bd;font-size:11px}
.asset-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:10px}
.asset {min-width:0;background:linear-gradient(140deg,#06182b,#04111f);border:1px solid #087bb8;border-radius:11px;padding:9px;min-height:115px;overflow:hidden}
.asset.up {border-color:#087e65}.asset.down {border-color:#a6425b}.asset.stale {border-color:#617386;opacity:.85}
.asset-name {font-size:20px;font-weight:900;color:#40bbff}
.asset-price {font-size:clamp(13px,2.3vw,21px);font-weight:800;color:#f2f8ff;white-space:nowrap}
.positive {color:#14dc99;font-weight:800}.negative {color:#ff4d72;font-weight:800}
.asset-bottom {display:flex;justify-content:space-between;align-items:baseline;gap:4px;flex-wrap:wrap}
.asset-bottom span {font-size:clamp(12px,2vw,19px)}
.gauge {height:13px;border-radius:12px;background:linear-gradient(90deg,#ef4264,#f6ce41,#18d79b);position:relative;margin:12px 0}
.gauge-pin {position:absolute;top:-7px;width:4px;height:27px;background:white;box-shadow:0 0 6px white}
.summary-grid {display:grid;grid-template-columns:1.4fr 1fr;gap:8px}
.impact {border-bottom:1px solid #153e57;padding:8px 2px;font-size:13px}
.news {padding:9px 0;border-bottom:1px solid #153e57;font-size:13px}
.news-num {display:inline-block;background:#1599db;border-radius:50%;color:#001323;padding:2px 7px;font-weight:900}
a {color:#68caff!important}
@media(max-width:600px){
.block-container {padding:.5rem .4rem 1.5rem}
.war-panel {padding:9px}.asset-grid{gap:6px}.asset{padding:7px;min-height:112px}
.asset-name{font-size:17px}.asset-bottom span{font-size:13px}
.subbrand{letter-spacing:2px}.muted{font-size:11px}.tiny{font-size:10px}
.summary-grid{grid-template-columns:1fr 1fr;gap:6px}
.section{font-size:15px}
}
</style>''', unsafe_allow_html=True)

@st.cache_data(ttl=55, show_spinner=False)
def load_quotes():
    symbols = list(dict.fromkeys([a[2] for a in ASSETS] + [s[0] for s in STOCKS]))
    out = {}
    try:
        frame = yf.download(symbols, period='5d', interval='5m', group_by='ticker', auto_adjust=False, progress=False, threads=True, timeout=15)
    except Exception:
        frame = pd.DataFrame()
    for sym in symbols:
        try:
            if frame.empty:
                continue
            part = frame[sym] if isinstance(frame.columns, pd.MultiIndex) else frame
            close = pd.to_numeric(part['Close'], errors='coerce').dropna()
            if close.empty:
                continue
            last_time = close.index[-1]
            if last_time.tzinfo is None:
                # yfinance normally returns tz-aware intraday indexes. If not,
                # do not claim a reliable source timestamp.
                timestamp = None
            else:
                timestamp = last_time.tz_convert(BRT).to_pydatetime()
            # Intraday series is used for sparkline, not the daily percentage baseline.
            out[sym] = {'price': float(close.iloc[-1]), 'time': timestamp,
                        'series': close.tail(32).tolist(), 'pct': None}
        except Exception:
            continue
    # Daily closes: previous completed daily bar is a more consistent reference
    # than comparing the first and last 5-minute candles.
    try:
        daily = yf.download(symbols, period='7d', interval='1d', group_by='ticker', auto_adjust=False, progress=False, threads=True, timeout=15)
        for sym in symbols:
            if sym not in out or daily.empty:
                continue
            part = daily[sym] if isinstance(daily.columns, pd.MultiIndex) else daily
            d = pd.to_numeric(part['Close'], errors='coerce').dropna()
            if len(d) < 2:
                continue
            # Daily current bar can be the current trading day; the previous row
            # is used as reference when date matches the intraday quote's date.
            intraday_dt = out[sym]['time']
            if intraday_dt is None:
                continue
            last_daily_date = pd.Timestamp(d.index[-1]).date()
            reference = float(d.iloc[-2]) if last_daily_date == intraday_dt.date() else float(d.iloc[-1])
            if reference > 0:
                out[sym]['pct'] = (out[sym]['price'] / reference - 1) * 100
    except Exception:
        pass
    return out

@st.cache_data(ttl=300, show_spinner=False)
def load_news():
    # Pesquisa orientada a mercado, não notícias genéricas com uma palavra-chave.
    queries = [
        '(Nasdaq OR "Nasdaq 100" OR "US stocks" OR "S&P 500") (stocks OR market OR earnings) when:1d',
        '(Federal Reserve OR inflation OR Treasury yields OR Nvidia OR Microsoft OR Apple OR Micron OR semiconductor) (stocks OR Nasdaq OR markets OR earnings) when:1d',
    ]
    relevant = ('nasdaq','s&p 500','wall street','stocks','stock market','federal reserve',
                'fed rate','interest rate','inflation','treasury yield','bond yield',
                'nvidia','microsoft','apple shares','micron','semiconductor','chip stocks',
                'technology shares','tech stocks','earnings','artificial intelligence',
                'dow jones','us futures','u.s. futures')
    excluded = ('ballroom','donor','wedding','celebrity','sports','football','soccer',
                'royal family','movie review','horoscope','lottery')
    found = {}
    for query in queries:
        url = f'https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en'
        try:
            r = requests.get(url, timeout=9, headers={'User-Agent':'Mozilla/5.0'})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall('.//item'):
                title = html.unescape(item.findtext('title') or '').strip()
                link = (item.findtext('link') or '').strip()
                source = (item.findtext('source') or 'Google News').strip()
                try:
                    when = parsedate_to_datetime(item.findtext('pubDate') or '').astimezone(BRT)
                except Exception:
                    continue
                t = title.casefold()
                if (not title or not link.startswith('https://') or
                    not any(k in t for k in relevant) or any(k in t for k in excluded) or
                    not timedelta(minutes=-5) <= NOW-when <= timedelta(hours=24)):
                    continue
                key = re.sub(r'[^a-z0-9]+','',t)[:110]
                if key not in found or when > found[key]['when']:
                    found[key] = {'title':title,'url':link,'source':source,'when':when}
        except Exception:
            continue
    return sorted(found.values(), key=lambda n:n['when'], reverse=True)[:3]

def fresh(quote_data, symbol=None):
    if not quote_data or quote_data.get('pct') is None or not quote_data.get('time'):
        return False
    age = NOW - quote_data['time']
    # Futuros/dólar exigem no máximo 45 minutos de defasagem. Ações e índices
    # à vista podem ter fechado: janela de até 3 horas para leitura pós-fechamento.
    limit = timedelta(minutes=45) if symbol in CONTINUOUS else timedelta(hours=3)
    return timedelta(minutes=-5) <= age <= limit

def avg_signals(values):
    return float(np.mean(values)) if values else None

def calc_score(quotes):
    by_name = {name: quotes.get(symbol) for name, _, symbol in ASSETS}
    def s(name, inverse=False):
        q = by_name.get(name)
        if not fresh(q, next((symbol for name_,_,symbol in ASSETS if name_==name), None)):
            return None
        v = float(np.clip(q['pct'] / 2.0, -1, 1))
        return -v if inverse else v
    # Market beta, tech sector and mega-cap stocks overlap: group tech as
    # ONE signal (50% SOX, 25% XLK, 25% weighted top-4 stocks).
    stock_signals = []
    stock_total = 0.0
    for symbol, _, weight in STOCKS:
        q = quotes.get(symbol)
        if fresh(q, symbol):
            stock_signals.append((float(np.clip(q['pct']/2.0,-1,1)), weight))
            stock_total += weight
    stocks_signal = sum(v*w for v,w in stock_signals)/stock_total if stock_total else None
    tech_parts = [(s('SOX'),.50),(s('XLK'),.25),(stocks_signal,.25)]
    tech = sum(v*w for v,w in tech_parts if v is not None)/sum(w for v,w in tech_parts if v is not None) if any(v is not None for v,w in tech_parts) else None
    groups = {
        'mercado': s('ES'),
        'tecnologia': tech,
        'juros_dolar': avg_signals([v for v in (s('US10Y',True),s('DXY',True)) if v is not None]),
        'volatilidade': avg_signals([v for v in (s('VIX',True),s('VXN',True)) if v is not None]),
    }
    active = {k:v for k,v in groups.items() if v is not None}
    # Missing groups are not silently normalized to 100%: report insufficient coverage.
    coverage = sum(GROUP_WEIGHTS[k] for k in active)
    score = round(100 * sum(GROUP_WEIGHTS[k]*v for k,v in active.items()) / coverage) if coverage >= .75 else None
    return score, coverage, groups

def classify(score):
    if score is None: return ('DADOS INSUFICIENTES','#a4b6c8')
    if score <= -60: return ('BAIXA FORTE','#ff4265')
    if score <= -20: return ('BAIXA MODERADA','#ff8761')
    if score < 20: return ('LATERALIZAÇÃO','#ffd25b')
    if score < 60: return ('ALTA MODERADA','#15d99b')
    return ('ALTA FORTE','#15d99b')

def fmt_price(p):
    return f'{p:,.2f}' if p is not None else '—'

def sparkline(values, color):
    if len(values)<2: return ''
    arr=np.array(values, dtype=float)
    lo,hi=float(np.min(arr)),float(np.max(arr))
    y=16-(arr-lo)/(hi-lo if hi!=lo else 1)*13
    x=np.linspace(1,94,len(arr))
    pts=' '.join(f'{xx:.1f},{yy:.1f}' for xx,yy in zip(x,y))
    return f'<svg viewBox="0 0 96 20" width="100%" height="25" aria-hidden="true"><polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/></svg>'

def asset_card(name, subtitle, q, extra=''):
    if not q:
        return f'<div class="asset stale"><div class="asset-name">{name}</div><div class="muted">{subtitle}</div><div class="asset-price">Indisponível</div><div class="tiny">Fonte sem dados</div></div>'
    pct=q.get('pct')
    up=pct is not None and pct>=0
    cls='stale' if not fresh(q, next((sym for n,_,sym in ASSETS if n==name), name)) else 'up' if up else 'down' if pct is not None else ''
    color='#14dc99' if up else '#ff4d72'
    delta=f'{"▲" if up else "▼"} {pct:+.2f}%' if pct is not None else 'Variação indisponível'
    when=q['time'].strftime('%d/%m %H:%M') if q.get('time') else 'Horário indisponível'
    stale=' · ATRASADA' if not fresh(q, next((sym for n,_,sym in ASSETS if n==name), name)) else ''
    return (f'<div class="asset {cls}"><div class="asset-name">{name}</div><div class="muted">{subtitle}{extra}</div>'
            f'<div class="asset-bottom"><span class="asset-price">{fmt_price(q["price"])}</span>'
            f'<span class="{"positive" if up else "negative" if pct is not None else "muted"}">{delta}</span></div>'
            f'{sparkline(q.get("series",[]),color)}<div class="tiny">Cotação: {when} BRT{stale}</div></div>')

# Automatic refresh without requiring extra dependencies.
st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
with st.spinner('Consultando mercado...'):
    quotes = load_quotes()
score, coverage, groups = calc_score(quotes)
classification, status_color = classify(score)
score_str = f'{score:+d}' if score is not None else '—'

st.markdown(f'''<div class="war-panel"><div class="brand">WAR TRADING</div><div class="subbrand">LIVE MARKET 2.4</div>
<div class="muted">BRASÍLIA · {NOW.strftime('%d/%m/%Y %H:%M:%S')} · ↻ 60 SEG</div></div>''', unsafe_allow_html=True)
position = 50 if score is None else (score+100)/2
st.markdown(f'''<div class="summary-grid">
<div class="war-panel"><div class="section">CONCLUSÃO PARA O MNQ</div>
<div class="status" style="color:{status_color}">{classification}</div>
<div class="muted">Leitura intermarket: {score_str}. Cobertura de grupos: {coverage:.0%}.
NQ é referência, não soma. Indicador exploratório, não é sinal de entrada.</div></div>
<div class="war-panel"><div class="section">WAR SCORE MNQ</div>
<div class="status" style="text-align:center">{score_str}</div>
<div class="gauge"><div class="gauge-pin" style="left:{position}%"></div></div>
<div class="tiny">-100 BAIXA | 0 NEUTRO | +100 ALTA</div></div></div>''', unsafe_allow_html=True)

st.markdown('<div class="section">RADAR INTERMARKET · 8 ATIVOS</div>', unsafe_allow_html=True)
st.markdown('<div class="asset-grid">'+''.join(asset_card(name,desc,quotes.get(sym)) for name,desc,sym in ASSETS)+'</div>',unsafe_allow_html=True)

st.markdown('<div class="section">TOP 4 AÇÕES · PESOS DE REFERÊNCIA</div>',unsafe_allow_html=True)
st.caption('Pesos de referência do QQQ de 13/10/2026; não atualizados automaticamente. Verifique a composição antes de operar.')
st.markdown('<div class="asset-grid">'+''.join(asset_card(sym,company,quotes.get(sym),f' · peso ref. {weight:.2f}%') for sym,company,weight in STOCKS)+'</div>',unsafe_allow_html=True)

impact=[]
for label,group in [('ES','mercado'),('SOX / XLK / AÇÕES','tecnologia'),('US10Y / DXY','juros_dolar'),('VIX / VXN','volatilidade')]:
    v=groups[group]
    if v is not None:
        impact.append((abs(v*GROUP_WEIGHTS[group]),label,v,GROUP_WEIGHTS[group]))
impact_html=''
for _,label,v,w in sorted(impact,reverse=True):
    direction='FAVORÁVEL' if v>=0 else 'DESFAVORÁVEL'
    color='#14dc99' if v>=0 else '#ff4d72'
    impact_html+=f'<div class="impact"><b>{label}</b><br><span style="color:{color}">{direction}</span> · peso {w:.0%}</div>'
if not impact_html:
    impact_html='<div class="tiny">Sinais atuais indisponíveis.</div>'
news=load_news()
news_html=''
for i,n in enumerate(news,1):
    title=html.escape(n['title']); source=html.escape(n['source'])
    url=html.escape(n['url'],quote=True)
    news_html+=f'<div class="news"><span class="news-num">{i}</span> <a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a><div class="tiny">{n["when"].strftime("%d/%m %H:%M")} BRT · {source} · impacto não classificado</div></div>'
if not news_html:
    news_html='<div class="tiny">Nenhuma notícia suficientemente relevante disponível. Não exibimos manchetes inventadas.</div>'
st.markdown(f'''<div class="war-panel"><div class="section">MAIORES IMPACTOS NO MNQ</div>{impact_html}
<div class="tiny">Grupos agregados para reduzir dupla contagem. Pesos experimentais.</div></div>''', unsafe_allow_html=True)
st.markdown(f'''<div class="war-panel"><div class="section">NOTÍCIAS RELEVANTES · ÚLTIMAS 3</div>{news_html}</div>''', unsafe_allow_html=True)
st.markdown('''<div class="war-panel tiny">Cotações: Yahoo Finance (yfinance); dados podem atrasar.
Notícias: Google News RSS, com links para as fontes. Atualização da página a cada 60 segundos.
Cotações antigas são excluídas do WAR SCORE, mas podem aparecer nos cartões marcadas como ATRASADAS.
Cobertura refere-se a grupos com dados válidos; não garante disponibilidade de todos os ativos.
Pesos e metodologia exploratórios, sem backtest; não constituem recomendação de investimento.</div>''',unsafe_allow_html=True)
