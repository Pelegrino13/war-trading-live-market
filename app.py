import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
import math

st.set_page_config(page_title='WAR TRADING | LIVE MARKET 2.0', page_icon='⚔️', layout='wide', initial_sidebar_state='collapsed')
TZ = ZoneInfo('America/Sao_Paulo')
ASSETS = [
 ('NQ','Nasdaq Futuro','NQ=F',0.0),
 ('ES','S&P 500 Futuro','ES=F',0.30),
 ('DXY','Índice do Dólar','DX-Y.NYB',-0.20),
 ('VIX','Volatilidade','^VIX',-0.25),
 ('US10Y','Treasury 10 anos','^TNX',-0.20),
 ('CL','Petróleo WTI','CL=F',-0.03),
 ('GC','Ouro','GC=F',-0.02),
 ('FERRO','Minério de Ferro','',0.0),
]

st.markdown('''<style>
.stApp {background:#061321;color:#eaf4ff}
.block-container {max-width:1200px;padding:0.65rem 0.65rem 2rem}
header[data-testid="stHeader"] {background:transparent}
.war-head {border:1px solid #18547a;border-radius:12px;padding:12px 15px;background:linear-gradient(110deg,#081725,#0b253b);display:flex;justify-content:space-between;align-items:center;gap:8px}
.brand {font-weight:900;font-size:clamp(20px,4vw,34px);letter-spacing:1px;color:#41baff}
.sub {color:#9ac8e9;font-size:12px;letter-spacing:3px}
.meta {color:#a9c4da;font-size:12px;text-align:right}
.war-card {background:#091c2d;border:1px solid #155076;border-radius:10px;padding:12px;margin:6px 0;min-height:126px}
.code {color:#45baff;font-size:19px;font-weight:800}
.name {font-size:11px;color:#a6c0d3}
.price {font-size:clamp(18px,3vw,27px);font-weight:800;margin-top:7px}
.up {color:#29dca1}.down {color:#ff5669}.flat {color:#ffd15b}
.change {font-weight:800;font-size:18px}.muted {color:#8faac0;font-size:11px}
.panel {background:#091c2d;border:1px solid #155076;border-radius:10px;padding:12px;margin:7px 0}
.panel-title {color:#45baff;font-weight:800;font-size:14px;margin-bottom:8px}
.signal {font-weight:900;font-size:clamp(21px,4vw,33px)}
.score {font-weight:900;font-size:clamp(35px,7vw,58px);line-height:1.1}
.bar {height:12px;border-radius:9px;background:linear-gradient(90deg,#e64156,#f4b942,#efd95d,#39cf8d,#08a975);position:relative;margin:15px 0 8px}
.needle {position:absolute;top:-5px;width:3px;height:22px;background:white;box-shadow:0 0 5px white}
.small {font-size:12px;color:#c5d6e5}
.stButton button {border:1px solid #1977a4;background:#0b2940;color:#d9f4ff}
@media(max-width:600px){.block-container{padding:0.45rem}.war-card{padding:9px;min-height:118px}.brand{font-size:22px}.price{font-size:19px}.change{font-size:16px}.panel{padding:10px}}
</style>''', unsafe_allow_html=True)

@st.cache_data(ttl=60,show_spinner=False)
def load_quotes():
    output={}
    for code,name,ticker,weight in ASSETS:
        if not ticker:
            output[code]={'error':'Fonte não configurada'}
            continue
        try:
            obj=yf.Ticker(ticker)
            hist=obj.history(period='7d',interval='1d',auto_adjust=False)
            hist=hist.dropna(subset=['Close'])
            if len(hist)<2:
                output[code]={'error':'Histórico insuficiente'}
                continue
            prev=float(hist['Close'].iloc[-2]); daily=float(hist['Close'].iloc[-1])
            if prev<=0 or not math.isfinite(daily):
                output[code]={'error':'Preço inválido'}
                continue
            # Intraday last price when available; fallback to last daily close.
            intr=obj.history(period='1d',interval='1m',auto_adjust=False)
            intr=intr.dropna(subset=['Close'])
            if not intr.empty:
                price=float(intr['Close'].iloc[-1]); stamp=intr.index[-1]
            else:
                price=daily;stamp=hist.index[-1]
            if stamp.tzinfo is None: stamp=stamp.tz_localize('UTC')
            stamp=stamp.tz_convert(TZ)
            # Daily history last row is current trading day if the session has started.
            # If latest intraday date differs from daily date, do not assume the baseline.
            daily_day=hist.index[-1].date()
            if stamp.date()!=daily_day:
                price=daily; stamp=hist.index[-1].tz_convert(TZ) if hist.index[-1].tzinfo else hist.index[-1].tz_localize('UTC').tz_convert(TZ)
            pct=(price/prev-1)*100
            output[code]={'price':price,'pct':pct,'stamp':stamp.strftime('%d/%m %H:%M'),'weight':weight}
        except Exception:
            output[code]={'error':'Fonte indisponível'}
    return output

now=datetime.now(TZ)
st.markdown(f'''<div class="war-head"><div><div class="brand">⚔️ WAR TRADING</div><div class="sub">LIVE MARKET 2.0</div></div><div class="meta">BRASÍLIA<br>{now:%d/%m/%Y %H:%M:%S}<br>↻ 60 SEG</div></div>''',unsafe_allow_html=True)

