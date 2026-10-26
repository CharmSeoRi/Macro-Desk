# ... existing code ...
        # High Yield Spread
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
        
        fig_hy = go.Figure()
        fig_hy.add_trace(go.Scatter(
            x=hy_spread.index, 
            y=hy_spread.values, 
            name="HY Spread (%)",
            line=dict(color="#ef4444", width=2)
        ))
# ... existing code ...
