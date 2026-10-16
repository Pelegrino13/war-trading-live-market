import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from urllib.parse import quote
from email.utils import parsedate_to_datetime
import html
import re

st.set_page_config(page_title='WAR TRADING — LIVE MARKET 3.0', page_icon='📈', layout='wide', initial_sidebar_state='collapsed')
BRT = ZoneInfo('America/Sao_Paulo')
NY = ZoneInfo('America/New_York')
STOCKS = [('NVDA', 'Nvidia', 8.31), ('AAPL', 'Apple', 7.51), ('MSFT', 'Microsoft', 6.09), ('MU', 'Micron', 4.48)]
ASSETS = [('NQ', 'Nasdaq Futuro', 'NQ=F'), ('ES', 'S&P 500 Futuro', 'ES=F'),
          ('SOX', 'Semicondutores', '^SOX'), ('US10Y', 'Treasury 10 anos', '^TNX'),
          ('DXY', 'Índice do Dólar', 'DX-Y.NYB'), ('VIX', 'Volatilidade S&P 500', '^VIX'),
          ('VXN', 'Volatilidade Nasdaq', '^VXN'), ('XLK', 'ETF Tecnologia', 'XLK')]
GROUP_WEIGHTS = {'mercado': .30, 'tecnologia': .25, 'juros_dolar': .25, 'volatilidade': .20}
FUTURES = {'NQ=F', 'ES=F'}
CASH_SYMBOLS = {'^SOX', '^TNX', '^VIX', '^VXN', 'XLK', 'NVDA', 'AAPL', 'MSFT', 'MU'}

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
        if symbol in frame.columns.get_level_values(0):
            return frame[symbol]
        if symbol in frame.columns.get_level_values(1):
            return frame.xs(symbol, axis=1, level=1)
        return None
    return frame


def cleaned_close(frame):
    if frame is None or 'Close' not in frame:
        return pd.Series(dtype=float)
    values = pd.to_numeric(frame['Close'], errors='coerce')
    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]
    return values.replace([np.inf, -np.inf], np.nan).dropna().loc[lambda x: x > 0]


@st.cache_data(ttl=55, show_spinner=False)
def load_quotes():
    symbols = list(dict.fromkeys([a[2] for a in ASSETS] + [s[0] for s in STOCKS]))
    try:
        intraday = yf.download(symbols, period='7d', interval='5m', group_by='ticker',
                               auto_adjust=False, progress=False, threads=True, timeout=15)
    except Exception:
        intraday = pd.DataFrame()
    try:
        daily = yf.download(symbols, period='20d', interval='1d', group_by='ticker',
                            auto_adjust=False, progress=False, threads=True, timeout=15)
    except Exception:
        daily = pd.DataFrame()
    out = {}
    for sym in symbols:
        try:
            i = cleaned_close(part_for(intraday, sym))
            d = cleaned_close(part_for(daily, sym))
            daily_fallback = i.empty
            if not i.empty:
                timestamp = pd.Timestamp(i.index[-1])
                if timestamp.tzinfo is None:
                    continue  # Não inventar fuso de barras intradiárias.
                stamp = timestamp.tz_convert(BRT).to_pydatetime()
                price = float(i.iloc[-1])
                series = i.tail(32).tolist()
            elif not d.empty:
                # Data diária sem hora real: NÃO afirmar que o fechamento foi às 17h.
                day = pd.Timestamp(d.index[-1]).date()
                stamp = datetime.combine(day, time(0, 0), tzinfo=BRT)
                price = float(d.iloc[-1])
                series = d.tail(32).tolist()
            else:
                continue
            reference = None
            reference_date = None
            # Barras diárias podem incluir dia atual parcial; usar apenas dia anterior.
            if not daily_fallback:
                candidates = [(pd.Timestamp(idx).date(), float(v)) for idx, v in d.items()
                              if pd.Timestamp(idx).date() < stamp.date()]
            else:
                candidates = [(pd.Timestamp(idx).date(), float(v)) for idx, v in d.iloc[:-1].items()]
            if candidates:
                reference_date, reference = candidates[-1]
            pct = None
            if reference and reference > 0 and (stamp.date() - reference_date).days <= 5:
                pct = (price / reference - 1) * 100
            out[sym] = dict(price=price, time=stamp, series=series, pct=pct,
                            reference_date=reference_date, daily_fallback=daily_fallback)
        except Exception:
            continue
    return out