# The fragment refreshes every 60 seconds while the app is open and active.
@st.fragment(run_every='60s')
def dashboard():
    quotes=load_quotes()
    valid=[(c,quotes[c]) for c,_,_,w in ASSETS if w!=0 and 'pct' in quotes[c]]
    coverage=sum(abs(x['weight']) for _,x in valid)
    # Saturation at +/- 2% daily move, weighted by expected relationship to MNQ.
    score=None
    if coverage>=0.75:
        score=round(sum(max(-1,min(1,x['pct']/2.0))*x['weight']*100 for _,x in valid)/coverage)
        score=max(-100,min(100,score))
    if score is None: label='DADOS INSUFICIENTES'; css='flat'
    elif score<=-60: label='BAIXA FORTE';css='down'
    elif score<=-20: label='BAIXA MODERADA';css='down'
    elif score<=19: label='LATERALIZAÇÃO';css='flat'
    elif score<=59: label='ALTA MODERADA';css='up'
    else: label='ALTA FORTE';css='up'
    contributors=[]
    for code,x in valid:
        effect=x['pct']*x['weight']
        if abs(effect)>0.0001:
            contributors.append((abs(effect),code,'favorável' if effect>0 else 'contrário',x['pct']))
    contributors.sort(reverse=True)
    leaders=contributors[:4]
    if score is None: summary='Aguardando cobertura suficiente das fontes para produzir uma leitura consolidada.'
    elif leaders:
        reasons=', '.join(f'{c} ({"alta" if p>0 else "baixa"} {abs(p):.2f}%, impacto {e})' for _,c,e,p in leaders)
        summary=f'Leitura intermarket: {label.lower()} ({score:+d}). Principais fatores: {reasons}. Esta é uma medida de pressão, não um sinal de entrada.'
    else: summary='Sem movimentos relevantes detectados nos ativos disponíveis.'
    a,b=st.columns([1.1,1])
    with a:
        st.markdown(f'<div class="panel"><div class="panel-title">CONCLUSÃO PARA O MNQ</div><div class="signal {css}">{label}</div><div class="small">{summary}</div></div>',unsafe_allow_html=True)
    with b:
        if score is None: indicator='<div class="muted">Sem pontuação</div>'
        else:
            pos=(score+100)/2
            indicator=f'<div class="score {css}">{score:+d}</div><div class="bar"><div class="needle" style="left:{pos}%"></div></div><div class="muted">-100 BAIXA &nbsp; | &nbsp; 0 NEUTRO &nbsp; | &nbsp; +100 ALTA</div>'
        st.markdown(f'<div class="panel"><div class="panel-title">WAR SCORE MNQ</div>{indicator}</div>',unsafe_allow_html=True)
    st.markdown('<div class="panel-title" style="margin:10px 0 2px">RADAR DE MERCADO</div>',unsafe_allow_html=True)
    for start in range(0,len(ASSETS),2):
        c1,c2=st.columns(2)
        for col,(code,name,ticker,weight) in zip((c1,c2),ASSETS[start:start+2]):
            x=quotes[code]
            with col:
                if 'pct' in x:
                    css2='up' if x['pct']>0.02 else 'down' if x['pct']< -0.02 else 'flat'
                    arrow='▲' if x['pct']>0.02 else '▼' if x['pct']< -0.02 else '▬'
                    content=f'<div class="price">{x["price"]:,.2f}</div><div class="change {css2}">{arrow} {x["pct"]:+.2f}%</div><div class="muted">Cotação: {x["stamp"]} BRT</div>'
                else:
                    content=f'<div class="price muted">Indisponível</div><div class="muted">{x["error"]}</div>'
                st.markdown(f'<div class="war-card"><div class="code">{code}</div><div class="name">{name}</div>{content}</div>',unsafe_allow_html=True)
    st.markdown('<div class="panel-title">MAIORES IMPACTOS ESTIMADOS NO MNQ</div>',unsafe_allow_html=True)
    if leaders:
        for _,code,effect,pct in leaders:
            color='up' if effect=='favorável' else 'down'
            st.markdown(f'<div class="panel" style="margin:3px 0;padding:8px"><b>{code}</b> &nbsp; <span class="{color}">{effect.upper()}</span> &nbsp; <span class="small">Variação do ativo: {pct:+.2f}%</span></div>',unsafe_allow_html=True)
    else: st.info('Aguardando dados para calcular impactos.')
    st.markdown('<div class="muted">Pesos ilustrativos de pesquisa: ES 30%, DXY 20%, VIX 25%, US10Y 20%, CL 3%, GC 2%. Variação normalizada por ±2% (parâmetro inicial). NQ é referência, não soma no score. FERRO não soma até haver fonte confiável. Relações mudam conforme o regime de mercado.</div>',unsafe_allow_html=True)
    st.caption('Dados: Yahoo Finance (yfinance). Podem estar atrasados. O painel atualiza a cada 60 s enquanto aberto; a fonte pode atualizar menos frequentemente. Notícias ainda não integradas.')

dashboard()
