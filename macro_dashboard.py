import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from fredapi import Fred
import requests
from datetime import datetime, timedelta

# 페이지 기본 설정 (와이드 모드, 다크 테마 지향)
st.set_page_config(
    page_title="글로벌 매크로 FICC 대시보드",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 CSS를 통한 UI 다듬기 (모바일 반응형 및 다크 콕핏 스타일)
st.markdown("""
<style>
    /* 기본 여백 및 헤더 최적화 */
    .block-container {
        padding-top: 1.8rem !important;
        padding-bottom: 2.5rem !important;
    }
    .main-header {
        font-size: clamp(1.4rem, 4vw, 2.2rem);
        font-weight: 700;
        color: #fca311;
        margin-bottom: 15px;
        letter-spacing: -0.5px;
    }
    /* 메트릭 카드 전용 스타일 (FICC 단말기 느낌) */
    [data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.05); /* 라이트/다크 모드 범용 반투명 배경 */
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 8px;
        padding: 10px 14px;0
        box-shadow: none; 
        transition: all 0.2s ease-in-out;
    }
    [data-testid="stMetric"]:hover {
        border-color: #fca311;
        background-color: rgba(128, 128, 128, 0.1);
    }
    [data-testid="stMetricLabel"] {
        font-size: clamp(0.72rem, 2vw, 0.85rem) !important;
        font-weight: 600 !important;
        /* 색상 강제 지정 제거 - 테마 자동 적응 */
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    [data-testid="stMetricValue"] {
        font-size: clamp(1.05rem, 2.8vw, 1.45rem) !important;
        font-weight: 700 !important;
        /* 색상 강제 지정 제거 - 테마 자동 적응 */
    }
    /* 등락률(Delta) 가독성 극대화 */
    [data-testid="stMetricDelta"] div {
        font-weight: 800 !important; 
        font-size: clamp(0.75rem, 2vw, 0.85rem) !important;
    }

    /* 📱 모바일 화면 (폭 768px 이하) 전용 반응형 그리드 */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 1.0rem !important;
        }
        /* 컬럼들이 가로로 찌그러지지 않고 모바일 2열 카드로 자동 배치 */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 8px !important;
        }
        [data-testid="column"] {
            min-width: calc(50% - 6px) !important;
            flex: 1 1 calc(50% - 6px) !important;
            padding: 0 !important;
        }
        /* 차트 컨테이너는 모바일에서 100% 전폭 사용 */
        .stPlotlyChart {
            min-width: 100% !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 1. DATA FETCHING FUNCTIONS (Cached & Robust)
# ==========================================
@st.cache_data(ttl=300)
def fetch_yf_current(ticker):
    """단일 티커의 현재 가격 및 전일 대비 변동 데이터를 가져옵니다."""
    try:
        data = yf.Ticker(ticker).history(period="2d")
        if len(data) >= 2:
            current = data['Close'].iloc[-1]
            prev = data['Close'].iloc[-2]
            pct_change = ((current - prev) / prev) * 100
            diff = current - prev
            return {"price": current, "diff": diff, "pct_change": pct_change}
        elif len(data) == 1:
            return {"price": data['Close'].iloc[0], "diff": 0.0, "pct_change": 0.0}
        return None
    except Exception:
        return None

@st.cache_data(ttl=300)
def fetch_yf_history(ticker, period="3mo"):
    """히스토리 데이터를 가져옵니다 (기본 3개월)."""
    try:
        data = yf.Ticker(ticker).history(period=period)
        if not data.empty:
            data.index = data.index.tz_localize(None)
            return data['Close']
        return pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=300)
def fetch_fred_series(api_key, series_id, days=365):
    """FRED 데이터를 가져옵니다."""
    if not api_key:
        return pd.Series(dtype=float)
    try:
        fred = Fred(api_key=api_key)
        start_date = (datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')
        data = fred.get_series(series_id, observation_start=start_date)
        return data
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=300)
def fetch_crypto_ticker(symbol_binance, symbol_yf):
    """
    암호화폐 시세를 다중 백엔드(Binance Vision / Binance US / yfinance)로 수집합니다.
    AWS 미국 클라우드 서버의 지역 차단(HTTP 451)을 우회합니다.
    """
    # 1차 시도: Binance Public Data Vision (공용 마켓 데이터 전용 미러)
    try:
        url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={symbol_binance}"
        resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            if 'lastPrice' in data and 'priceChangePercent' in data:
                return {
                    "price": float(data['lastPrice']),
                    "pct_change": float(data['priceChangePercent'])
                }
    except Exception:
        pass

    # 2차 시도: Binance US API
    try:
        url = f"https://api.binance.us/api/v3/ticker/24hr?symbol={symbol_binance}"
        resp = requests.get(url, timeout=3, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            if 'lastPrice' in data and 'priceChangePercent' in data:
                return {
                    "price": float(data['lastPrice']),
                    "pct_change": float(data['priceChangePercent'])
                }
    except Exception:
        pass

    # 3차 백업: yfinance
    try:
        yf_data = fetch_yf_current(symbol_yf)
        if yf_data:
            return {
                "price": yf_data['price'],
                "pct_change": yf_data['pct_change']
            }
    except Exception:
        pass

    return None

# ==========================================
# 2. SIDEBAR & HEADER (FX & DXY)
# ==========================================
st.sidebar.title("⚙️ 데스크 설정")

default_api_key = ""
try:
    if "FRED_API_KEY" in st.secrets:
        default_api_key = st.secrets["FRED_API_KEY"]
except Exception:
    pass

fred_api_key = st.sidebar.text_input(
    "FRED API Key", 
    value=default_api_key, 
    type="password", 
    help="거시경제 데이터를 불러오려면 FRED API 키를 입력하세요."
)

if not fred_api_key:
    st.sidebar.warning("하단 블록 7(매크로 시스템 리스크)을 로드하려면 FRED API 키가 필요합니다.")
st.sidebar.markdown("---")
st.sidebar.info("⏱️ API 트래픽 제한을 방지하기 위해 데이터는 5분 단위로 자동 캐싱됩니다.")

# 최상단 헤더: 주요 환율 및 달러 인덱스
st.markdown('<div class="main-header">글로벌 매크로 대시보드</div>', unsafe_allow_html=True)

fx_cols = st.columns(5)
fx_tickers = [
    ("달러 인덱스 (DXY)", "DX-Y.NYB", ""),
    ("원/달러 (USD/KRW)", "KRW=X", "₩"),
    ("유로/달러 (EUR/USD)", "EURUSD=X", "$"),
    ("엔/달러 (USD/JPY)", "JPY=X", "¥"),
    ("위안/달러 (USD/CNY)", "CNY=X", "¥")
]

for i, (name, ticker, symbol) in enumerate(fx_tickers):
    data = fetch_yf_current(ticker)
    if data:
        decimals = 2 if "KRW" in ticker or "JPY" in ticker else 4
        price_str = f"{symbol}{data['price']:,.{decimals}f}"
        fx_cols[i].metric(
            label=name, 
            value=price_str, 
            delta=f"{data['pct_change']:+.2f}%"
        )
st.divider()

# ==========================================
# 3. BLOCK 1: GLOBAL EQUITIES (글로벌 주가지수)
# ==========================================
st.subheader("🌎 블록 1: 글로벌 핵심 주가지수")

all_indices = [
    ("S&P 500", "^GSPC"), 
    ("나스닥 100", "^NDX"), 
    ("다우존스", "^DJI"), 
    ("러셀 2000", "^RUT"), 
    ("필라델피아 반도체", "^SOX"), 
    ("유로스톡스 50", "^STOXX50E"),
    ("코스피", "^KS11"), 
    ("코스닥", "^KQ11"), 
    ("상해종합", "000001.SS"), 
    ("항셍 지수", "^HSI"), 
    ("항셍 테크", "^HSTECH"), 
    ("닛케이 225", "^N225")
]

# API 호출에 성공한 데이터만 순서대로 수집 (이빨 빠짐 방지)
valid_indices = []
for name, ticker in all_indices:
    data = fetch_yf_current(ticker)
    if data:
        valid_indices.append((name, data))

# 6개씩 묶어서 빈칸 없이 차례대로 화면에 렌더링
for i in range(0, len(valid_indices), 6):
    cols = st.columns(6)
    chunk = valid_indices[i:i+6]
    for j, (name, data) in enumerate(chunk):
        cols[j].metric(label=name, value=f"{data['price']:,.2f}", delta=f"{data['pct_change']:+.2f}%")

st.divider()

# ==========================================
# 4. BLOCK 2: INDEX FUTURES (지수 선물 및 미니 차트)
# ==========================================
st.subheader("📈 블록 2: 주요 지수 선물 (Index Futures)")

def plot_sparkline(ticker, title, period="1mo"):
    hist = fetch_yf_history(ticker, period)
    if hist.empty:
        return None
    
    color = '#00cc96' if hist.iloc[-1] >= hist.iloc[0] else '#ef553b'
    
    fig = go.Figure(go.Scatter(
        x=hist.index, y=hist.values, mode='lines', 
        line=dict(color=color, width=2)
    ))
    
    y_min, y_max = hist.min(), hist.max()
    padding = (y_max - y_min) * 0.1
    
    fig.update_layout(
        title=dict(text=title, font=dict(size=12, color='gray')),
        height=140, 
        margin=dict(l=0, r=40, t=25, b=0), 
        xaxis=dict(visible=False),
        yaxis=dict(
            visible=True, side='right', showgrid=True, 
            gridcolor='rgba(255,255,255,0.1)', 
            tickfont=dict(size=10, color='gray'),
            range=[y_min - padding, y_max + padding]
        ), 
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False
    )
    return fig

fut_cols = st.columns(4)
futures = [
    ("S&P 500 선물 (ES)", "ES=F"), 
    ("나스닥 100 선물 (NQ)", "NQ=F"), 
    ("다우 선물 (YM)", "YM=F"), 
    ("러셀 2000 선물 (RTY)", "RTY=F")
]

for i, (name, ticker) in enumerate(futures):
    data = fetch_yf_current(ticker)
    if data:
        with fut_cols[i]:
            st.metric(label=name, value=f"{data['price']:,.2f}", delta=f"{data['pct_change']:+.2f}%")
            fig = plot_sparkline(ticker, "최근 1개월 추세")
            if fig:
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

st.divider()

# ==========================================
# 5. BLOCK 3: BASIS MONITOR (현선물 베이시스)
# ==========================================
st.subheader("📉 블록 3: 현선물 베이시스 모니터 (선물 - 현물)")

col2_1, col2_2 = st.columns(2)

def plot_basis(spot_ticker, fut_ticker, title):
    spot_hist = fetch_yf_history(spot_ticker, "1mo")
    fut_hist = fetch_yf_history(fut_ticker, "1mo")
    
    if not spot_hist.empty and not fut_hist.empty:
        df = pd.concat([spot_hist, fut_hist], axis=1).dropna()
        df.columns = ['Spot', 'Futures']
        df['Basis'] = df['Futures'] - df['Spot']
        
        colors = ['#00cc96' if val >= 0 else '#ef553b' for val in df['Basis']]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df.index, y=df['Basis'], marker_color=colors, name="Basis"))
        fig.update_layout(
            title=f"{title} 베이시스 (현재: {df['Basis'].iloc[-1]:.2f})",
            template="plotly_dark", height=150, margin=dict(l=20, r=20, t=40, b=20)
        )
        return fig
    return None

with col2_1:
    fig_spx = plot_basis("^GSPC", "ES=F", "S&P 500 (선물 ES - 현물 SPX)")
    if fig_spx:
        st.plotly_chart(fig_spx, use_container_width=True)

with col2_2:
    fig_ndx = plot_basis("^NDX", "NQ=F", "나스닥 100 (선물 NQ - 현물 NDX)")
    if fig_ndx:
        st.plotly_chart(fig_ndx, use_container_width=True)

st.divider()

# ==========================================
# 6. BLOCK 4: BONDS & YIELDS (국채 및 금리)
# ==========================================
st.subheader("🏛️ 블록 4: 글로벌 국채 금리 및 T-Note 선물")

bond_cols = st.columns(5)
bonds_assets = [
    ("미 10년물 국채 금리", "^TNX", "%"), 
    ("미 30년물 국채 금리", "^TYX", "%"), 
    ("미 10년물 국채 선물 (ZN)", "ZN=F", "$"), 
    ("미 5년물 국채 선물 (ZF)", "ZF=F", "$"), 
    ("미 2년물 국채 선물 (ZT)", "ZT=F", "$")
]

for i, (name, ticker, symbol) in enumerate(bonds_assets):
    data = fetch_yf_current(ticker)
    if data:
        color_logic = "inverse" if "금리" in name else "normal"
        bond_cols[i].metric(
            label=name, 
            value=f"{symbol}{data['price']:,.2f}" if symbol == "$" else f"{data['price']:,.2f}{symbol}", 
            delta=f"{data['pct_change']:+.2f}%",
            delta_color=color_logic
        )

st.divider()

# ==========================================
# 7. BLOCK 5: COMMODITIES & SPILLOVER (원자재 및 스프레드)
# ==========================================
st.subheader("🛢️ 블록 5: 핵심 원자재 및 섹터 스프레드")

st.markdown("##### 1) 핵심 원자재 선물 실시간 가격")
comm_cols = st.columns(5)
comm_assets = [
    ("WTI 원유", "CL=F", "$"), 
    ("브렌트유", "BZ=F", "$"), 
    ("금 (Gold)", "GC=F", "$"), 
    ("은 (Silver)", "SI=F", "$"), 
    ("구리 (Copper)", "HG=F", "$")
]

for i, (name, ticker, symbol) in enumerate(comm_assets):
    data = fetch_yf_current(ticker)
    if data:
        comm_cols[i].metric(
            label=name, 
            value=f"{symbol}{data['price']:,.2f}", 
            delta=f"{data['pct_change']:+.2f}%"
        )

st.write("")

st.markdown("##### 2) 원자재 스프레드 및 상대가치 비율")
col3_1, col3_2 = st.columns(2)

with col3_1:
    bz = fetch_yf_history("BZ=F", "3mo")
    cl = fetch_yf_history("CL=F", "3mo")
    if not bz.empty and not cl.empty:
        energy_spread = (bz - cl).dropna()
        fig_eng = go.Figure()
        fig_eng.add_trace(go.Scatter(
            x=energy_spread.index, y=energy_spread.values, mode='lines', 
            name="Brent-WTI", line=dict(color='#ab63fa', width=2)
        ))
        fig_eng.add_hline(y=energy_spread.mean(), line_dash="dot", line_color="gray", annotation_text="3개월 평균선")
        fig_eng.update_layout(
            title=f"에너지 스프레드: 브렌트유 - WTI (현재: ${energy_spread.iloc[-1]:.2f})",
            template="plotly_dark", height=150, margin=dict(l=20, r=40, t=40, b=20)
        )
        st.plotly_chart(fig_eng, use_container_width=True)

with col3_2:
    gc = fetch_yf_history("GC=F", "6mo")
    pa = fetch_yf_history("PA=F", "6mo")
    if not gc.empty and not pa.empty:
        ratio = (gc / pa).dropna()
        ma60 = ratio.rolling(window=60).mean()
        fig_metals = go.Figure()
        fig_metals.add_trace(go.Scatter(x=ratio.index, y=ratio.values, mode='lines', name="금/팔라듐 비율", line=dict(color='#ffd700')))
        fig_metals.add_trace(go.Scatter(x=ma60.index, y=ma60.values, mode='lines', name="60일 이동평균", line=dict(color='white', dash='dash')))
        fig_metals.update_layout(
            title=f"귀금속 낙수효과: 금 / 팔라듐 비율 (현재: {ratio.iloc[-1]:.2f})",
            template="plotly_dark", height=150, margin=dict(l=20, r=40, t=40, b=20)
        )
        st.plotly_chart(fig_metals, use_container_width=True)

st.divider()

# ==========================================
# 8. BLOCK 6: CRYPTO STRESS & DIVERGENCE
# ==========================================
st.subheader("₿ 블록 6: 암호화폐 스트레스 및 테더(USDT) 프리미엄")

col4_1, col4_2 = st.columns([1.2, 2])

with col4_1:
    btc_spot = fetch_yf_current("BTC-USD")
    btc_usdt = fetch_crypto_ticker("BTCUSDT", "BTC-USD")
    usdt_peg = fetch_yf_current("USDT-USD")
    
    divergence = None
    if btc_spot and btc_usdt and btc_spot['price'] > 0:
        divergence = ((btc_usdt['price'] - btc_spot['price']) / btc_spot['price']) * 100
    elif usdt_peg and usdt_peg['price'] > 0:
        divergence = (usdt_peg['price'] - 1.0) * 100

    if divergence is not None:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=divergence,
            number={'suffix': "%", 'valueformat': "+.3f", 'font': {'size': 20, 'color': '#fca311'}},
            title={'text': "USDT 테더 괴리율 / 프리미엄", 'font': {'size': 13, 'color': '#94a3b8'}},
            gauge={
                'axis': {'range': [-1, 1], 'tickwidth': 1, 'tickcolor': "gray"},
                'bar': {'color': "#fca311", 'thickness': 0.7},
                'steps': [
                    {'range': [-1, -0.2], 'color': "#ef553b"}, 
                    {'range': [-0.2, 0.2], 'color': "rgba(255,255,255,0.08)"}, 
                    {'range': [0.2, 1], 'color': "#00cc96"}  
                ]
            }
        ))
        fig_gauge.update_layout(
            template="plotly_dark", 
            height=180, 
            margin=dict(l=15, r=15, t=25, b=15)
        )
        st.plotly_chart(fig_gauge, use_container_width=True, config={'displayModeBar': False, 'responsive': True})
    else:
        st.info("암호화폐 괴리율 지표를 산출 중입니다.")

with col4_2:
    crypto_cols = st.columns(3)
    cryptos = [
        ("비트코인", "BTCUSDT", "BTC-USD"), 
        ("이더리움", "ETHUSDT", "ETH-USD"), 
        ("솔라나", "SOLUSDT", "SOL-USD")
    ]
    
    for i, (name, symbol_binance, symbol_yf) in enumerate(cryptos):
        data = fetch_crypto_ticker(symbol_binance, symbol_yf)
        if data:
            crypto_cols[i].metric(
                label=f"{name} ({symbol_yf.replace('-USD','')})", 
                value=f"${data['price']:,.2f}", 
                delta=f"{data['pct_change']:+.2f}%"
            )

st.divider()

# ==========================================
# 9. BLOCK 7: MACRO TRIGGERS (시스템 리스크)
# ==========================================
st.subheader("🚨 블록 7: 매크로 시스템 리스크 및 이상 변동성 모니터")

col5_1, col5_2, col5_3 = st.columns([1.5, 1.5, 1])

with col5_1:
    hy_spread = fetch_fred_series(fred_api_key, "BAMLH0A0HYM2", days=365)
    if not hy_spread.empty:
        current_hy = hy_spread.iloc[-1]
        fig_hy = go.Figure()
        
        fig_hy.add_trace(go.Scatter(
            x=hy_spread.index, y=hy_spread.values, mode='lines', 
            name="HY Spread", line=dict(color='#00cc96', width=2)
        ))
        fig_hy.add_hline(y=5.0, line_dash="dash", line_color="red", annotation_text="위험 경계선 (5.0%)")
        fig_hy.update_layout(
            title=f"미국 하이일드 스프레드 (현재: {current_hy:.2f}%)", 
            template="plotly_dark", height=300, margin=dict(l=20, r=20, t=40, b=20)
        )
        if current_hy >= 5.0:
            st.error(f"⚠️ 하이일드 스프레드 경고: {current_hy:.2f}%")
        st.plotly_chart(fig_hy, use_container_width=True)
    else:
        st.info("FRED API 키가 필요합니다.")

with col5_2:
    dgs10 = fetch_fred_series(fred_api_key, "DGS10", days=365)
    dgs2 = fetch_fred_series(fred_api_key, "DGS2", days=365)
    
    if not dgs10.empty and not dgs2.empty:
        spread_10_2 = (dgs10 - dgs2).dropna()
        current_spread = spread_10_2.iloc[-1]
        
        fig_yield = go.Figure()
        fig_yield.add_trace(go.Scatter(
            x=spread_10_2.index, y=spread_10_2.values, mode='lines', 
            name="10Y-2Y", line=dict(color='#636efa', width=2), fill='tozeroy'
        ))
        fig_yield.add_hline(y=0.0, line_width=2, line_color="white", annotation_text="역전 기준선")
        fig_yield.update_layout(
            title=f"미국 장단기 금리차 10Y-2Y (현재: {current_spread:.2f}%)", 
            template="plotly_dark", height=300, margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig_yield, use_container_width=True)
    else:
        st.info("FRED API 키가 필요합니다.")

with col5_3:
    st.markdown("##### VIX 및 이상 변동성 지표")
    vix = fetch_yf_current("^VIX")
    vix1d = fetch_yf_current("^VIX1D")
    skew = fetch_yf_current("^SKEW")
    
    if vix:
        st.metric(label="VIX (30일 변동성)", value=f"{vix['price']:.2f}", delta=f"{vix['pct_change']:+.2f}%", delta_color="inverse")
    if vix1d:
        st.metric(label="VIX1D (1일 당일 변동성)", value=f"{vix1d['price']:.2f}", delta=f"{vix1d['pct_change']:+.2f}%", delta_color="inverse")
    if skew:
        st.metric(label="SKEW (블랙스완 방어 비용)", value=f"{skew['price']:.2f}", delta=f"{skew['pct_change']:+.2f}%", delta_color="inverse")

st.caption("🚀 데이터 소스: yfinance, FRED, Binance REST API | 1인 FICC 데스크 전용")
