import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go

# 0. 페이지 기본 설정
st.set_page_config(page_title="주식 & 원자재 통합 분석기", layout="wide")

@st.cache_data
def get_krx_list():
    try: return fdr.StockListing('KRX')
    except: return pd.DataFrame()

def get_ticker(name, krx_df):
    if krx_df.empty: return name
    row = krx_df[krx_df['Name'] == name]
    if not row.empty:
        code = row.iloc[0]['Code']
        market = row.iloc[0]['Market']
        return f"{code}.KS" if market == 'KOSPI' else f"{code}.KQ"
    return name

# --- 1. 사이드바 설정 ---
st.sidebar.header("🔍 기본 설정")
load_days = st.sidebar.slider("데이터 로드 범위 (최대 영업일)", 30, 500, 150)

default_symbols = {
    'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Dow Jones': '^DJI', 
    'Russell 2000': '^RUT', 'KOSPI': '^KS11', 'KOSDAQ': '^KQ11',
    '금 (Gold)': 'GC=F', '은 (Silver)': 'SI=F', '구리 (Copper)': 'HG=F',
    'WTI 원유': 'CL=F', '철광석 (Iron Ore)': 'TIO=F'
}

krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "", placeholder="예: 삼성전자, TSLA, NVDA")

symbols = default_symbols.copy()
if added_stocks:
    for s in added_stocks.split(','):
        name = s.strip()
        if name: symbols[name] = get_ticker(name, krx_df)