def session_open(symbol, now):
    """Aproximação das sessões NY; não é calendário de feriados da bolsa."""
    ny = now.astimezone(NY)
    day, minute = ny.weekday(), ny.hour * 60 + ny.minute
    if symbol in FUTURES:
        return ((day == 6 and minute >= 18 * 60) or
                (day in (0, 1, 2, 3) and not (17 * 60 <= minute < 18 * 60)) or
                (day == 4 and minute < 17 * 60))
    if symbol == 'DX-Y.NYB':
        return day < 5  # Horários específicos do DXY variam por fornecedor.
    return day < 5 and 9 * 60 + 30 <= minute < 16 * 60


def quote_status(q, symbol, now):
    if not q or q.get('pct') is None or q.get('time') is None:
        return 'sem_referencia'
    age = now - q['time']
    if age < timedelta(minutes=-5):
        return 'obsoleta'
    if q.get('daily_fallback'):
        # Fechamento diário não possui timestamp intradiário confiável.
        return 'fechamento' if not session_open(symbol, now) and age <= timedelta(days=4) else 'obsoleta'
    limit = timedelta(minutes=20) if symbol in FUTURES or symbol == 'DX-Y.NYB' else timedelta(minutes=25)
    if age <= limit and session_open(symbol, now):
        return 'recente'
    if not session_open(symbol, now) and age <= timedelta(days=4):
        return 'fechamento'
    return 'obsoleta'


def score_news_title(title):
    """Seleciona eventos econômicos e notícias de mercado, não páginas de instrumentos."""
    t = title.casefold()
    blocked = (
        'option chain', 'options chain', 'option quotes', 'options quotes',
        'total return index', 'historical data', 'historical prices',
        'stock quote', 'stock price history', 'real-time quote', 'realtime quote',
        'market cap', 'dividend history', 'technical analysis', 'price target',
        'analyst rating', 'insider sells', 'insider buys', 'shares sold',
        'shares bought', 'class action', 'lawsuit filed', 'earnings calendar',
        'economic calendar', 'etf holdings', 'index methodology',
        'utility rate', 'electric rate', 'water rate', 'insurance rate',
        'rate hike for', 'rate hike on', 'rate increase for', 'rate increase on',
        'local jobs report', 'state releases', 'school', 'county', 'city council',
        'ballroom', 'wedding', 'celebrity', 'football', 'soccer',
        'how to buy', 'should you buy', 'best stocks to buy', 'stock forecast',
        'what is', 'explained:', 'price prediction', 'investing guide',
    )
    if any(phrase in t for phrase in blocked):
        return None
    categories = [
        ('FED / JUROS', 14, ('federal reserve', 'fomc', 'fed chair',
            'fed governor', 'fed officials', 'fed rate', 'fed cuts',
            'fed hikes', 'powell says', 'fed president', 'interest rate decision')),
        ('INFLAÇÃO / EMPREGO', 14, ('us cpi', 'u.s. cpi', 'consumer price index',
            'core pce', 'pce inflation', 'us payrolls', 'nonfarm payroll',
            'us jobs report', 'u.s. jobs report', 'us unemployment',
            'producer price index', 'us inflation', 'u.s. inflation')),
        ('TREASURIES / DÓLAR', 11, ('treasury yields', 'treasury yield',
            '10-year yield', 'us 10-year', 'u.s. 10-year', 'dollar index', 'dxy')),
        ('NASDAQ / MERCADO', 12, ('nasdaq 100', 'nasdaq-100', 'nasdaq futures',
            'nasdaq composite', 'wall street stocks', 's&p 500 futures',
            'us stock futures', 'u.s. stock futures', 'wall street falls',
            'wall street rises', 'wall street rallies', 'wall street slides')),
        ('BALANÇOS BIG TECH', 12, ('nvidia earnings', 'microsoft earnings',
            'apple earnings', 'amazon earnings', 'alphabet earnings',
            'meta earnings', 'tesla earnings', 'micron earnings',
            'broadcom earnings', 'nvidia results', 'microsoft results',
            'apple results', 'amazon results', 'alphabet results')),
        ('SEMICONDUTORES / IA', 10, ('semiconductor stocks', 'chip stocks',
            'ai chip', 'semiconductor export', 'chip export restrictions',
            'nvidia ai chips', 'chipmakers', 'semiconductor tariffs')),
    ]
    hits = [(weight, category) for category, weight, phrases in categories
            if any(phrase in t for phrase in phrases)]
    if not hits:
        return None
    # A menção a um índice, isoladamente, não constitui uma notícia.
    category = max(hits)[1]
    if category == 'NASDAQ / MERCADO':
        event_words = (r'\b(fall|falls|fell|drop|drops|dropped|slide|slides|'
                       r'rise|rises|rose|gain|gains|gained|rally|rallies|'
                       r'jump|jumps|surge|surges|slump|slumps|sink|sinks|'
                       r'tumble|tumbles|plunge|plunges|rebound|rebounds|'
                       r'flat|steady|mixed|slip|slips|dip|dips|retreat|'
                       r'climb|climbs|edge|edges|trade|trades|trading|'
                       r'open|opens|close|closes|futures|selloff|sell-off)\b')
        if not re.search(event_words, t):
            return None
    return max(hits)


