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

st.set_page_config(page_title='WAR TRADING — LIVE MARKET 2.7', page_icon='📈', layout='wide', initial_sidebar_state='collapsed')
BRT = ZoneInfo('America/Sao_Paulo')
NOW = datetime.now(BRT)

STOCKS = [('NVDA', 'Nvidia', 8.31), ('AAPL', 'Apple', 7.51), ('MSFT', 'Microsoft', 6.09), ('MU', 'Micron', 4.48)]
ASSETS = [('NQ', 'Nasdaq Futuro', 'NQ=F'), ('ES', 'S&P 500 Futuro', 'ES=F'),
          ('SOX', 'Semicondutores', '^SOX'), ('US10Y', 'Treasury 10 anos', '^TNX'),
          ('DXY', 'Índice do Dólar', 'DX-Y.NYB'), ('VIX', 'Volatilidade S&P 500', '^VIX'),
          ('VXN', 'Volatilidade Nasdaq', '^VXN'), ('XLK', 'ETF Tecnologia', 'XLK')]
GROUP_WEIGHTS = {'mercado': .30, 'tecnologia': .25, 'juros_dolar': .25, 'volatilidade': .20}
FUTURES = {'NQ=F', 'ES=F'}
CASH_SYMBOLS = {'^SOX', '^TNX', '^VIX', '^VXN', 'XLK', 'NVDA', 'AAPL', 'MSFT', 'MU'}
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
        frame = yf.download(symbols, period='7d', interval='5m', group_by='ticker',
                            auto_adjust=False, progress=False, threads=True, timeout=15)
    except Exception:
        frame = pd.DataFrame()
    try:
        daily = yf.download(symbols, period='20d', interval='1d', group_by='ticker',
                            auto_adjust=False, progress=False, threads=True, timeout=15)
    except Exception:
        daily = pd.DataFrame()
    for sym in symbols:
        try:
            intraday = part_for(frame, sym)
            dpart = part_for(daily, sym)
            closes = (pd.to_numeric(intraday['Close'], errors='coerce')
                      .replace([np.inf, -np.inf], np.nan).dropna()) if intraday is not None else pd.Series(dtype=float)
            closes = closes[closes > 0]
            daily_fallback = False
            if not closes.empty:
                ts = pd.Timestamp(closes.index[-1])
                if ts.tzinfo is None:
                    continue
                stamp = ts.tz_convert(BRT).to_pydatetime()
                price = float(closes.iloc[-1])
            elif dpart is not None:
                # Último fechamento diário, caso a fonte não entregue barras intradiárias.
                dc = pd.to_numeric(dpart['Close'], errors='coerce').replace([np.inf, -np.inf], np.nan).dropna()
                dc = dc[dc > 0]
                if dc.empty:
                    continue
                last_day = pd.Timestamp(dc.index[-1]).date()
                stamp = datetime.combine(last_day, datetime.min.time(), tzinfo=BRT).replace(hour=17)
                price = float(dc.iloc[-1])
                closes = dc.tail(32)
                daily_fallback = True
            else:
                continue
            item = {'price': price, 'time': stamp, 'series': closes.tail(32).tolist(),
                    'pct': None, 'reference_date': None, 'daily_fallback': daily_fallback}
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


def market_closed(symbol):
    """Horários aproximados NY; feriados e sessões especiais não são inferidos."""
    ny = NOW.astimezone(ZoneInfo('America/New_York'))
    weekday = ny.weekday()
    minutes = ny.hour * 60 + ny.minute
    if symbol in FUTURES:
        # CME: pausa diária aproximada 17:00-18:00 NY; fim de semana.
        return (weekday == 5 or (weekday == 6 and minutes < 18 * 60)
                or (weekday == 4 and minutes >= 17 * 60)
                or (weekday < 5 and 17 * 60 <= minutes < 18 * 60))
    if symbol == 'DX-Y.NYB':
        # Horário variável conforme fornecedor; fim de semana é inequívoco.
        return weekday >= 5
    return weekday >= 5 or minutes < 9 * 60 + 30 or minutes >= 16 * 60


def quote_status(q, symbol):
    """Preserva fechamentos identificados; nunca trata preço antigo como ao vivo."""
    if not q or q.get('pct') is None or q.get('time') is None:
        return 'sem_referencia'
    age = NOW - q['time']
    if age < timedelta(minutes=-5):
        return 'obsoleta'
    limit = timedelta(minutes=60) if symbol in FUTURES or symbol == 'DX-Y.NYB' else timedelta(minutes=90)
    if age <= limit and not q.get('daily_fallback'):
        return 'recente'
    if market_closed(symbol) and age <= timedelta(days=7):
        return 'fechamento'
    return 'obsoleta'