# --- 2. 데이터 로드 및 정제 ---
prices_dict = {}
with st.spinner('데이터를 수집 및 정제 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                df = df.reset_index()
                df['Date'] = pd.to_datetime(df['Date']).dt.date
                close_col = 'Close' if 'Close' in df.columns else df.columns[1]
                temp_df = pd.DataFrame({
                    'Date': df['Date'],
                    name: df[close_col].iloc[:,0] if isinstance(df[close_col], pd.DataFrame) else df[close_col]
                }).set_index('Date')
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    df_merged = pd.concat(prices_dict.values(), axis=1).sort_index()
    df_merged = df_merged.interpolate(method='linear', limit_direction='both')
    df_merged = df_merged.tail(load_days)
    
    # --- 3. 메인 화면 상단 구성 ---
    st.title("📈 주식 & 원자재 수익률 및 하락률 분석")
    
    selected_symbols = st.multiselect(
        "그래프에 표시할 항목을 선택하세요",
        options=list(df_merged.columns),
        default=list(df_merged.columns)[:5] # 너무 많으면 복잡하므로 기본 5개
    )
    
    st.sidebar.subheader("📅 분석 범위 (0% 리셋)")
    min_d, max_d = df_merged.index.min(), df_merged.index.max()
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD")
    
    start_date, end_date = user_date[0], user_date[1]
    
    if not selected_symbols:
        st.warning("항목을 선택해 주세요.")
    else:
        filtered_prices = df_merged.loc[start_date:end_date, selected_symbols].copy()
        norm_df = (filtered_prices / filtered_prices.iloc[0] - 1) * 100
        daily_rets = filtered_prices.pct_change()
        
        st.success(f"✅ **분석 범위:** {start_date} ~ {end_date} (**총 {len(filtered_prices)} 영업일**)")
        
        # 공통 컬러맵 생성 (두 차트의 색상을 일치시키기 위함)
        colors = px.colors.qualitative.Alphabet 
        color_map = {col: colors[i % len(colors)] for i, col in enumerate(selected_symbols)}

        # --- 4. 메인 그래프 (수익률 추이) ---
        st.subheader("🚀 누적 수익률 (%)")
        fig_main = go.Figure()

        for col in selected_symbols:
            fig_main.add_trace(go.Scatter(
                x=norm_df.index, y=norm_df[col],
                name=col, legendgroup=col,
                mode='lines', line=dict(width=2, color=color_map[col]),
                connectgaps=True, hovertemplate='%{x}<br>수익률: %{y:.2f}%'
            ))
            
            max_val = norm_df[col].max()
            max_date = norm_df[col].idxmax()
            fig_main.add_trace(go.Scatter(
                x=[max_date], y=[max_val],
                name=col, legendgroup=col, mode='markers',
                marker=dict(size=10, symbol='star', color=color_map[col]),
                showlegend=False, hoverinfo='skip'
            ))

        fig_main.add_hline(y=0, line_dash="dash", line_color="black")
        
        # X축 설정 동기화의 핵심
        fig_main.update_layout(
            hovermode='x unified', template='plotly_white', height=450, 
            margin=dict(t=10, b=10),
            xaxis=dict(showticklabels=True, range=[start_date, end_date]) # 날짜 범위 고정
        )
        st.plotly_chart(fig_main, use_container_width=True)

        # --- 5. 드로우다운(Drawdown) 그래프 ---
        st.subheader("📉 최고가 대비 하락률 (Drawdown %)")
        fig_dd = go.Figure()

        all_min_dd = []
        for col in selected_symbols:
            rolling_high = filtered_prices[col].cummax()
            drawdown = ((filtered_prices[col] / rolling_high) - 1) * 100
            all_min_dd.append(drawdown.min())
            
            fig_dd.add_trace(go.Scatter(
                x=drawdown.index, y=drawdown,
                name=col, legendgroup=col,
                mode='lines', line=dict(width=1.5, color=color_map[col]),
                fill='tozeroy', 
                connectgaps=True, hovertemplate='%{x}<br>하락률: %{y:.2f}%'
            ))
            
            is_high = drawdown.abs() < 1e-6
            df_high = drawdown[is_high]
            fig_dd.add_trace(go.Scatter(
                x=df_high.index, y=df_high,
                mode='markers', legendgroup=col,
                marker=dict(size=8, symbol='diamond', color=color_map[col], line=dict(width=1, color='white')),
                showlegend=False, hoverinfo='skip'
            ))

        min_y_limit = min(all_min_dd) if all_min_dd else -10
        y_range_bottom = min(min_y_limit * 1.1, -5.0)

        fig_dd.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
        
        # 상단 차트와 X축 범위를 완벽히 일치시킴
        fig_dd.update_layout(
            hovermode='x unified', template='plotly_white', height=350,
            yaxis=dict(title="하락률 (%)", range=[y_range_bottom, 2], autorange=False),
            xaxis=dict(range=[start_date, end_date]), # 상단 차트와 동일한 날짜 범위 적용
            margin=dict(t=10, b=10)
        )
        st.plotly_chart(fig_dd, use_container_width=True)

        st.divider()

        # --- 6. 하단 분석 리포트 ---
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("항목 간 상관관계")
            if len(selected_symbols) > 1:
                corr_matrix = daily_rets.dropna(how='all').corr()
                fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                st.plotly_chart(fig_corr, use_container_width=True)

        with col_right:
            st.subheader("📊 성과 요약")
            summary_data = []
            num_days = len(daily_rets.dropna(how='all'))
            
            for col in selected_symbols:
                summary_data.append({
                    '항목': col,
                    '현재수익률 (%)': norm_df[col].iloc[-1],
                    '최고수익률 (%)': norm_df[col].max(),
                    '일평균 변동성 (%)': daily_rets[col].std() * 100,
                    '선택기간 변동률 (%)': daily_rets[col].std() * np.sqrt(num_days) * 100
                })
            
            sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
            
            def highlight_status(row):
                curr, max_r = row['현재수익률 (%)'], row['최고수익률 (%)']
                is_max = abs(curr - max_r) < 1e-9
                is_near = (max_r - curr) <= 5.0
                return ['color: red; font-weight: bold' if is_max and val == curr else 
                        'color: blue; font-weight: bold' if is_near and val == curr else '' for val in row]

            st.dataframe(
                sum_df.style.apply(highlight_status, axis=1).format({
                    '현재수익률 (%)': '{:.2f}', '최고수익률 (%)': '{:.2f}',
                    '일평균 변동성 (%)': '{:.2f}', '선택기간 변동률 (%)': '{:.2f}'
                }), hide_index=True, use_container_width=True
            )
else:
    st.error("데이터 수집에 실패했습니다.")