def news_direction(title):
    """Rotula movimento observado do Nasdaq, sem prever reação a eventos macro."""
    t = title.casefold()
    # Exige que a manchete trate do mercado de ações, não de outro ativo.
    if not re.search(r'\b(nasdaq|s&p 500|stock futures|stocks|wall street)\b', t):
        return None
    up = bool(re.search(r'\b(rise|rises|rose|gain|gains|gained|rally|rallies|'
                        r'jump|jumps|surge|surges|rebound|rebounds|climb|climbs)\b', t))
    down = bool(re.search(r'\b(fall|falls|fell|drop|drops|dropped|slide|slides|'
                          r'slump|slumps|sink|sinks|tumble|tumbles|plunge|plunges)\b', t))
    if up == down:
        return None
    return 'POSITIVO NASDAQ' if up else 'NEGATIVO NASDAQ'


@st.cache_data(ttl=900, show_spinner=False)
def translate_title(title):
    try:
        response = requests.get('https://translate.googleapis.com/translate_a/single',
            params={'client': 'gtx', 'sl': 'auto', 'tl': 'pt', 'dt': 't', 'q': title},
            timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        chunks = response.json()[0]
        translated = ''.join(part[0] for part in chunks if part and part[0]).strip()
        return translated or title
    except Exception:
        return title


@st.cache_data(ttl=300, show_spinner=False)
def load_news():
    now = datetime.now(BRT)
    searches = [
        '("Federal Reserve" OR FOMC OR "Fed chair") (stocks OR markets OR rates) when:1d',
        '("US CPI" OR "core PCE" OR "nonfarm payroll" OR "Treasury yields") when:1d',
        '("Nasdaq futures" OR "S&P 500 futures" OR "Nasdaq composite") when:1d',
        '("Nvidia earnings" OR "Microsoft earnings" OR "Apple earnings" OR "Amazon earnings" OR "Meta earnings") when:1d',
        '("semiconductor stocks" OR "AI chips" OR "chip export restrictions") when:1d',
    ]
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
                age = now - when
                if not timedelta(minutes=-5) <= age <= timedelta(hours=24):
                    continue
                ranked = score_news_title(title)
                if ranked is None:
                    continue
                priority, category = ranked
                # Penalidade moderada por idade; macro tem prioridade sobre manchetes genéricas.
                points = priority * 100 - age.total_seconds() / 3600 * 9
                if category == 'NASDAQ / MERCADO':
                    points -= age.total_seconds() / 3600 * 16
                base = re.sub(r'\s+-\s+[^-]+$', '', title).casefold()
                key = re.sub(r'[^a-z0-9]+', '', base)[:110]
                row = dict(title=title, url=link, source=source, when=when,
                           category=category, points=points, direction=news_direction(title))
                if key not in found or points > found[key]['points']:
                    found[key] = row
        except Exception:
            continue
    ordered = sorted(found.values(), key=lambda n: (n['points'], n['when']), reverse=True)
    chosen, counts, event_keys = [], {}, set()
    stop = {'stocks', 'stock', 'market', 'markets', 'nasdaq', 'futures',
            'today', 'after', 'amid', 'says', 'said', 'rates', 'rate',
            'federal', 'reserve', 'wall', 'street', 'shares', 'the', 'with'}

    def story_tokens(item):
        title = re.sub(r'\s+-\s+[^-]+$', '', item['title'].casefold())
        return set(re.findall(r'[a-z]{4,}', title)) - stop

    def event_key(item):
        t = item['title'].casefold()
        if item['category'] == 'FED / JUROS':
            # Declarações de um mesmo dirigente e expectativas da mesma reunião
            # não devem monopolizar o Top 3.
            if any(w in t for w in ('warsh', 'powell', 'fed chair', 'fed president')):
                return 'fed_discurso_' + next((w for w in ('warsh', 'powell') if w in t), 'dirigente')
            if any(w in t for w in ('hold', 'holding', 'unchanged', 'pause', 'cut', 'hike')):
                return 'fed_decisao_expectativas'
        if item['category'] == 'INFLAÇÃO / EMPREGO':
            for term in ('cpi', 'pce', 'payroll', 'unemployment', 'ppi'):
                if term in t:
                    return 'macro_' + term
        if item['category'] == 'NASDAQ / MERCADO':
            if 'pre-market' in t or 'premarket' in t or 'before the bell' in t:
                return 'mercado_premarket'
            return 'mercado_sessao'
        return None

    for item in ordered:
        category = item['category']
        if counts.get(category, 0) >= 1:
            continue  # eventos distintos: no máximo uma notícia por categoria
        key = event_key(item)
        if key and key in event_keys:
            continue
        tokens = story_tokens(item)
        duplicate = any(
            len(tokens & story_tokens(old)) >= 3 and
            len(tokens & story_tokens(old)) / max(1, min(len(tokens), len(story_tokens(old)))) >= .55
            for old in chosen
        )
        if duplicate:
            continue
        # Notícia de pré-mercado perde prioridade após o início da sessão NY.
        ny = now.astimezone(NY)
        if key == 'mercado_premarket' and ny.hour >= 12:
            continue
        chosen.append(item)
        counts[category] = counts.get(category, 0) + 1
        if key:
            event_keys.add(key)
        if len(chosen) == 3:
            break
    for item in chosen:
        item['title_pt'] = translate_title(item['title'])
    return chosen


@st.cache_data(ttl=21600, show_spinner=False)
def load_qqq_weights():
    """Fonte opcional; sem dados verificáveis mantém pesos antigos rotulados."""
    try:
        holdings = yf.Ticker('QQQ').funds_data.top_holdings
        if not isinstance(holdings, pd.DataFrame) or holdings.empty:
            return None
        # yfinance costuma retornar símbolos no índice e coluna 'Holding Percent'.
        col = next((c for c in holdings.columns if str(c).casefold() in
                    ('holding percent', 'holding_percent', 'weight')), None)
        if col is None:
            return None
        result = {}
        for sym, _, _ in STOCKS:
            if sym not in holdings.index:
                return None
            val = float(holdings.loc[sym, col])
            if not np.isfinite(val) or val <= 0:
                return None
            result[sym] = val * 100 if val <= 1 else val
        if not all(0 < x < 30 for x in result.values()):
            return None
        # A API não garante data da composição; evitar rotular como peso atual confirmado.
        return result
    except Exception:
        return None


GROUP_COMPONENTS = {
    'mercado': [('ES', 'ES=F')],
    'tecnologia': [('SOX', '^SOX'), ('XLK', 'XLK'),
                   ('NVDA', 'NVDA'), ('AAPL', 'AAPL'), ('MSFT', 'MSFT'), ('MU', 'MU')],
    'juros_dolar': [('US10Y', '^TNX'), ('DXY', 'DX-Y.NYB')],
    'volatilidade': [('VIX', '^VIX'), ('VXN', '^VXN')],
}
GROUP_NAMES = {
    'mercado': 'ES', 'tecnologia': 'SOX / XLK / AÇÕES',
    'juros_dolar': 'US10Y / DXY', 'volatilidade': 'VIX / VXN',
}
STATUS_NAMES = {
    'recente': 'recente', 'fechamento': 'último fechamento',
    'obsoleta': 'atrasada', 'sem_referencia': 'sem referência de variação',
}


def calc_score(quotes, now, weights):
    """Devolve pontuação, cobertura, grupos, modo e auditoria de cada grupo.

    Fora das sessões usa apenas fechamentos identificados. Em horário misto
    utiliza somente dados recentes; não mistura fechamento com intraday.
    """
    market_off = all(not session_open(sym, now) for _, _, sym in ASSETS)
    mode = 'fechamento' if market_off else 'recente'

    def signal(sym, inverse=False):
        q = quotes.get(sym)
        status = quote_status(q, sym, now)
        permitted = ('recente', 'fechamento') if market_off else ('recente',)
        if status not in permitted:
            return None
        return float(np.clip(q['pct'] / 2.0, -1, 1)) * (-1 if inverse else 1)

    def average(*values):
        vals = [v for v in values if v is not None]
        return float(np.mean(vals)) if vals else None

    available_stocks = [(signal(sym), weights.get(sym, ref)) for sym, _, ref in STOCKS]
    available_stocks = [(v, w) for v, w in available_stocks if v is not None and w > 0]
    stocks_value = (sum(v*w for v, w in available_stocks) /
                    sum(w for _, w in available_stocks)) if available_stocks else None
    tech_parts = [(signal('^SOX'), .50), (signal('XLK'), .25), (stocks_value, .25)]
    tech_parts = [(v, w) for v, w in tech_parts if v is not None]
    tech = sum(v*w for v, w in tech_parts)/sum(w for _, w in tech_parts) if tech_parts else None
    groups = {
        'mercado': signal('ES=F'),
        'tecnologia': tech,
        'juros_dolar': average(signal('^TNX', True), signal('DX-Y.NYB', True)),
        'volatilidade': average(signal('^VIX', True), signal('^VXN', True)),
    }
    coverage = sum(GROUP_WEIGHTS[k] for k, v in groups.items() if v is not None)
    score = (round(100 * sum(GROUP_WEIGHTS[k] * v for k, v in groups.items()
                             if v is not None) / coverage) if coverage >= .75 else None)
    details = {}
    for key, members in GROUP_COMPONENTS.items():
        used, excluded = [], []
        for name, sym in members:
            status = quote_status(quotes.get(sym), sym, now)
            allowed = status in (('recente', 'fechamento') if market_off else ('recente',))
            if allowed:
                used.append(name + (' (fech.)' if status == 'fechamento' else ''))
            else:
                excluded.append(f'{name}: {STATUS_NAMES.get(status, status)}')
        details[key] = {'used': used, 'excluded': excluded,
                        'value': groups[key], 'weight': GROUP_WEIGHTS[key]}
    return score, coverage, groups, mode, details


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


def asset_card(name, subtitle, q, symbol, now, extra=''):
    if not q:
        return f'<div class="asset stale"><div class="asset-name">{name}</div><div class="muted">{subtitle}</div><div class="asset-price">Indisponível</div><div class="tiny">Fonte sem dados</div></div>'
    pct = q.get('pct')
    up = pct is not None and pct >= 0
    status = quote_status(q, symbol, now)
    valid = status in ('recente', 'fechamento')
    cls = 'stale' if not valid else ('up' if up else 'down')
    color = '#14dc99' if up else '#ff4d72'
    delta = f'{"▲" if up else "▼"} {pct:+.2f}%' if pct is not None else 'Variação indisponível'
    when = q['time'].strftime('%d/%m %H:%M') if q.get('time') else 'Horário indisponível'
    if q.get('daily_fallback'):
        when = q['time'].strftime('%d/%m') + ' (diária)'
    suffix = (' · ÚLTIMO FECHAMENTO / INFORMATIVO' if status == 'fechamento'
              else '' if status == 'recente' else ' · ATRASADA / NÃO ENTRA NO SCORE')
    price = f'{q["price"]:,.2f}'
    return (f'<div class="asset {cls}"><div class="asset-name">{name}</div><div class="muted">{subtitle}{extra}</div>'
            f'<div class="asset-bottom"><span class="asset-price">{price}</span>'
            f'<span class="{"positive" if up else "negative" if pct is not None else "muted"}">{delta}</span></div>'
            f'{sparkline(q.get("series", []), color)}<div class="tiny">Cotação: {when} BRT{suffix}</div></div>')


@st.fragment(run_every='60s')
def render_dashboard():
    now = datetime.now(BRT)
    with st.spinner('Consultando mercado...'):
        quotes = load_quotes()
    dynamic_weights = load_qqq_weights()
    weights = dynamic_weights or {sym: weight for sym, _, weight in STOCKS}
    score, coverage, groups, mode, details = calc_score(quotes, now, weights)
    classification, status_color = classify(score)
    score_str = f'{score:+d}' if score is not None else '—'
    score_color = ('#a4b6c8' if score is None else
                   '#ff4265' if score <= -20 else
                   '#ffd25b' if score < 20 else '#15d99b')
    score_mode = ('LEITURA COM ÚLTIMOS FECHAMENTOS · INFORMATIVA' if mode == 'fechamento'
                  else 'LEITURA COM COTAÇÕES RECENTES' if mode == 'recente'
                  else 'SEM COBERTURA RECENTE SUFICIENTE')
    st.markdown(f'''<div class="war-panel"><div class="brand">WAR TRADING</div><div class="subbrand">LIVE MARKET 3.0</div>
    <div class="muted">BRASÍLIA · {now.strftime('%d/%m/%Y %H:%M:%S')} · ↻ 60 SEG</div></div>''', unsafe_allow_html=True)
    position = 50 if score is None else max(0, min(100, (score + 100) / 2))
    st.markdown(f'''<div class="summary-grid">
    <div class="war-panel"><div class="section">CONCLUSÃO PARA O MNQ</div>
    <div class="status" style="color:{status_color}">{classification}</div>
    <div class="muted">Leitura intermarket: {score_str}. Cobertura de grupos: {coverage:.0%}.
    {score_mode}. NQ é referência, não soma. Indicador experimental; não é sinal de entrada.</div></div>
    <div class="war-panel"><div class="section">WAR SCORE MNQ</div>
    <div class="status" style="text-align:center;color:{score_color}">{score_str}</div>
    <div class="gauge"><div class="gauge-pin" style="left:{position}%"></div></div>
    <div class="tiny">-100 BAIXA | 0 NEUTRO | +100 ALTA</div></div></div>''', unsafe_allow_html=True)
    st.markdown('<div class="section">RADAR INTERMARKET · 8 ATIVOS</div>', unsafe_allow_html=True)
    st.markdown('<div class="asset-grid">' + ''.join(asset_card(name, desc, quotes.get(sym), sym, now) for name, desc, sym in ASSETS) + '</div>', unsafe_allow_html=True)
    st.markdown('<div class="section">TOP 4 AÇÕES · PESOS DE REFERÊNCIA</div>', unsafe_allow_html=True)
    if dynamic_weights:
        st.caption('Pesos indicativos obtidos do provedor de composição do QQQ (data-base não fornecida pela API). Não presumir atualização em tempo real.')
    else:
        st.caption('Pesos ilustrativos de referência do QQQ em 13/10/2026; consulta dinâmica indisponível. Confirme a composição antes de operar.')
    st.markdown('<div class="asset-grid">' + ''.join(asset_card(sym, company, quotes.get(sym), sym, now, f' · peso ref. {weights[sym]:.2f}%') for sym, company, _ in STOCKS) + '</div>', unsafe_allow_html=True)
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
    audit_html = '<div class="section" style="font-size:14px;margin-top:12px">AUDITORIA DO WAR SCORE</div>'
    audit_html += f'<div class="tiny">Modo: {"FECHAMENTOS / INFORMATIVO" if mode == "fechamento" else "RECENTE"} · Cobertura efetiva: {coverage:.0%} · Mínimo: 75%</div>'
    for group, detail in details.items():
        value = detail['value']
        state = 'INCLUÍDO' if value is not None else 'EXCLUÍDO'
        color = '#14dc99' if value is not None else '#ff4d72'
        contribution = f' · contribuição ponderada: {100 * detail["weight"] * value:+.1f}' if value is not None else ''
        audit_html += (f'<div class="impact"><b>{GROUP_NAMES[group]}</b> · peso {detail["weight"]:.0%} '
                       f'<span style="color:{color}">{state}</span>{contribution}'
                       f'<div class="tiny">Utilizados: {html.escape(", ".join(detail["used"]) or "nenhum")}</div>'
                       f'<div class="tiny">Excluídos: {html.escape("; ".join(detail["excluded"]) or "nenhum")}</div></div>')
    audit_html += '<div class="tiny">Contribuições antes da normalização por cobertura. Com dados faltantes, os pesos válidos são renormalizados. Grupos parcialmente disponíveis usam somente os componentes válidos.</div>'

    news = load_news()
    news_html = ''
    for i, item in enumerate(news, 1):
        title = html.escape(item.get('title_pt', item['title']))
        source = html.escape(item['source'])
        url = html.escape(item['url'], quote=True)
        category = html.escape(item['category'])
        direction = item.get('direction')
        if direction == 'POSITIVO NASDAQ':
            tag = '<span class="positive">POSITIVO NASDAQ (manchete)</span>'
        elif direction == 'NEGATIVO NASDAQ':
            tag = '<span class="negative">NEGATIVO NASDAQ (manchete)</span>'
        else:
            tag = '<span class="tiny">impacto direcional não classificado</span>'
        news_html += (f'<div class="news"><span class="news-num">{i}</span> '
                      f'<span class="news-tag">{category}</span><br>'
                      f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>'
                      f'<div class="tiny">{item["when"].strftime("%d/%m %H:%M")} BRT · {source} · {tag}</div></div>')
    if not news_html:
        news_html = '<div class="tiny">Nenhuma notícia relevante de fonte financeira selecionada encontrada nas últimas 24h. Não exibimos notícias genéricas para preencher espaço.</div>'
    st.markdown(f'<div class="war-panel"><div class="section">MAIORES IMPACTOS NO MNQ</div>{impact_html}{audit_html}<div class="tiny">Grupos agregados para reduzir dupla contagem. Pesos experimentais.</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="war-panel"><div class="section">NOTÍCIAS RELEVANTES · TOP 3 POR PRIORIDADE</div>{news_html}</div>', unsafe_allow_html=True)
    st.markdown('''<div class="war-panel tiny">Cotações: Yahoo Finance (yfinance), sujeitas a atrasos e indisponibilidade. Notícias: Google News RSS, fontes financeiras selecionadas e tradução automática (pode falhar). Direção das notícias: heurística restrita ao movimento explícito descrito na manchete, não é previsão de impacto. Atualização Streamlit a cada 60 segundos enquanto a sessão estiver conectada; fontes possuem cache e atraso próprios. Percentuais contra o último fechamento diário anterior disponível. Fora das sessões de referência, leitura de fechamentos informativa; durante sessões mistas, somente dados recentes entram na pontuação. Horários de feriados e sessões especiais não são validados. Pesos e escala de intensidade são hipóteses não validadas por backtest; o WAR SCORE não é recomendação nem sinal de entrada.</div>''', unsafe_allow_html=True)


render_dashboard()