def freshness(q, symbol):
    return quote_status(q, symbol) in ('recente', 'fechamento')


def score_news_title(title):
    t = title.casefold()
    # Evita falsos positivos: "rate hike" pode ser tarifa de energia ou seguros.
    excluded = ('utility rate', 'electric rate', 'water rate', 'insurance rate',
                'rate hike for', 'rate hike on', 'rate increase for', 'rate increase on',
                'consumers rate hike', 'rate hike approved', 'local jobs report',
                'state releases', 'school', 'county', 'city council', 'ballroom',
                'wedding', 'celebrity', 'football', 'soccer', 'insider sells',
                'insider buys', 'price target', 'analyst rating', 'stock price down',
                'stock price up', "here's why", "here's what happened", 'shares sold',
                'shares bought', 'class action', 'lawsuit filed')
    if any(x in t for x in excluded):
        return None
    categories = [
        ('FED / JUROS', 12, ('federal reserve', 'fomc', 'fed chair', 'fed governor',
                             'fed officials', 'fed rate', 'fed cuts', 'fed hikes',
                             'powell says', 'banco central americano')),
        ('INFLAÇÃO / EMPREGO', 12, ('us cpi', 'u.s. cpi', 'consumer price index',
                                    'core pce', 'pce inflation', 'us payrolls',
                                    'nonfarm payroll', 'us jobs report',
                                    'u.s. jobs report', 'us unemployment',
                                    'u.s. unemployment', 'producer price index')),
        ('TREASURIES / DÓLAR', 10, ('treasury yields', 'treasury yield', '10-year yield',
                                    'us 10-year', 'u.s. 10-year', 'dollar index',
                                    'dxy', 'rendimento dos treasuries')),
        ('NASDAQ / MERCADO', 11, ('nasdaq 100', 'nasdaq-100', 'nasdaq futures',
                                  'nasdaq composite', 'wall street stocks',
                                  's&p 500 futures', 'us stock futures',
                                  'u.s. stock futures', 'futuros do nasdaq')),
        ('BALANÇOS BIG TECH', 11, ('nvidia earnings', 'microsoft earnings',
                                   'apple earnings', 'amazon earnings',
                                   'alphabet earnings', 'meta earnings',
                                   'tesla earnings', 'micron earnings',
                                   'broadcom earnings', 'big tech earnings')),
        ('SEMICONDUTORES / IA', 9, ('semiconductor stocks', 'chip stocks',
                                    'ai chip', 'semiconductor export',
                                    'chip export restrictions', 'nvidia ai chips')),
    ]
    hits = [(weight, category) for category, weight, phrases in categories
            if any(phrase in t for phrase in phrases)]
    return max(hits) if hits else None


