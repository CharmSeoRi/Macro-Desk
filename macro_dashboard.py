import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import re

# ---------------------------------------------------------
# 1. 페이지 환경설정 및 모바일/태블릿 반응형 CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="1인 FICC 매크로 콕핏",
    page_icon="🌐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 반응형 그리드 & 터치 친화적 CSS 주입
st.markdown("""
<style>
    /* 여백 최적화 */
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }
    
    /* 폰트 기본 */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* 반응형 메트릭 카드 컨테이너 */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        margin-bottom: 16px;
    }
    
    /* 단일 메트릭 카드 스타일 (라이트 모드 최적화) */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        padding: 12px 14px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .metric-title {
        font-size: 0.82rem;
        color: #4b5563;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #111827;
        letter-spacing: -0.02em;
    }
    .metric-sub {
        font-size: 0.78rem;
        font-weight: 500;
        margin-top: 4px;
    }
    .text-up { color: #dc2626; }
    .text-down { color: #2563eb; }
    .text-neutral { color: #6b7280; }
    
    /* 태블릿 세로 및 모바일 반응형 미디어 쿼리 */
    @media (max-width: 1024px) {
        .metric-grid {
            grid-template-columns: repeat(3, 1fr);
        }
    }
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.8rem;
            padding-right: 0.8rem;
        }
        .metric-grid {
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
        }
        .metric-value {
            font-size: 1.15rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# Plotly 차트용 모바일 터치 스크롤 방해 금지 설정
PLOTLY_TOUCH_CONFIG = {
    'scrollZoom': False,
    'displayModeBar': False,
    'responsive': True
}

# ---------------------------------------------------------
# 2. FRED API 키 보안 및 수집기
# ---------------------------------------------------------
def get_fred_key():
    if "FRED_API_KEY" in st.secrets:
        return st.secrets["FRED_API_KEY"]
    if "fred_key" in st.session_state:
        return st.session_state["fred_key"]
    return None

with st.sidebar:
    st.header("⚙️ 시스템 설정")
    saved_key = get_fred_key()
    user_key = st.text_input(
        "FRED API Key", 
        value=saved_key if saved_key else "", 
        type="password",
        help="연준 경제통계 조회를 위한 32자리 키"
    )
    if user_key:
        st.session_state["fred_key"] = user_key

@st.cache_data(ttl=3600)
def fetch_fred_series(series_id, api_key, days=365*5):
    """FRED 일별/주별 데이터 수집 함수"""
    if not api_key:
        return pd.Series(dtype=float)
    
    start_date = (datetime.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&observation_start={start_date}"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json().get('observations', [])
            records = []
            for d in data:
                val = d.get('value', '.')
                if val != '.':
                    records.append({'date': d['date'], 'value': float(val)})
            if records:
                df = pd.DataFrame(records)
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
                return df['value'].sort_index()
    except Exception:
        pass
    return pd.Series(dtype=float)

# ---------------------------------------------------------
# 3. Yahoo Finance 배치 다운로더
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_batch_market_data(tickers):
    """야후 파이낸스 일괄 수집"""
    ticker_str = " ".join(tickers)
    try:
        df = yf.download(ticker_str, period="1y", interval="1d", progress=False, group_by='ticker')
        return df
    except Exception:
        return pd.DataFrame()

# 전체 필요 티커 정의
ALL_TICKERS = [
    # 환율
    "USDKRW=X", "DX-Y.NYB", "EURUSD=X", "USDJPY=X", "USDCNH=X",
    # 주가지수 & ETF
    "^GSPC", "^IXIC", "^RUT", "^N225", "^GDAXI", "005930.KS", "SPY", "RSP",
    # 선물
    "ES=F", "NQ=F",
    # 변동성
    "^VIX", "^VIX1D", "^SKEW", "^MOVE",
    # 원자재 & ETF
    "CL=F", "USO", "USL", "HG=F", "GC=F", "PALL=F",
    # 금리
    "^TNX", "^FVX", "^IRX"
]

market_data = fetch_batch_market_data(ALL_TICKERS)

def extract_series(df, ticker):
    """멀티인덱스/단일인덱스 yfinance 데이터프레임에서 Close 추출"""
    if df.empty:
        return pd.Series(dtype=float)
    try:
        if isinstance(df.columns, pd.MultiIndex):
            if ticker in df.columns.levels[0]:
                sub = df[ticker]['Close'].dropna()
                return sub
        else:
            if 'Close' in df.columns:
                return df['Close'].dropna()
    except Exception:
        pass
    return pd.Series(dtype=float)

# ---------------------------------------------------------
# 4. 상단 웰컴 헤더 & 환율 메트릭
# ---------------------------------------------------------
st.title("🌐 1인 FICC 글로벌 매크로 콕핏")
st.caption(f"마지막 데이터 수신: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (5분 자동 갱신)")

usdkrw_series = extract_series(market_data, "USDKRW=X")
dxy_series = extract_series(market_data, "DX-Y.NYB")
eur_series = extract_series(market_data, "EURUSD=X")
jpy_series = extract_series(market_data, "USDJPY=X")

st.markdown("### 💱 주요 통화 & 달러 인덱스 (FX Cockpit)")
c1, c2, c3, c4 = st.columns(4)

def render_metric_box(col, title, s, is_currency=False, prefix=""):
    with col:
        if len(s) >= 2:
            last = s.iloc[-1]
            prev = s.iloc[-2]
            chg = last - prev
            pct = (chg / prev) * 100
            sign = "+" if chg > 0 else ""
            color_cls = "text-up" if chg > 0 else "text-down"
            fmt_val = f"{prefix}{last:,.2f}" if not is_currency else f"₩{last:,.1f}"
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">{title}</div>
                <div class="metric-value">{fmt_val}</div>
                <div class="metric-sub {color_cls}">{sign}{chg:.2f} ({sign}{pct:.2f}%)</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info(f"{title}: 데이터 수신 중")

render_metric_box(c1, "원/달러 환율 (USD/KRW)", usdkrw_series, is_currency=True)
render_metric_box(c2, "달러 인덱스 (DXY)", dxy_series)
render_metric_box(c3, "유로/달러 (EUR/USD)", eur_series)
render_metric_box(c4, "달러/엔 (USD/JPY)", jpy_series)

st.markdown("---")

# ---------------------------------------------------------
# 5. 블록 1: 글로벌 주가지수 & 시장 건전성 (Breadth)
# ---------------------------------------------------------
st.subheader("📈 글로벌 주가지수 & 시장 건전성 (Market Breadth)")

col_idx1, col_idx2, col_idx3, col_idx4 = st.columns(4)
render_metric_box(col_idx1, "S&P 500 (^GSPC)", extract_series(market_data, "^GSPC"))
render_metric_box(col_idx2, "나스닥 종합 (^IXIC)", extract_series(market_data, "^IXIC"))
render_metric_box(col_idx3, "러셀 2000 소형주 (^RUT)", extract_series(market_data, "^RUT"))
render_metric_box(col_idx4, "삼성전자 (005930.KS)", extract_series(market_data, "005930.KS"), prefix="₩")

# [복합지표 3] 동일가중 vs 시총가중 S&P 500 (RSP / SPY)
rsp_s = extract_series(market_data, "RSP")
spy_s = extract_series(market_data, "SPY")

if not rsp_s.empty and not spy_s.empty:
    common_idx = rsp_s.index.intersection(spy_s.index)
    rsp_spy_ratio = (rsp_s.loc[common_idx] / spy_s.loc[common_idx])
    ma50 = rsp_spy_ratio.rolling(50).mean()
    
    st.markdown("#### ⚖️ 미국 시장 참여도/건전성: 동일가중 vs 시총가중 (RSP / SPY Ratio)")
    
    last_r = rsp_spy_ratio.iloc[-1]
    prev_r = rsp_spy_ratio.iloc[-2]
    chg_r = last_r - prev_r
    last_ma = ma50.iloc[-1] if not ma50.empty else last_r
    
    is_healthy = last_r >= last_ma
    badge_text = "🟢 시장 건전성 양호 (Breadth 확장)" if is_healthy else "🚨 소수 대형주 쏠림 심화 (경계)"
    badge_bg = "#ecfdf5" if is_healthy else "#fef2f2"
    badge_color = "#047857" if is_healthy else "#b91c1c"
    
    st.markdown(f"""
    <div style="background-color: {badge_bg}; border: 1px solid {badge_color}33; border-radius: 8px; padding: 8px 14px; margin-bottom: 10px; display: inline-block;">
        <span style="font-weight: 700; color: {badge_color};">{badge_text}</span>
        <span style="color: #4b5563; font-size: 0.85rem; margin-left: 10px;">현재 비율: <b>{last_r:.4f}</b> (전일 대비 {chg_r:+.4f}) | 50일 이평: {last_ma:.4f}</span>
    </div>
    """, unsafe_allow_html=True)
    
    fig_breadth = go.Figure()
    fig_breadth.add_trace(go.Scatter(
        x=rsp_spy_ratio.index, 
        y=rsp_spy_ratio.values, 
        name="RSP/SPY Ratio", 
        line=dict(color="#059669" if is_healthy else "#dc2626", width=2)
    ))
    fig_breadth.add_trace(go.Scatter(
        x=ma50.index, 
        y=ma50.values, 
        name="50일 이동평균선", 
        line=dict(color="#2563eb", width=2.2, dash="dash")
    ))
    fig_breadth.update_layout(
        height=260,
        margin=dict(l=20, r=20, t=10, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        dragmode=False
    )
    st.plotly_chart(fig_breadth, use_container_width=True, config=PLOTLY_TOUCH_CONFIG)

st.markdown("---")

# ---------------------------------------------------------
# 6. 블록 3: 지수 선물 & 현선물 베이시스 (카드 수치 전용)
# ---------------------------------------------------------
st.subheader("🎯 미국 지수 현선물 베이시스 (Real-Time Basis)")

es_s = extract_series(market_data, "ES=F")
spx_s = extract_series(market_data, "^GSPC")
nq_s = extract_series(market_data, "NQ=F")
ndx_s = extract_series(market_data, "^IXIC")

col_b1, col_b2, col_b3, col_b4 = st.columns(4)

def render_basis_card(col, name, fut_s, spot_s):
    with col:
        if not fut_s.empty and not spot_s.empty:
            fut = fut_s.iloc[-1]
            spot = spot_s.iloc[-1]
            basis = fut - spot
            basis_pct = (basis / spot) * 100
            
            is_contango = basis >= 0
            state_text = "콘탱고 (정상)" if is_contango else "백워데이션 (패닉/선물할인)"
            color_cls = "text-up" if not is_contango else "text-down"
            
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">{name} 현선물 베이시스</div>
                <div class="metric-value">{basis:+.2f} pt</div>
                <div class="metric-sub {color_cls}">괴리율: {basis_pct:+.2f}% ({state_text})</div>
                <div style="font-size:0.75rem; color:#6b7280; margin-top:4px;">선물: {fut:,.2f} | 현물: {spot:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info(f"{name}: 데이터 준비 중")

render_basis_card(col_b1, "S&P 500 (ES)", es_s, spx_s)
render_basis_card(col_b2, "나스닥 100 (NQ)", nq_s, ndx_s)

# 공포/변동성 콤팩트 카드
vix_s = extract_series(market_data, "^VIX")
vix1d_s = extract_series(market_data, "^VIX1D")
render_metric_box(col_b3, "VIX (30일 공포지수)", vix_s)
render_metric_box(col_b4, "VIX1D (1일 초단기 공포)", vix1d_s)

st.markdown("---")

# ---------------------------------------------------------
# 7. 블록 5: 원자재 및 거시 비율 (Macro Ratios)
# ---------------------------------------------------------
st.subheader("🛢️ 원자재 캘린더 스프레드 & 닥터 코퍼 (Macro Ratios)")

col_com1, col_com2 = st.columns(2)

with col_com1:
    st.markdown("#### ⏳ WTI 기간구조 (USO - USL 캘린더 스프레드 프록시)")
    uso_s = extract_series(market_data, "USO")
    usl_s = extract_series(market_data, "USL")
    
    if not uso_s.empty and not usl_s.empty:
        c_idx = uso_s.index.intersection(usl_s.index)
        # 1년 전 100 기준 정규화 차이 (기간구조 기울기 추적)
        uso_norm = (uso_s.loc[c_idx] / uso_s.loc[c_idx].iloc[0]) * 100
        usl_norm = (usl_s.loc[c_idx] / usl_s.loc[c_idx].iloc[0]) * 100
        spread = uso_norm - usl_norm
        
        last_sp = spread.iloc[-1]
        prev_sp = spread.iloc[-2]
        chg_sp = last_sp - prev_sp
        
        is_back = last_sp >= 0
        tag = "[백워데이션: 실물 공급 부족/타이트]" if is_back else "[콘탱고: 재고 여유/수요 둔화]"
        tag_color = "#059669" if is_back else "#dc2626"
        
        st.markdown(f"""
        <div style="font-size: 0.9rem; margin-bottom: 8px;">
            <b>상태:</b> <span style="color: {tag_color}; font-weight: 700;">{tag}</span>
            <span style="color: #6b7280; margin-left: 8px;">스프레드 인덱스: <b>{last_sp:+.2f} pt</b> ({chg_sp:+.2f})</span>
        </div>
        """, unsafe_allow_html=True)
        
        fig_oil = go.Figure()
        fig_oil.add_trace(go.Scatter(
            x=spread.index, 
            y=spread.values, 
            name="USO-USL Slope",
            fill='tozeroy',
            line=dict(color="#059669" if is_back else "#dc2626", width=2)
        ))
        fig_oil.add_hline(y=0, line_dash="dash", line_color="#4b5563", line_width=1.5)
        fig_oil.update_layout(
            height=260,
            margin=dict(l=20, r=20, t=10, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            dragmode=False
        )
        st.plotly_chart(fig_oil, use_container_width=True, config=PLOTLY_TOUCH_CONFIG)

with col_com2:
    # [복합지표 2] 구리/금 비율 vs 미국 10년물 국채 금리
    st.markdown("#### 🏭 구리 / 금 비율 (Copper/Gold) vs 미 10년물 금리")
    cu_s = extract_series(market_data, "HG=F")
    au_s = extract_series(market_data, "GC=F")
    tnx_s = extract_series(market_data, "^TNX")
    
    if not cu_s.empty and not au_s.empty:
        c_idx2 = cu_s.index.intersection(au_s.index)
        cg_ratio = (cu_s.loc[c_idx2] / au_s.loc[c_idx2]) * 1000
        
        fig_cg = go.Figure()
        fig_cg.add_trace(go.Scatter(
            x=cg_ratio.index, 
            y=cg_ratio.values, 
            name="Cu/Au × 1,000",
            line=dict(color="#d97706", width=2)
        ))
        
        if not tnx_s.empty:
            common_tnx = tnx_s.index.intersection(cg_ratio.index)
            fig_cg.add_trace(go.Scatter(
                x=common_tnx, 
                y=tnx_s.loc[common_tnx].values, 
                name="미 10년물 금리 (%)",
                line=dict(color="#2563eb", width=1.8, dash="dot"),
                yaxis="y2"
            ))
            
        fig_cg.update_layout(
            height=260,
            margin=dict(l=20, r=40, t=10, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="Cu/Au Ratio", titlefont=dict(color="#d97706")),
            yaxis2=dict(title="10Y Yield (%)", titlefont=dict(color="#2563eb"), overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            dragmode=False
        )
        st.plotly_chart(fig_cg, use_container_width=True, config=PLOTLY_TOUCH_CONFIG)

st.markdown("---")

# ---------------------------------------------------------
# 8. 블록 7: 거시경제 시스템 리스크 & 연준 유동성
# ---------------------------------------------------------
st.subheader("🚨 매크로 시스템 리스크 & 연준 순유동성 (Macro System Risk)")

fred_key = get_fred_key()

if not fred_key:
    st.warning("⚠️ 좌측 사이드바에 FRED API Key를 입력하시면 연준 유동성, 하이일드 스프레드, 장단기 금리차가 즉시 활성화됩니다.")
else:
    # 조회 기간 라디오 버튼
    period_sel = st.radio(
        "조회 기간 선택", 
        ["1년", "3년", "5년", "전체(Max)"], 
        index=2, 
        horizontal=True
    )
    days_map = {"1년": 365, "3년": 365*3, "5년": 365*5, "전체(Max)": 365*30}
    sel_days = days_map[period_sel]
    
    col_mac1, col_mac2 = st.columns(2)
    
    # 1) 하이일드 스프레드
    with col_mac1:
        st.markdown("#### 🚨 미국 하이일드 회사채 스프레드 (ICE BofA)")
        
        # 역사적 블랙스완 벤치마크 레퍼런스 가이드
        st.markdown("""
        <div style="background-color: rgba(220, 38, 38, 0.05); border: 1px solid rgba(220, 38, 38, 0.2); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.85rem;">
            <div style="font-weight: 700; color: #dc2626; margin-bottom: 4px;">📌 역사적 블랙스완 위기 피크 (Peak Reference)</div>
            <div style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between; color: #374151;">
                <span>• <b>'08 금융위기(리만):</b> <span style="color:#b91c1c; font-weight:700;">19.88%</span></span>
                <span>• <b>'02 닷컴버블:</b> <span style="color:#b91c1c; font-weight:700;">11.00%</span></span>
                <span>• <b>'20 코로나 팬데믹:</b> <span style="color:#b91c1c; font-weight:700;">10.87%</span></span>
                <span>• <b>'16 셰일 위기:</b> <span style="color:#b91c1c; font-weight:700;">8.39%</span></span>
                <span>• <b>경계 임계선:</b> <span style="color:#f59e0b; font-weight:700;">5.00%</span></span>
            </div>
            <div style="font-size: 0.75rem; color: #6b7280; margin-top: 4px;">* ICE 정책 변경으로 무료 API 시계열이 최근 3년으로 제한되어 비교용 고정 벤치마크를 제공합니다.</div>
        </div>
        """, unsafe_allow_html=True)
        
        hy_spread = fetch_fred_series("BAMLH0A0HYM2", fred_key, days=sel_days)
        if not hy_spread.empty:
            fig_hy = go.Figure()
            fig_hy.add_trace(go.Scatter(
                x=hy_spread.index, 
                y=hy_spread.values, 
                name="HY Spread (%)",
                line=dict(color="#ef4444", width=2)
            ))
            fig_hy.add_hline(y=5.0, line_dash="dash", line_color="#dc2626", annotation_text="위험 임계선 (5.0%)")
            fig_hy.update_layout(
                height=280,
                margin=dict(l=20, r=20, t=20, b=20),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_hy, use_container_width=True)
            
    # 2) 장단기 금리차 (10Y - 2Y)
    with col_mac2:
        st.markdown("#### ⏳ 장단기 국채 금리차 (10Y - 2Y)")
        dgs10 = fetch_fred_series("DGS10", fred_key, days=sel_days)
        dgs2 = fetch_fred_series("DGS2", fred_key, days=sel_days)
        
        if not dgs10.empty and not dgs2.empty:
            c_idx_yield = dgs10.index.intersection(dgs2.index)
            yield_spread = dgs10.loc[c_idx_yield] - dgs2.loc[c_idx_yield]
            
            fig_ys = go.Figure()
            fig_ys.add_trace(go.Scatter(
                x=yield_spread.index, 
                y=yield_spread.values, 
                name="10Y - 2Y",
                fill='tozeroy',
                line=dict(color="#2563eb", width=2)
            ))
            fig_ys.add_hline(y=0.0, line_dash="solid", line_color="#4b5563", line_width=1.5)
            fig_ys.update_layout(
                height=355,
                margin=dict(l=20, r=20, t=20, b=20),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_ys, use_container_width=True)
            
    # [복합지표 1] 연준 순유동성 (Fed Net Liquidity = WALCL - WTREGEN - RRPONTSYD)
    st.markdown("#### 💧 연준 실질 순유동성 (Fed Net Liquidity = Total Assets - TGA - RRP)")
    walcl = fetch_fred_series("WALCL", fred_key, days=sel_days)        # 주간, $ Millions
    tga = fetch_fred_series("WTREGEN", fred_key, days=sel_days)         # 주간, $ Millions
    rrp = fetch_fred_series("RRPONTSYD", fred_key, days=sel_days)       # 일간, $ Billions
    
    if not walcl.empty and not tga.empty and not rrp.empty:
        # 단위를 조 달러($ Trillion)로 통일
        df_liq = pd.DataFrame({
            'walcl': walcl / 1_000_000,
            'tga': tga / 1_000_000,
            'rrp': (rrp * 1000) / 1_000_000
        }).fillna(method='ffill').dropna()
        
        net_liquidity = df_liq['walcl'] - df_liq['tga'] - df_liq['rrp']
        
        last_liq = net_liquidity.iloc[-1]
        prev_liq = net_liquidity.iloc[-2]
        chg_liq = (last_liq - prev_liq) * 1000 # $ Billion 단위 환산
        
        st.markdown(f"""
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 8px 14px; margin-bottom: 8px; display: inline-block;">
            <span style="font-weight: 700; color: #166534;">현재 연준 순유동성: ${last_liq:.2f}T (조 달러)</span>
            <span style="color: #4b5563; font-size: 0.85rem; margin-left: 10px;">직전 대비: <b>{chg_liq:+.1f}B (십억 달러)</b></span>
        </div>
        """, unsafe_allow_html=True)
        
        fig_liq = go.Figure()
        fig_liq.add_trace(go.Scatter(
            x=net_liquidity.index, 
            y=net_liquidity.values, 
            name="Net Liquidity ($T)", 
            fill='tozeroy',
            line=dict(color="#10b981", width=2)
        ))
        fig_liq.update_layout(
            height=250,
            margin=dict(l=20, r=20, t=10, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            dragmode=False
        )
        st.plotly_chart(fig_liq, use_container_width=True, config=PLOTLY_TOUCH_CONFIG)

    # [복합지표 4] 채권 변동성 vs 주식 변동성 비율 (MOVE / VIX)
    move_s = extract_series(market_data, "^MOVE")
    vix_s = extract_series(market_data, "^VIX")
    
    if not move_s.empty and not vix_s.empty:
        c_v = move_s.index.intersection(vix_s.index)
        move_vix = move_s.loc[c_v] / vix_s.loc[c_v]
        last_mv = move_vix.iloc[-1]
        
        is_stress = last_mv >= 6.0
        mv_tag = "🚨 채권 공포 대비 주식 시장 방심 (괴리 확대 경계)" if is_stress else "🟢 자산군 간 변동성 균형 양호"
        mv_color = "#b91c1c" if is_stress else "#047857"
        
        st.markdown(f"#### ⚡ 채권 변동성 vs 주식 변동성 비율 (MOVE / VIX)")
        st.markdown(f"""
        <div style="font-size: 0.9rem; margin-bottom: 8px;">
            <b>진단:</b> <span style="color: {mv_color}; font-weight: 700;">{mv_tag}</span>
            <span style="color: #6b7280; margin-left: 8px;">현재 수치: <b>{last_mv:.2f} pt</b> (위험 임계선: 6.0 pt)</span>
        </div>
        """, unsafe_allow_html=True)
        
        fig_mv = go.Figure()
        fig_mv.add_trace(go.Scatter(
            x=move_vix.index, 
            y=move_vix.values, 
            name="MOVE/VIX",
            line=dict(color="#dc2626" if is_stress else "#8b5cf6", width=2)
        ))
        fig_mv.add_hline(y=6.0, line_dash="dash", line_color="#ef4444", annotation_text="방심 경계선 (6.0)")
        fig_mv.update_layout(
            height=240,
            margin=dict(l=20, r=20, t=10, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            dragmode=False
        )
        st.plotly_chart(fig_mv, use_container_width=True, config=PLOTLY_TOUCH_CONFIG)
