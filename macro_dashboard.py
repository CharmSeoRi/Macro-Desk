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

# 커스텀 CSS를 통한 UI 다듬기 (콕핏 스타일)
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        border-radius: 5px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.5);
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #fca311;
        margin-bottom: 20px;
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
    except Exception as e:
        return None

@st.cache_data(ttl=300)
def fetch_yf_history(ticker, period="3mo"):
    """히스토리 데이터를 가져옵니다 (기본 3개월)."""
    try:
        data = yf.Ticker(ticker).history(period=period)
        if not data.empty:
            # DatetimeIndex의 시간대 정보 제거
            data.index = data.index.tz_localize(None)
            return data['Close']
        return pd.Series(dtype=float)
    except Exception as e:
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
    except Exception as e:
        return pd.Series(dtype=float)

@st.cache_data(ttl=300)
def fetch_binance_ticker(symbol):
    """바이낸스 REST API에서 실시간 가격을 가져옵니다."""
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        response = requests.get(url, timeout=5)
        data = response.json()
        return {
            "price": float(data['lastPrice']),
            "pct_change": float(data['priceChangePercent'])
        }
    except Exception as e:
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
    st.sidebar.warning("하단 블록 5(매크로 시스템 리스크)를 로드하려면 FRED API 키가 필요합니다.")
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
        # 소수점 처리 (KRW, JPY는 2자리, 나머지는 4자리)
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

# 6열(Column)로 확장 및 상해종합/코스닥 추가
eq_cols1 = st.columns(6)
indices_row1 = [("S&P 500", "^GSPC"), ("나스닥 100", "^NDX"), ("다우존스", "^DJI"), ("러셀 2000", "^RUT"), ("필라델피아 반도체", "^SOX"), ("유로스톡스 50", "^STOXX50E")]
for i, (name, ticker) in enumerate(indices_row1):
    data = fetch_yf_current(ticker)
    if data:
        eq_cols1[i].metric(label=name, value=f"{data['price']:,.2f}", delta=f"{data['pct_change']:+.2f}%")

# 두 번째 줄을 위한 새로운 6열 생성
eq_cols2 = st.columns(6)
indices_row2 = [("코스피", "^KS11"), ("코스닥", "^KQ11"), ("상해종합", "000001.SS"), ("항셍 지수", "^HSI"), ("항셍 테크", "^HSTECH"), ("닛케이 225", "^N225")]
for i, (name, ticker) in enumerate(indices_row2):
    data = fetch_yf_current(ticker)
    if data:
        eq_cols2[i].metric(label=name, value=f"{data['price']:,.2f}", delta=f"{data['pct_change']:+.2f}%")

st.divider()

# ==========================================
# 4. BLOCK 2: INDEX FUTURES (지수 선물 및 미니 차트)
# ==========================================
st.subheader("📈 블록 2: 주요 지수 선물 (Index Futures)")

# 미니 스파크라인 차트 생성 함수 (스케일링 및 Y축 추가)
def plot_sparkline(ticker, title, period="1mo"):
    hist = fetch_yf_history(ticker, period)
    if hist.empty: return None
    
    color = '#00cc96' if hist.iloc[-1] >= hist.iloc[0] else '#ef553b'
    
    fig = go.Figure(go.Scatter(
        x=hist.index, y=hist.values, mode='lines', 
        line=dict(color=color, width=2)
        # fill='tozeroy' 속성을 제거하여 강제로 0으로 내려가는 현상 방지
    ))
    
    # Y축 타이트 줌 스케일링 설정 (고가와 저가 사이를 타이트하게 잡음)
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
            range=[y_min - padding, y_max + padding] # 동적 범위 설정
        ), 
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        showlegend=False
    )
    return fig

fut_cols = st.columns(4)
futures = [("S&P 500 선물 (ES)", "ES=F"), ("나스닥 100 선물 (NQ)", "NQ=F"), ("다우 선물 (YM)", "YM=F"), ("러셀 2000 선물 (RTY)", "RTY=F")]

for i, (name, ticker) in enumerate(futures):
    data = fetch_yf_current(ticker)
    if data:
        with fut_cols[i]:
            st.metric(label=name, value=f"{data['price']:,.2f}", delta=f"{data['pct_change']:+.2f}%")
            fig = plot_sparkline(ticker, "최근 1개월 추세")
            if fig:
                # config={'displayModeBar': False} 로 불필요한 차트 툴바 숨김
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
            template="plotly_dark", height=150, margin=dict(l=20, r=20, t=40, b=20) # 200 -> 150으로 대폭 축소
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
        # 금리(Yield)의 경우 상승하면 빨간색(부정적/리스크), 하락하면 녹색을 띄게끔 델타 컬러 반전 적용
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

# 원자재 가격 메트릭 
st.markdown("##### 1) 핵심 원자재 선물 실시간 가격")
comm_cols = st.columns(5)
comm_assets = [
    ("WTI 원유", "CL=F", "$"), ("브렌트유", "BZ=F", "$"), 
    ("금 (Gold)", "GC=F", "$"), ("은 (Silver)", "SI=F", "$"), 
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

st.write("") # 간격 띄우기

# 스프레드 및 낙수효과 차트
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
            template="plotly_dark", height=150, margin=dict(l=20, r=40, t=40, b=20) # 높이를 150으로 축소
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
            template="plotly_dark", height=150, margin=dict(l=20, r=40, t=40, b=20) # 높이를 150으로 축소
        )
        st.plotly_chart(fig_metals, use_container_width=True)

st.divider()

# ==========================================
# 8. BLOCK 6: CRYPTO STRESS & DIVERGENCE
# ==========================================
st.subheader("₿ 블록 6: 암호화폐 스트레스 및 테더(USDT) 프리미엄")

col4_1, col4_2 = st.columns([1, 2])

with col4_1:
    btc_yf = fetch_yf_current("BTC-USD")
    btc_binance = fetch_binance_ticker("BTCUSDT")
    
    if btc_yf and btc_binance:
        spot_price = btc_yf['price']
        tether_price = btc_binance['price']
        divergence = ((tether_price - spot_price) / spot_price) * 100
        
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=divergence,
            title={'text': "BTCUSDT vs BTC-USD 갭 (%)", 'font': {'size': 14}},
            gauge={
                'axis': {'range': [-1, 1]},
                'bar': {'color': "#fca311", 'thickness': 0.7}, # 두께를 0.3에서 0.7로 키워 시인성 압도적 상향
                'steps': [
                    {'range': [-1, -0.2], 'color': "#ef553b"}, 
                    {'range': [-0.2, 0.2], 'color': "rgba(255,255,255,0.05)"}, 
                    {'range': [0.2, 1], 'color': "#00cc96"}  
                ]
            }
        ))
        fig_gauge.update_layout(template="plotly_dark", height=250, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)
    else:
        st.info("비트코인 괴리율 데이터를 불러오지 못했습니다.")

with col4_2:
    st.markdown("<br>", unsafe_allow_html=True) # 줄맞춤용
    crypto_cols = st.columns(3)
    cryptos = [("비트코인", "BTCUSDT"), ("이더리움", "ETHUSDT"), ("솔라나", "SOLUSDT")]
    
    for i, (name, symbol) in enumerate(cryptos):
        data = fetch_binance_ticker(symbol)
        if data:
            crypto_cols[i].metric(
                label=f"{name} ({symbol})", 
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