@st.cache_data(ttl=900, show_spinner=False)
def translate_title(title):
    """Tradução automática best-effort, preservando o original se falhar."""
    try:
        response = requests.get('https://translate.googleapis.com/translate_a/single',
            params={'client': 'gtx', 'sl': 'auto', 'tl': 'pt', 'dt': 't', 'q': title},
            timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        chunks = response.json()[0]
        translated = ''.join(part[0] for part in chunks if part and part[0]).strip()
        return translated if translated else title
    except Exception:
        return title


@st.cache_data(ttl=300, show_spinner=False)
def load_news():
    searches = [
        '("Federal Reserve" OR FOMC OR "Jerome Powell") (stocks OR markets OR rates) when:1d',
        '("US CPI" OR "core PCE" OR "nonfarm payroll" OR "Treasury yields") when:1d',
        '("Nasdaq 100" OR "Nasdaq futures" OR "S&P 500 futures") when:1d',
        '("Nvidia earnings" OR "Microsoft earnings" OR "Apple earnings" OR "Amazon earnings" OR "Meta earnings") when:1d',
        '("semiconductor stocks" OR "AI chip" OR "chip export restrictions") when:1d',
    ]
    # Fontes de cobertura econômica/financeira. Fonte não equivale a confirmação
    # de impacto: o filtro só lê títulos, não o corpo da notícia.
    allowed = ('reuters', 'bloomberg', 'cnbc', 'associated press', 'ap news',
               'marketwatch', 'yahoo finance', 'financial times', 'barron',
               'wall street journal', 'investing.com', 'the economist',
               'the guardian', 'fortune', 'business insider')
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
                source = (item.findtext('source') or '').strip()
                if not title or not link.startswith('https://') or not any(x in source.casefold() for x in allowed):
                    continue
                try:
                    when = parsedate_to_datetime(item.findtext('pubDate') or '').astimezone(BRT)
                except Exception:
                    continue
                age = NOW - when
                if not timedelta(minutes=-5) <= age <= timedelta(hours=24):
                    continue
                ranked = score_news_title(title)
                if ranked is None:
                    continue
                priority, category = ranked
                points = priority * 100 - age.total_seconds() / 3600 * 3
                key = re.sub(r'[^a-z0-9]+', '', title.casefold().split(' - ')[0])[:100]
                row = {'title': title, 'url': link, 'source': source,
                       'when': when, 'category': category, 'points': points}
                if key not in found or points > found[key]['points']:
                    found[key] = row
        except Exception:
            continue
    ordered = sorted(found.values(), key=lambda n: (n['points'], n['when']), reverse=True)
    chosen, counts = [], {}
    for item in ordered:
        category = item['category']
        if counts.get(category, 0) >= 2:
            continue
        chosen.append(item)
        counts[category] = counts.get(category, 0) + 1
        if len(chosen) == 3:
            break
    for item in chosen:
        item['title_pt'] = translate_title(item['title'])
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
    status = quote_status(q, symbol)
    valid = status in ('recente', 'fechamento')
    cls = 'stale' if not valid else ('up' if up else 'down')
    color = '#14dc99' if up else '#ff4d72'
    delta = f'{"▲" if up else "▼"} {pct:+.2f}%' if pct is not None else 'Variação indisponível'
    when = q['time'].strftime('%d/%m %H:%M') if q.get('time') else 'Horário indisponível'
    suffix = (' · ÚLTIMO FECHAMENTO / SCORE INFORMATIVO' if status == 'fechamento'
              else '' if valid else ' · ATRASADA / NÃO ENTRA NO SCORE')
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
using_closes = any(quote_status(quotes.get(sym), sym) == 'fechamento' for _, _, sym in ASSETS)
classification, status_color = classify(score)
score_str = f'{score:+d}' if score is not None else '—'
score_mode = 'LEITURA COM ÚLTIMOS FECHAMENTOS · INFORMATIVA' if using_closes else 'LEITURA COM COTAÇÕES RECENTES'

st.markdown(f'''<div class="war-panel"><div class="brand">WAR TRADING</div><div class="subbrand">LIVE MARKET 2.7</div>
<div class="muted">BRASÍLIA · {NOW.strftime('%d/%m/%Y %H:%M:%S')} · ↻ 60 SEG</div></div>''', unsafe_allow_html=True)
position = 50 if score is None else (score + 100) / 2
st.markdown(f'''<div class="summary-grid">
<div class="war-panel"><div class="section">CONCLUSÃO PARA O MNQ</div>
<div class="status" style="color:{status_color}">{classification}</div>
<div class="muted">Leitura intermarket: {score_str}. Cobertura de grupos: {coverage:.0%}.
{score_mode}. NQ é referência, não soma. Indicador experimental; não é sinal de entrada.</div></div>
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
    title = html.escape(item.get('title_pt', item['title']))
    source = html.escape(item['source'])
    url = html.escape(item['url'], quote=True)
    category = html.escape(item['category'])
    news_html += (f'<div class="news"><span class="news-num">{i}</span> '
                  f'<span class="news-tag">{category}</span><br>'
                  f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
                  f'<div class="tiny">{item["when"].strftime("%d/%m %H:%M")} BRT · {source} · impacto direcional não classificado</div></div>')
if not news_html:
    news_html = '<div class="tiny">Nenhuma manchete verificada de fonte financeira e relevância suficiente nas últimas 24h. Não exibimos notícias genéricas para preencher espaço.</div>'

# Quadros propositalmente EMPILHADOS, inclusive em telas grandes.
st.markdown(f'<div class="war-panel"><div class="section">MAIORES IMPACTOS NO MNQ</div>{impact_html}<div class="tiny">Grupos agregados para reduzir dupla contagem. Pesos experimentais.</div></div>', unsafe_allow_html=True)
st.markdown(f'<div class="war-panel"><div class="section">NOTÍCIAS RELEVANTES · TOP 3 POR PRIORIDADE</div>{news_html}</div>', unsafe_allow_html=True)
st.markdown('''<div class="war-panel tiny">Cotações: Yahoo Finance (yfinance), sujeitas a atrasos e indisponibilidade. Notícias: Google News RSS, fontes financeiras selecionadas e tradução automática (pode falhar); classificação heurística sem leitura do conteúdo integral. Atualização da página a cada 60 segundos, quando o navegador permitir. Percentuais contra o último fechamento diário anterior disponível. Com mercado fechado, últimos preços disponíveis (até 7 dias) podem compor SCORE INFORMATIVO; dados antigos durante mercado aberto são excluídos. Feriados e horários especiais podem exigir revisão. Pesos, sinais inversos e escala de intensidade são hipóteses não validadas por backtest; o WAR SCORE não é recomendação nem sinal de entrada.</div>''', unsafe_allow_html=True)
