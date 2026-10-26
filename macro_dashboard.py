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

# 커스텀 CSS를 통한 UI 다듬기 (태블릿 세로 및 모바일 반응형 완벽 대응)
st.markdown("""
<style>
    /* 기본 여백 및 헤더 최적화 */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2.5rem !important;
    }
    .main-header {
        font-size: clamp(1.3rem, 3.5vw, 2.2rem);
        font-weight: 700;
        color: #fca311;
        margin-bottom: 12px;
        letter-spacing: -0.5px;
    }
    /* 메트릭 카드 전용 스타일 */
    [data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 8px;
        padding: 8px 12px;
        box-shadow: none; 
        transition: all 0.2s ease-in-out;
        width: 100% !important;
        box-sizing: border-box !important;
    }
    [data-testid="stMetric"]:hover {
        border-color: #fca311;
        background-color: rgba(128, 128, 128, 0.1);
    }
    [data-testid="stMetricLabel"] {
        font-size: clamp(0.72rem, 1.8vw, 0.85rem) !important;
        font-weight: 600 !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    [data-testid="stMetricValue"] {
        font-size: clamp(0.95rem, 2.4vw, 1.35rem) !important;
        font-weight: 700 !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    [data-testid="stMetricDelta"] div {
        font-weight: 800 !important; 
        font-size: clamp(0.72rem, 1.8vw, 0.82rem) !important;
    }

    /* 📱 모바일 및 📟 태블릿 세로 모드 반응형 그리드 */
    @media (min-width: 769px) and (max-width: 1024px) {
        .block-container {
            padding-left: 1.2rem !important;
            padding-right: 1.2rem !important;
        }
        [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 10px !important;
        }
        [data-testid="column"] {
            min-width: calc(33.333% - 10px) !important;
            flex: 1 1 calc(33.333% - 10px) !important;
            padding: 0 !important;
        }
    }

    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 0.8rem !important;
        }
        [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 8px !important;
        }
        [data-testid="column"] {
            min-width: calc(50% - 6px) !important;
            flex: 1 1 calc(50% - 6px) !important;
            padding: 0 !important;
        }
        .stPlotlyChart {
            min-width: 100% !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# 모바일 터치 스크롤 방해 금지 Plotly 전역 설정 딕셔너리
TOUCH_SAFE_CONFIG = {
    'displayModeBar': False,
    'scrollZoom': False,
    'doubleClick': False,
    'showAxisDragHandles': False,
    'responsive': True
}

# 정밀 분석을 위해 줌/툴바를 지원하는 인터랙티브 차트 설정
MACRO_CHART_CONFIG = {
    'displayModeBar': True,
    'scrollZoom': False,
    'displaylogo': False,
    'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
    'responsive': True
}

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
    """히스토리 데이터를 가져옵니다."""
    try:
        data = yf.Ticker(ticker).history(period=period)
        if not data.empty:
            data.index = data.index.tz_localize(None)
            return data['Close']
        return pd.Series(dtype=float)
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=300)
def fetch_fred_series(api_key, series_id, days=1825):
    """FRED 데이터를 가져옵니다."""
    if not api_key:
        return pd.Series(dtype=float)
    try:
        fred = Fred(api_key=api_key)
        start_date = (datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')
        data = fred.get_series(series_id, observation_start=start_date)
        return data.dropna()
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=600)
def fetch_fed_net_liquidity(api_key, days=1095):
    """연준 순유동성(Fed Net Liquidity)을 산출합니다.
    - WALCL (총자산, $Millions)
    - WTREGEN (재무부 TGA 잔고, $Millions)
    - RRPONTSYD (역레포 잔고, $Billions -> $Millions 변환: * 1000)
    - 수식: WALCL - WTREGEN - RRP ($Trillions 단위로 정규화)
    """
    if not api_key:
        return pd.Series(dtype=float)
    try:
        # 버퍼 기간을 두어 ffill 전방 보간이 끊기지 않도록 처리
        walcl = fetch_fred_series(api_key, "WALCL", days=days + 60)
        tga = fetch_fred_series(api_key, "WTREGEN", days=days + 60)
        rrp = fetch_fred_series(api_key, "RRPONTSYD", days=days + 60)
        
        if walcl.empty or tga.empty or rrp.empty:
            return pd.Series(dtype=float)
        
        # 날짜 인덱스 통합 및 ffill 처리
        all_dates = walcl.index.union(tga.index).union(rrp.index).sort_values()
        df = pd.DataFrame(index=all_dates)
        df['walcl'] = walcl.reindex(all_dates).ffill()
        df['tga'] = tga.reindex(all_dates).ffill()
        df['rrp'] = (rrp * 1000.0).reindex(all_dates).ffill()  # $B -> $M 단위 맞춤
        
        df = df.dropna()
        # 최종 수치: 조 달러($Trillions) 단위로 변환
        net_liq_trillions = (df['walcl'] - df['tga'] - df['rrp']) / 1_000_000.0
        
        cutoff = datetime.today() - timedelta(days=days)
        return net_liq_trillions[net_liq_trillions.index >= pd.Timestamp(cutoff)]
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=300)
def fetch_crypto_ticker(symbol_binance, symbol_yf):
    """암호화폐 시세를 다중 백엔드로 수집합니다."""
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

fred_api_key = ""
try:
    if "FRED_API_KEY" in st.secrets:
        fred_api_key = st.secrets["FRED_API_KEY"]
except Exception:
    pass

# 화면 입력창 노출 없이 Secrets 연동 상태만 안전하게 표시
if fred_api_key:
    st.sidebar.success("🔒 FRED API 보안 연결됨")
else:
    fred_api_key = st.sidebar.text_input(
        "FRED API Key", 
        value="", 
        type="password", 
        help="거시경제 데이터를 불러오려면 FRED API 키를 입력하세요."
    )

st.sidebar.markdown("---")
st.sidebar.info("⏱️ 트래픽 절약 및 속도 향상을 위해 데이터는 5~10분 단위로 자동 캐싱됩니다.")

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
# 3. BLOCK 1: GLOBAL EQUITIES & MARKET BREADTH
# ==========================================
st.subheader("🌎 블록 1: 글로벌 핵심 주가지수 & 시장 건전성 (Breadth)")

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

valid_indices = []
for name, ticker in all_indices:
    data = fetch_yf_current(ticker)
    if data:
        valid_indices.append((name, data))

for i in range(0, len(valid_indices), 6):
    cols = st.columns(6)
    chunk = valid_indices[i:i+6]
    for j, (name, data) in enumerate(chunk):
        cols[j].metric(label=name, value=f"{data['price']:,.2f}", delta=f"{data['pct_change']:+.2f}%")

st.write("")
# 신규 지표: 동일가중 vs 시총가중 S&P 500 (RSP / SPY Ratio)
st.markdown("##### 📊 미국 시장 건전성: 동일가중 vs 시총가중 (RSP / SPY)")
rsp_hist = fetch_yf_history("RSP", "1y")
spy_hist = fetch_yf_history("SPY", "1y")

if not rsp_hist.empty and not spy_hist.empty:
    common_idx = rsp_hist.index.intersection(spy_hist.index)
    breadth_ratio = (rsp_hist.loc[common_idx] / spy_hist.loc[common_idx]).dropna()
    
    if len(breadth_ratio) >= 2:
        curr_ratio = breadth_ratio.iloc[-1]
        prev_ratio = breadth_ratio.iloc[-2]
        ratio_diff = curr_ratio - prev_ratio
        ratio_pct = (ratio_diff / prev_ratio) * 100
        
        # 50일 이동평균을 통한 추세 판정
        ma50 = breadth_ratio.rolling(window=50).mean()
        is_expanding = curr_ratio >= ma50.iloc[-1] if not ma50.empty else (curr_ratio >= breadth_ratio.iloc[0])
        
        status_label = "시장 건전성 양호 (Breadth 확장)" if is_expanding else "소수 대형주 쏠림 심화 (다이버전스 경계)"
        # 라이트/일반 모드에서도 또렷하게 보이는 고대비 컬러
        status_color = "#059669" if is_expanding else "#dc2626"
        
        b_col1, b_col2 = st.columns([1, 3])
        with b_col1:
            st.metric(
                label=f"RSP / SPY 비율 [{status_label}]",
                value=f"{curr_ratio:.4f}",
                delta=f"{ratio_pct:+.2f}% (전일비)",
                delta_color="normal" if is_expanding else "inverse"
            )
            st.caption("💡 **해설**: 비율 상승 시 중소형주 동반 상승(건전), 하락 시 빅테크 소수 종목만 오르는 착시 장세.")
        
        with b_col2:
            fig_breadth = go.Figure()
            fig_breadth.add_trace(go.Scatter(
                x=breadth_ratio.index, y=breadth_ratio.values, mode='lines',
                name="RSP/SPY Ratio", line=dict(color=status_color, width=2.5)
            ))
            # 라이트 모드(흰색 배경)에서도 선명하게 보이는 딥 블루/네이비 대시선
            fig_breadth.add_trace(go.Scatter(
                x=ma50.index, y=ma50.values, mode='lines',
                name="50일 이동평균", line=dict(color='#2563eb', dash='dash', width=2.2)
            ))
            fig_breadth.update_layout(
                title=dict(text="S&P 500 Breadth: RSP(동일가중) vs SPY(시총가중) 1년 추이", font=dict(size=12)),
                height=180,
                margin=dict(l=20, r=20, t=30, b=20),
                dragmode=False,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_breadth, use_container_width=True, config=TOUCH_SAFE_CONFIG)

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
        line=dict(color=color, width=2),
        hoverinfo='x+y'
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
        showlegend=False,
        dragmode=False
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
                st.plotly_chart(fig, use_container_width=True, config=TOUCH_SAFE_CONFIG)

st.divider()

# ==========================================
# 5. BLOCK 3: BASIS MONITOR (현선물 베이시스 당일 수치 전용)
# ==========================================
st.subheader("📉 블록 3: 현선물 베이시스 (실시간 당일 수치)")

spx_spot = fetch_yf_current("^GSPC")
es_fut = fetch_yf_current("ES=F")
ndx_spot = fetch_yf_current("^NDX")
nq_fut = fetch_yf_current("NQ=F")

col_b1, col_b2, col_b3, col_b4 = st.columns(4)

if spx_spot and es_fut:
    spx_basis = es_fut['price'] - spx_spot['price']
    spx_basis_pct = (spx_basis / spx_spot['price']) * 100
    spx_status = "콘탱고 (정상)" if spx_basis >= 0 else "백워데이션 (경계)"
    with col_b1:
        st.metric(
            label=f"S&P 500 베이시스 [{spx_status}]",
            value=f"{spx_basis:+.2f} pt",
            delta=f"{spx_basis_pct:+.2f}%",
            delta_color="normal" if spx_basis >= 0 else "inverse"
        )
    with col_b2:
        st.metric(
            label="S&P 500 선물(ES) vs 현물",
            value=f"ES: {es_fut['price']:,.2f}",
            delta=f"현물: {spx_spot['price']:,.2f}",
            delta_color="off"
        )

if ndx_spot and nq_fut:
    ndx_basis = nq_fut['price'] - ndx_spot['price']
    ndx_basis_pct = (ndx_basis / ndx_spot['price']) * 100
    ndx_status = "콘탱고 (정상)" if ndx_basis >= 0 else "백워데이션 (경계)"
    with col_b3:
        st.metric(
            label=f"나스닥 100 베이시스 [{ndx_status}]",
            value=f"{ndx_basis:+.2f} pt",
            delta=f"{ndx_basis_pct:+.2f}%",
            delta_color="normal" if ndx_basis >= 0 else "inverse"
        )
    with col_b4:
        st.metric(
            label="나스닥 100 선물(NQ) vs 현물",
            value=f"NQ: {nq_fut['price']:,.2f}",
            delta=f"현물: {ndx_spot['price']:,.2f}",
            delta_color="off"
        )

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
# 7. BLOCK 5: COMMODITIES & MACRO RATIOS
# ==========================================
st.subheader("🛢️ 블록 5: 핵심 원자재, 기간구조 및 거시 비율 (Macro Ratios)")

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

st.markdown("##### 2) 원자재 기간구조(WTI) 및 귀금속 상대가치 비율")
col3_1, col3_2 = st.columns(2)

with col3_1:
    uso_hist = fetch_yf_history("USO", "1y")
    usl_hist = fetch_yf_history("USL", "1y")
    uso_curr = fetch_yf_current("USO")
    usl_curr = fetch_yf_current("USL")
    
    if not uso_hist.empty and not usl_hist.empty and uso_curr and usl_curr:
        uso_norm = (uso_hist / uso_hist.iloc[0]) * 100
        usl_norm = (usl_hist / usl_hist.iloc[0]) * 100
        spread_series = uso_norm - usl_norm
        
        current_spread_val = spread_series.iloc[-1]
        prev_spread_val = spread_series.iloc[-2] if len(spread_series) >= 2 else current_spread_val
        spread_change = current_spread_val - prev_spread_val

        is_backwardation = current_spread_val >= 0
        status_text = "백워데이션 (실물 공급 부족 / 타이트)" if is_backwardation else "콘탱고 (실물 재고 여유 / 수요 둔화)"
        status_color = "#00cc96" if is_backwardation else "#ef553b"
        
        st.metric(
            label=f"WTI 기간구조 기울기 [{status_text}]",
            value=f"{current_spread_val:+.2f} pt",
            delta=f"{spread_change:+.2f} pt 전일비",
            delta_color="normal" if is_backwardation else "inverse"
        )
        
        fig_oil = go.Figure()
        fig_oil.add_trace(go.Scatter(
            x=spread_series.index, 
            y=spread_series.values, 
            mode='lines',
            name="USO - USL 스프레드",
            line=dict(color=status_color, width=2),
            fill='tozeroy'
        ))
        fig_oil.add_hline(
            y=0.0, 
            line_dash="dash", 
            line_color="#64748b", 
            annotation_text="0.0 (수급 중립선)",
            annotation_position="bottom right"
        )
        fig_oil.update_layout(
            title=dict(text="WTI Crude Oil Calendar Spread Proxy (USO vs USL, 1년)", font=dict(size=12)),
            height=200, 
            margin=dict(l=20, r=30, t=30, b=20), 
            dragmode=False, 
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_oil, use_container_width=True, config=TOUCH_SAFE_CONFIG)
    else:
        st.info("원유 기간구조(USO/USL) 데이터를 로드 중입니다.")

with col3_2:
    gc = fetch_yf_history("GC=F", "6mo")
    pa = fetch_yf_history("PA=F", "6mo")
    if not gc.empty and not pa.empty:
        ratio = (gc / pa).dropna()
        ma60 = ratio.rolling(window=60).mean()
        fig_metals = go.Figure()
        fig_metals.add_trace(go.Scatter(x=ratio.index, y=ratio.values, mode='lines', name="금/팔라듐 비율", line=dict(color='#d97706', width=2)))
        fig_metals.add_trace(go.Scatter(x=ma60.index, y=ma60.values, mode='lines', name="60일 이동평균", line=dict(color='#2563eb', dash='dash', width=2)))
        fig_metals.update_layout(
            title=dict(text=f"귀금속 낙수효과: 금 / 팔라듐 비율 (현재: {ratio.iloc[-1]:.2f})", font=dict(size=12)),
            height=200, 
            margin=dict(l=20, r=40, t=30, b=20), 
            dragmode=False, 
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_metals, use_container_width=True, config=TOUCH_SAFE_CONFIG)

st.write("")

# 신규 지표: 구리 / 금 비율 (Copper / Gold Ratio * 1000) vs 미 10년물 국채 금리
st.markdown("##### 3) 글로벌 경기 풍향계: 구리 / 금 비율 vs 미국 10년물 국채 금리")
hg_hist = fetch_yf_history("HG=F", "1y")
gc_hist = fetch_yf_history("GC=F", "1y")
tnx_hist = fetch_yf_history("^TNX", "1y")

if not hg_hist.empty and not gc_hist.empty:
    cg_idx = hg_hist.index.intersection(gc_hist.index)
    cg_ratio = ((hg_hist.loc[cg_idx] / gc_hist.loc[cg_idx]) * 1000.0).dropna()
    
    if len(cg_ratio) >= 2:
        curr_cg = cg_ratio.iloc[-1]
        prev_cg = cg_ratio.iloc[-2]
        cg_pct = ((curr_cg - prev_cg) / prev_cg) * 100
        
        c_col1, c_col2 = st.columns([1, 3])
        with c_col1:
            st.metric(
                label="구리 / 금 비율 (HG/GC × 1,000)",
                value=f"{curr_cg:.3f}",
                delta=f"{cg_pct:+.2f}% (전일비)"
            )
            st.caption("💡 **매크로 시그널**: 비율 상승은 글로벌 경기 회복 및 금리 상승 압력을, 하락은 경기 둔화 및 안전자산 선호를 의미합니다.")
        
        with c_col2:
            fig_cg = go.Figure()
            # 좌측 축: 구리/금 비율
            fig_cg.add_trace(go.Scatter(
                x=cg_ratio.index, y=cg_ratio.values, mode='lines',
                name="구리/금 비율 (좌축)", line=dict(color='#d97706', width=2)
            ))
            # 우측 보조축: 미 10년물 국채 금리(^TNX)
            if not tnx_hist.empty:
                fig_cg.add_trace(go.Scatter(
                    x=tnx_hist.index, y=tnx_hist.values, mode='lines',
                    name="미 10년물 금리 (우축, %)", line=dict(color='#0284c7', width=1.8, dash='dot'),
                    yaxis="y2"
                ))
            
            fig_cg.update_layout(
                title=dict(text="Copper / Gold Ratio vs US 10Y Yield (1년 동행성 비교)", font=dict(size=12)),
                height=220,
                margin=dict(l=20, r=40, t=30, b=20),
                dragmode=False,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(title="Cu/Au × 1,000", tickfont=dict(color='#d97706')),
                yaxis2=dict(title="10Y Yield (%)", tickfont=dict(color='#0284c7'), overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_cg, use_container_width=True, config=TOUCH_SAFE_CONFIG)

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
            number={'suffix': "%", 'valueformat': "+.3f", 'font': {'size': 20, 'color': '#d97706'}},
            title={'text': "USDT 테더 괴리율 / 프리미엄", 'font': {'size': 13}},
            gauge={
                'axis': {'range': [-1, 1], 'tickwidth': 1, 'tickcolor': "#64748b"},
                'bar': {'color': "#d97706", 'thickness': 0.7},
                'steps': [
                    {'range': [-1, -0.2], 'color': "#ef4444"}, 
                    {'range': [-0.2, 0.2], 'color': "rgba(100,116,139,0.15)"}, 
                    {'range': [0.2, 1], 'color': "#10b981"}  
                ]
            }
        ))
        fig_gauge.update_layout(
            height=180, 
            margin=dict(l=15, r=15, t=25, b=15),
            dragmode=False, 
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_gauge, use_container_width=True, config=TOUCH_SAFE_CONFIG)
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
# 9. BLOCK 7: MACRO TRIGGERS, LIQUIDITY & VOLATILITY
# ==========================================
st.subheader("🚨 블록 7: 매크로 시스템 리스크, 유동성 및 이상 변동성")

# 시계열 기간 선택기
period_col, _ = st.columns([3, 1])
with period_col:
    period_choice = st.radio(
        "📅 거시경제 시계열 조회 기간",
        ["1년", "3년", "5년 (기본)", "10년", "전체 (1996년~)"],
        index=2,
        horizontal=True
    )

days_map = {
    "1년": 365,
    "3년": 365 * 3,
    "5년 (기본)": 365 * 5,
    "10년": 365 * 10,
    "전체 (1996년~)": 365 * 30
}
selected_days = days_map.get(period_choice, 1825)

# A) 신규 지표: 연준 순유동성 (Fed Net Liquidity)
st.markdown("##### 💧 1) 미국 연준 순유동성 (Fed Net Liquidity = WALCL - TGA - RRP)")
net_liq_series = fetch_fed_net_liquidity(fred_api_key, days=selected_days)

if not net_liq_series.empty:
    curr_liq = net_liq_series.iloc[-1]
    prev_liq = net_liq_series.iloc[-2] if len(net_liq_series) >= 2 else curr_liq
    liq_change = curr_liq - prev_liq
    
    liq_m_col1, liq_m_col2 = st.columns([1, 3])
    with liq_m_col1:
        st.metric(
            label="현재 연준 순유동성 ($Trillion)",
            value=f"${curr_liq:.3f} T",
            delta=f"{liq_change * 1000.0:+.1f} B (직전 보고서 대비)",
            delta_color="normal"
        )
        st.caption("💡 **산출 공식**: 연준 총자산(WALCL) - 재무부 잔고(TGA) - 역레포 잔고(RRP). 자산시장 유동성의 펀더멘털 엔진입니다.")
    
    with liq_m_col2:
        fig_liq = go.Figure()
        fig_liq.add_trace(go.Scatter(
            x=net_liq_series.index, y=net_liq_series.values, mode='lines',
            name="Fed Net Liquidity ($T)", line=dict(color='#0284c7', width=2),
            fill='tozeroy', fillcolor='rgba(2, 132, 199, 0.1)'
        ))
        fig_liq.update_layout(
            title=dict(text="Federal Reserve Net Liquidity ($ Trillions)", font=dict(size=12)),
            height=200,
            margin=dict(l=20, r=20, t=30, b=20),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_liq, use_container_width=True, config=MACRO_CHART_CONFIG)
else:
    st.info("연준 순유동성 데이터를 불러오려면 FRED API 키가 필요합니다.")

st.write("")

# B) 하이일드 스프레드 & 장단기 금리차
st.markdown("##### 🏛️ 2) 신용 스프레드 및 장단기 금리 역전 모니터")
col5_1, col5_2 = st.columns(2)

with col5_1:
    hy_spread = fetch_fred_series(fred_api_key, "BAMLH0A0HYM2", days=selected_days)
    if not hy_spread.empty:
        current_hy = hy_spread.iloc[-1]
        fig_hy = go.Figure()
        fig_hy.add_trace(go.Scatter(
            x=hy_spread.index, y=hy_spread.values, mode='lines', 
            name="HY Spread", line=dict(color='#059669', width=2)
        ))
        fig_hy.add_hline(y=5.0, line_dash="dash", line_color="#dc2626", annotation_text="위험 경계선 (5.0%)")
        fig_hy.update_layout(
            title=dict(text=f"미국 하이일드 스프레드 (현재: {current_hy:.2f}%)", font=dict(size=12)), 
            height=260, 
            margin=dict(l=20, r=20, t=35, b=20), 
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        if current_hy >= 5.0:
            st.error(f"⚠️ 하이일드 스프레드 경고: {current_hy:.2f}%")
        st.plotly_chart(fig_hy, use_container_width=True, config=MACRO_CHART_CONFIG)
    else:
        st.info("FRED API 키가 필요합니다.")

with col5_2:
    dgs10 = fetch_fred_series(fred_api_key, "DGS10", days=selected_days)
    dgs2 = fetch_fred_series(fred_api_key, "DGS2", days=selected_days)
    
    if not dgs10.empty and not dgs2.empty:
        spread_10_2 = (dgs10 - dgs2).dropna()
        current_spread = spread_10_2.iloc[-1]
        
        fig_yield = go.Figure()
        fig_yield.add_trace(go.Scatter(
            x=spread_10_2.index, y=spread_10_2.values, mode='lines', 
            name="10Y-2Y", line=dict(color='#4f46e5', width=2), fill='tozeroy'
        ))
        fig_yield.add_hline(y=0.0, line_width=1.5, line_color="#64748b", annotation_text="역전 기준선")
        fig_yield.update_layout(
            title=dict(text=f"미국 장단기 금리차 10Y-2Y (현재: {current_spread:.2f}%)", font=dict(size=12)), 
            height=260, 
            margin=dict(l=20, r=20, t=35, b=20), 
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_yield, use_container_width=True, config=MACRO_CHART_CONFIG)
    else:
        st.info("FRED API 키가 필요합니다.")

st.write("")

# C) 이상 변동성 & 신규 지표: MOVE / VIX Ratio
st.markdown("##### ⚡ 3) 크로스에셋 변동성 괴리 및 스트레스: MOVE / VIX Ratio")
v_col1, v_col2 = st.columns([1.2, 2.8])

with v_col1:
    vix = fetch_yf_current("^VIX")
    vix1d = fetch_yf_current("^VIX1D")
    skew = fetch_yf_current("^SKEW")
    move_curr = fetch_yf_current("^MOVE")
    
    if vix:
        st.metric(label="VIX (주식 30일 변동성)", value=f"{vix['price']:.2f}", delta=f"{vix['pct_change']:+.2f}%", delta_color="inverse")
    if move_curr:
        st.metric(label="MOVE 지수 (채권 변동성)", value=f"{move_curr['price']:.2f}", delta=f"{move_curr['pct_change']:+.2f}%", delta_color="inverse")
    if vix1d:
        st.metric(label="VIX1D (1일 초단기 변동성)", value=f"{vix1d['price']:.2f}", delta=f"{vix1d['pct_change']:+.2f}%", delta_color="inverse")
    if skew:
        st.metric(label="SKEW (꼬리위험 방어 비용)", value=f"{skew['price']:.2f}", delta=f"{skew['pct_change']:+.2f}%", delta_color="inverse")

with v_col2:
    move_hist = fetch_yf_history("^MOVE", "1y")
    vix_hist = fetch_yf_history("^VIX", "1y")
    
    if not move_hist.empty and not vix_hist.empty:
        mv_idx = move_hist.index.intersection(vix_hist.index)
        mv_ratio = (move_hist.loc[mv_idx] / vix_hist.loc[mv_idx]).dropna()
        
        if len(mv_ratio) >= 2:
            curr_mv = mv_ratio.iloc[-1]
            prev_mv = mv_ratio.iloc[-2]
            mv_diff = curr_mv - prev_mv
            
            # MOVE/VIX가 6.0 또는 6.5를 초과하면 채권 시장 대비 주식 시장의 방심(경계)
            is_complacent = curr_mv >= 6.0
            status_mv = "채권 공포 대비 주식 방심 (괴리 확대 경계)" if is_complacent else "정상 크로스에셋 변동성 밴드"
            
            st.metric(
                label=f"MOVE / VIX 비율 [{status_mv}]",
                value=f"{curr_mv:.2f}",
                delta=f"{mv_diff:+.2f} pt 전일비",
                delta_color="inverse" if is_complacent else "off"
            )
            
            fig_mv = go.Figure()
            fig_mv.add_trace(go.Scatter(
                x=mv_ratio.index, y=mv_ratio.values, mode='lines',
                name="MOVE/VIX Ratio", line=dict(color='#dc2626' if is_complacent else '#7c3aed', width=2)
            ))
            fig_mv.add_hline(
                y=6.0, line_dash="dash", line_color="#ef4444",
                annotation_text="방심 임계선 (6.0 pt)", annotation_position="top left"
            )
            fig_mv.update_layout(
                title=dict(text="ICE BofA MOVE / CBOE VIX Ratio (1년 추이)", font=dict(size=12)),
                height=220,
                margin=dict(l=20, r=30, t=30, b=20),
                dragmode=False,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_mv, use_container_width=True, config=TOUCH_SAFE_CONFIG)
    else:
        st.info("MOVE / VIX 시계열 데이터를 불러오는 중입니다.")

st.caption("🚀 데이터 소스: yfinance, FRED, Binance REST API | 1인 FICC 데스크 전용")
