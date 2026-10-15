import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
from email.utils import parsedate_to_datetime
import html
import re

st.set_page_config(page_title='WAR TRADING — LIVE MARKET 2.5', page_icon='📈', layout='wide', initial_sidebar_state='collapsed')
BRT = ZoneInfo('America/Sao_Paulo')
NOW = datetime.now(BRT)

STOCKS = [('NVDA', 'Nvidia', 8.31), ('AAPL', 'Apple', 7.51), ('MSFT', 'Microsoft', 6.09), ('MU', 'Micron', 4.48)]
ASSETS = [('NQ', 'Nasdaq Futuro', 'NQ=F'), ('ES', 'S&P 500 Futuro', 'ES=F'),
          ('SOX', 'Semicondutores', '^SOX'), ('US10Y', 'Treasury 10 anos', '^TNX'),
          ('DXY', 'Índice do Dólar', 'DX-Y.NYB'), ('VIX', 'Volatilidade S&P 500', '^VIX'),
          ('VXN', 'Volatilidade Nasdaq', '^VXN'), ('XLK', 'ETF Tecnologia', 'XLK')]
GROUP_WEIGHTS = {'mercado': .30, 'tecnologia': .25, 'juros_dolar': .25, 'volatilidade': .20}
FUTURES = {'NQ=F', 'ES=F'}
# Horário regular dos índices/ETFs/ações é tratado por idade de cotação, não por horário da página.
# Fora do pregão, o indicador é informativo e nunca um sinal operacional em tempo real.

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
.news-tag {color:#ffd25b;font-weight:800;font-size:11px}
a {color:#68caff!important}
@media(max-width:600px){
.block-container {padding:.5rem .4rem 1.5rem}
.war-panel {padding:9px}.asset-grid{gap:6px}.asset{padding:7px;min-height:112px}
.asset-name{font-size:17px}.asset-bottom span{font-size:13px}
.subbrand{letter-spacing:2px}.muted{font-size:11px}.tiny{font-size:10px}
.summary-grid{grid-template-columns:1fr 1fr;gap:6px}.section{font-size:15px}
}
</style>''', unsafe_allow_html=True)


def part_for(frame, symbol):
    if frame is None or frame.empty:
        return None
    if isinstance(frame.columns, pd.MultiIndex):
        if symbol not in frame.columns.get_level_values(0):
            return None
        return frame[symbol]
    return frame


@st.cache_data(ttl=55, show_spinner=False)
def load_quotes():
    symbols = list(dict.fromkeys([a[2] for a in ASSETS] + [s[0] for s in STOCKS]))
    out = {}
    try:
        frame = yf.download(symbols, period='5d', interval='5m', group_by='ticker',
                            auto_adjust=False, progress=False, threads=True, timeout=15)
    except Exception:
        frame = pd.DataFrame()
    try:
        daily = yf.download(symbols, period='14d', interval='1d', group_by='ticker',
                            auto_adjust=False, progress=False, threads=True, timeout=15)
    except Exception:
        daily = pd.DataFrame()
    for sym in symbols:
        try:
            intraday = part_for(frame, sym)
            if intraday is None:
                continue
            closes = pd.to_numeric(intraday['Close'], errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
            closes = closes[closes > 0]
            if closes.empty:
                continue
            ts = pd.Timestamp(closes.index[-1])
            if ts.tzinfo is None:
                continue
            stamp = ts.tz_convert(BRT).to_pydatetime()
            price = float(closes.iloc[-1])
            item = {'price': price, 'time': stamp, 'series': closes.tail(32).tolist(),
                    'pct': None, 'reference_date': None}
            dpart = part_for(daily, sym)
            if dpart is not None:
                d = pd.to_numeric(dpart['Close'], errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
                d = d[d > 0]
                # Somente fechamento de dia ANTERIOR à data da cotação intradiária.
                # Evita comparar com barra diária parcial ou futura.
                past = [(pd.Timestamp(idx).date(), float(value)) for idx, value in d.items()
                        if pd.Timestamp(idx).date() < stamp.date()]
                if past:
                    ref_date, reference = past[-1]
                    # Proteção contra fechamento muito antigo em dias úteis.
                    if (stamp.date() - ref_date).days <= 5 and reference > 0:
                        item['pct'] = (price / reference - 1) * 100
                        item['reference_date'] = ref_date
            out[sym] = item
        except Exception:
            continue
    return out


def freshness(q, symbol):
    if not q or q.get('pct') is None or q.get('time') is None:
        return False
    age = NOW - q['time']
    # Limite de idade do dado para cálculo; após fechamento, sinais à vista expiram.
    limit = timedelta(minutes=45) if symbol in FUTURES else timedelta(minutes=90)
    return timedelta(minutes=-5) <= age <= limit


def score_news_title(title):
    t = title.casefold()
    excluded = ('ballroom', 'donor', 'wedding', 'celebrity', 'football', 'soccer',
                'insider sells', 'insider buys', 'price target', 'analyst rating',
                'stock price down', 'stock price up', 'here\'s why', 'here\'s what happened',
                'shares sold', 'shares bought', 'class action', 'lawsuit filed')
    if any(x in t for x in excluded):
        return None
    categories = [
        ('FED / JUROS', 10, ('federal reserve', 'fed chair', 'fed decision', 'fomc',
                              'fed officials', 'rate cut', 'rate hike', 'interest rates')),
        ('INFLAÇÃO / EMPREGO', 10, ('consumer price index', 'cpi inflation', 'inflation data',
                                    'core pce', 'pce inflation', 'nonfarm payroll',
                                    'jobs report', 'unemployment rate', 'producer price index')),
        ('TREASURIES / DÓLAR', 8, ('treasury yields', 'treasury yield', '10-year yield',
                                   'bond yields', 'us dollar index', 'dollar index')),
        ('NASDAQ / MERCADO', 9, ('nasdaq 100', 'nasdaq-100', 'nasdaq futures',
                                 'nasdaq composite', 'wall street', 's&p 500', 'us stock futures')),
        ('BALANÇOS BIG TECH', 9, ('nvidia earnings', 'microsoft earnings', 'apple earnings',
                                   'amazon earnings', 'alphabet earnings', 'google earnings',
                                   'meta earnings', 'tesla earnings', 'micron earnings',
                                   'broadcom earnings', 'earnings guidance')),
        ('SEMICONDUTORES / IA', 7, ('semiconductor stocks', 'chip stocks', 'ai chip',
                                    'nvidia', 'semiconductor export', 'artificial intelligence spending')),
    ]
    hits = [(priority, category) for category, priority, phrases in categories
            if any(phrase in t for phrase in phrases)]
    if not hits:
        return None
    priority, category = max(hits)
    # Manchetes puramente sobre um único papel não superam dados macro.
    if category == 'SEMICONDUTORES / IA' and not any(k in t for k in
        ('earnings', 'guidance', 'chip', 'semiconductor', 'export', 'ai spending', 'artificial intelligence')):
        return None
    return priority, category


@st.cache_data(ttl=300, show_spinner=False)
def load_news():
    searches = [
        '("Federal Reserve" OR FOMC OR "rate cut" OR "rate hike") when:1d',
        '("CPI" OR "PCE inflation" OR "jobs report" OR "Treasury yields") when:1d',
        '("Nasdaq 100" OR "Nasdaq futures" OR "S&P 500" OR "Wall Street") when:1d',
        '("Nvidia earnings" OR "Microsoft earnings" OR "Apple earnings" OR "Alphabet earnings" OR "Amazon earnings" OR "Meta earnings") when:1d',
        '("semiconductor stocks" OR "chip stocks" OR "AI chip" OR "Micron earnings") when:1d',
    ]
    found = {}
    for query in searches:
        url = f'https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en'
        try:
            response = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for item in root.findall('.//item'):
                title = html.unescape(item.findtext('title') or '').strip()
                link = (item.findtext('link') or '').strip()
                source = (item.findtext('source') or 'Google News').strip()
                try:
                    when = parsedate_to_datetime(item.findtext('pubDate') or '').astimezone(BRT)
                except Exception:
                    continue
                if not title or not link.startswith('https://'):
                    continue
                age = NOW - when
                if not timedelta(minutes=-5) <= age <= timedelta(hours=24):
                    continue
                ranking = score_news_title(title)
                if ranking is None:
                    continue
                priority, category = ranking
                # Ranking por relevância e recência, não apenas pela hora.
                points = priority * 100 - age.total_seconds() / 3600 * 3
                key = re.sub(r'[^a-z0-9]+', '', title.casefold().split(' - ')[0])[:100]
                row = {'title': title, 'url': link, 'source': source, 'when': when,
                       'category': category, 'points': points}
                if key not in found or points > found[key]['points']:
                    found[key] = row
        except Exception:
            continue
    ordered = sorted(found.values(), key=lambda n: (n['points'], n['when']), reverse=True)
    # Diversidade temática: até 2 notícias de uma mesma categoria.
    chosen, counts = [], {}
    for item in ordered:
        cat = item['category']
        if counts.get(cat, 0) >= 2:
            continue
        chosen.append(item)
        counts[cat] = counts.get(cat, 0) + 1
        if len(chosen) == 3:
            break
    return chosen


def calc_score(quotes):
    lookup = {name: (symbol, quotes.get(symbol)) for name, _, symbol in ASSETS}
    def signal(name, inverse=False):
        symbol, q = lookup[name]
        if not freshness(q, symbol):
            return None
        # 2% = intensidade máxima de referência. Parâmetro experimental.
        value = float(np.clip(q['pct'] / 2.0, -1, 1))
        return -value if inverse else value

    stocks = [(float(np.clip(quotes[sym]['pct'] / 2.0, -1, 1)), weight)
              for sym, _, weight in STOCKS if freshness(quotes.get(sym), sym)]
    stocks_value = (sum(v * w for v, w in stocks) / sum(w for _, w in stocks)) if stocks else None
    tech_parts = [(signal('SOX'), .50), (signal('XLK'), .25), (stocks_value, .25)]
    available_tech = [(v, w) for v, w in tech_parts if v is not None]
    tech = (sum(v * w for v, w in available_tech) / sum(w for _, w in available_tech)) if available_tech else None
    def average(*values):
        available = [v for v in values if v is not None]
        return float(np.mean(available)) if available else None
    groups = {
        'mercado': signal('ES'),
        'tecnologia': tech,
        'juros_dolar': average(signal('US10Y', True), signal('DXY', True)),
        'volatilidade': average(signal('VIX', True), signal('VXN', True)),
    }
    valid = {k: v for k, v in groups.items() if v is not None}
    coverage = sum(GROUP_WEIGHTS[k] for k in valid)
    # Sem pelo menos 75% de cobertura, não produzimos classificação.
    score = round(100 * sum(GROUP_WEIGHTS[k] * v for k, v in valid.items()) / coverage) if coverage >= .75 else None
    return score, coverage, groups


def classify(score):
    if score is None: return ('DADOS INSUFICIENTES', '#a4b6c8')
    if score <= -60: return ('BAIXA FORTE', '#ff4265')
    if score <= -20: return ('BAIXA MODERADA', '#ff8761')
    if score < 20: return ('LATERALIZAÇÃO', '#ffd25b')
    if score < 60: return ('ALTA MODERADA', '#15d99b')
    return ('ALTA FORTE', '#15d99b')


def sparkline(values, color):
    if len(values) < 2: return ''
    arr = np.asarray(values, dtype=float)
    lo, hi = float(np.min(arr)), float(np.max(arr))
    y = 16 - (arr - lo) / (hi - lo if hi != lo else 1) * 13
    x = np.linspace(1, 94, len(arr))
    pts = ' '.join(f'{xx:.1f},{yy:.1f}' for xx, yy in zip(x, y))
    return f'<svg viewBox="0 0 96 20" width="100%" height="25" aria-hidden="true"><polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.8"/></svg>'


def asset_card(name, subtitle, q, symbol, extra=''):
    if not q:
        return f'<div class="asset stale"><div class="asset-name">{name}</div><div class="muted">{subtitle}</div><div class="asset-price">Indisponível</div><div class="tiny">Fonte sem dados</div></div>'
    pct = q.get('pct')
    up = pct is not None and pct >= 0
    valid = freshness(q, symbol)
    cls = 'stale' if not valid else ('up' if up else 'down')
    color = '#14dc99' if up else '#ff4d72'
    delta = f'{"▲" if up else "▼"} {pct:+.2f}%' if pct is not None else 'Variação indisponível'
    when = q['time'].strftime('%d/%m %H:%M') if q.get('time') else 'Horário indisponível'
    suffix = '' if valid else ' · ATRASADA / NÃO ENTRA NO SCORE'
    price = f'{q["price"]:,.2f}'
    return (f'<div class="asset {cls}"><div class="asset-name">{name}</div><div class="muted">{subtitle}{extra}</div>'
            f'<div class="asset-bottom"><span class="asset-price">{price}</span>'
            f'<span class="{"positive" if up else "negative" if pct is not None else "muted"}">{delta}</span></div>'
            f'{sparkline(q.get("series", []), color)}<div class="tiny">Cotação: {when} BRT{suffix}</div></div>')


# Atualização da página; os dados continuam sujeitos à frequência e disponibilidade da fonte.
st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)
with st.spinner('Consultando mercado...'):
    quotes = load_quotes()
score, coverage, groups = calc_score(quotes)
classification, status_color = classify(score)
score_str = f'{score:+d}' if score is not None else '—'

st.markdown(f'''<div class="war-panel"><div class="brand">WAR TRADING</div><div class="subbrand">LIVE MARKET 2.5</div>
<div class="muted">BRASÍLIA · {NOW.strftime('%d/%m/%Y %H:%M:%S')} · ↻ 60 SEG</div></div>''', unsafe_allow_html=True)
position = 50 if score is None else (score + 100) / 2
st.markdown(f'''<div class="summary-grid">
<div class="war-panel"><div class="section">CONCLUSÃO PARA O MNQ</div>
<div class="status" style="color:{status_color}">{classification}</div>
<div class="muted">Leitura intermarket: {score_str}. Cobertura de grupos: {coverage:.0%}.
NQ é referência, não soma. Indicador experimental, não é sinal de entrada.</div></div>
<div class="war-panel"><div class="section">WAR SCORE MNQ</div>
<div class="status" style="text-align:center">{score_str}</div>
<div class="gauge"><div class="gauge-pin" style="left:{position}%"></div></div>
<div class="tiny">-100 BAIXA | 0 NEUTRO | +100 ALTA</div></div></div>''', unsafe_allow_html=True)

st.markdown('<div class="section">RADAR INTERMARKET · 8 ATIVOS</div>', unsafe_allow_html=True)
st.markdown('<div class="asset-grid">' + ''.join(asset_card(name, desc, quotes.get(sym), sym) for name, desc, sym in ASSETS) + '</div>', unsafe_allow_html=True)
st.markdown('<div class="section">TOP 4 AÇÕES · PESOS DE REFERÊNCIA</div>', unsafe_allow_html=True)
st.caption('Pesos ilustrativos de referência do QQQ em 13/10/2026; não atualizados automaticamente. Confirme a composição antes de operar.')
st.markdown('<div class="asset-grid">' + ''.join(asset_card(sym, company, quotes.get(sym), sym, f' · peso ref. {weight:.2f}%') for sym, company, weight in STOCKS) + '</div>', unsafe_allow_html=True)

impacts = []
for label, group in [('ES', 'mercado'), ('SOX / XLK / AÇÕES', 'tecnologia'), ('US10Y / DXY', 'juros_dolar'), ('VIX / VXN', 'volatilidade')]:
    value = groups[group]
    if value is not None:
        impacts.append((abs(value * GROUP_WEIGHTS[group]), label, value, GROUP_WEIGHTS[group]))
impact_html = ''
for _, label, value, weight in sorted(impacts, reverse=True):
    direction = 'FAVORÁVEL' if value >= 0 else 'DESFAVORÁVEL'
    color = '#14dc99' if value >= 0 else '#ff4d72'
    impact_html += f'<div class="impact"><b>{label}</b><br><span style="color:{color}">{direction}</span> · peso {weight:.0%}</div>'
if not impact_html:
    impact_html = '<div class="tiny">Sinais atuais indisponíveis.</div>'

news = load_news()
news_html = ''
for i, item in enumerate(news, 1):
    title = html.escape(item['title'])
    source = html.escape(item['source'])
    url = html.escape(item['url'], quote=True)
    category = html.escape(item['category'])
    news_html += (f'<div class="news"><span class="news-num">{i}</span> '
                  f'<span class="news-tag">{category}</span><br>'
                  f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
                  f'<div class="tiny">{item["when"].strftime("%d/%m %H:%M")} BRT · {source} · impacto direcional não classificado</div></div>')
if not news_html:
    news_html = '<div class="tiny">Nenhuma notícia com relevância suficiente nas últimas 24h. Não exibimos notícias genéricas para preencher espaço.</div>'

# Quadros propositalmente EMPILHADOS, inclusive em telas grandes.
st.markdown(f'<div class="war-panel"><div class="section">MAIORES IMPACTOS NO MNQ</div>{impact_html}<div class="tiny">Grupos agregados para reduzir dupla contagem. Pesos experimentais.</div></div>', unsafe_allow_html=True)
st.markdown(f'<div class="war-panel"><div class="section">NOTÍCIAS RELEVANTES · TOP 3 POR PRIORIDADE</div>{news_html}</div>', unsafe_allow_html=True)
st.markdown('''<div class="war-panel tiny">Cotações: Yahoo Finance (yfinance), sujeitas a atrasos e indisponibilidade. Notícias: Google News RSS; ranking heurístico por tema e recência, sem leitura do conteúdo integral. Atualização da página a cada 60 segundos, quando o navegador permitir. Percentuais contra o último fechamento diário anterior disponível. Cotações fora do limite de idade não entram no WAR SCORE. Pesos, sinais inversos e escala de intensidade são hipóteses não validadas por backtest; o WAR SCORE não é recomendação nem sinal de entrada.</div>''', unsafe_allow_html=True)
