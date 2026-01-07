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
load_days = st.sidebar.slider("데이터 로드 범위 (최대 영업일)", 30, 730, 250)

default_symbols = {
    'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Dow Jones': '^DJI', 
    'KOSPI': '^KS11', 'KOSDAQ': '^KQ11',
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

# --- 2. 데이터 로드 ---
prices_dict = {}
with st.spinner('데이터를 수집 중...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='3y', auto_adjust=True, progress=False)
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
    df_merged = df_merged.interpolate(method='linear', limit_direction='both').tail(load_days)
    
    # --- 3. 메인 화면 ---
    st.title("📈 인터랙티브 구간 수익률 & 하락률 분석")
    
    selected_symbols = st.multiselect("분석 종목 선택", options=list(df_merged.columns), default=list(df_merged.columns)[:5])
    
    # 날짜 범위 선택 (슬라이더)
    min_d, max_d = df_merged.index.min(), df_merged.index.max()
    user_date = st.slider("분석 구간 설정 (드래그하여 변경)", min_value=min_d, max_value=max_d, value=(min_d, max_d))
    
    start_date, end_date = user_date[0], user_date[1]
    
    if selected_symbols:
        # 데이터 필터링 및 계산
        filtered_prices = df_merged.loc[start_date:end_date, selected_symbols].copy()
        norm_df = (filtered_prices / filtered_prices.iloc[0] - 1) * 100
        
        # ----------------------------
        # 4. 차트 생성 (수익률 & Drawdown)
        # ----------------------------
        colors = px.colors.qualitative.Alphabet
        
        # [차트 1] 누적 수익률
        fig_main = go.Figure()
        for i, col in enumerate(selected_symbols):
            fig_main.add_trace(go.Scatter(
                x=norm_df.index, y=norm_df[col], name=col,
                mode='lines', line=dict(width=2, color=colors[i % len(colors)]),
                hovertemplate='%{x}<br>수익률: %{y:.2f}%'
            ))
        
        fig_main.update_layout(
            title=f"선택 기간 누적 수익률 (기준일: {start_date})",
            hovermode='x unified', template='plotly_white', height=450,
            xaxis=dict(rangeslider=dict(visible=False)) # 하단 슬라이더와 연동을 위해 꺼둠
        )
        st.plotly_chart(fig_main, use_container_width=True)

        # [차트 2] Drawdown
        fig_dd = go.Figure()
        for i, col in enumerate(selected_symbols):
            rolling_high = filtered_prices[col].cummax()
            drawdown = ((filtered_prices[col] / rolling_high) - 1) * 100
            
            fig_dd.add_trace(go.Scatter(
                x=drawdown.index, y=drawdown, name=col,
                mode='lines', line=dict(width=1.5, color=colors[i % len(colors)]),
                fill='tozeroy', hovertemplate='%{x}<br>하락률: %{y:.2f}%'
            ))
            
            # 신고가 포인트
            highs = drawdown[drawdown.abs() < 1e-6]
            fig_dd.add_trace(go.Scatter(
                x=highs.index, y=highs, mode='markers',
                marker=dict(size=7, symbol='diamond', color=colors[i % len(colors)]),
                showlegend=False, hoverinfo='skip'
            ))

        fig_dd.update_layout(
            title="선택 기간 최고가 대비 하락률 (Drawdown)",
            hovermode='x unified', template='plotly_white', height=350,
            yaxis=dict(title="하락률 (%)")
        )
        st.plotly_chart(fig_dd, use_container_width=True)

        # ----------------------------
        # 5. 선택 영역 기반 실시간 통계 (표)
        # ----------------------------
        st.divider()
        st.subheader(f"📍 {start_date} ~ {end_date} 구간 상세 통계")
        
        num_days = len(filtered_prices)
        summary_list = []
        
        for col in selected_symbols:
            curr_p = filtered_prices[col]
            period_return = ((curr_p.iloc[-1] / curr_p.iloc[0]) - 1) * 100
            
            rolling_max = curr_p.cummax()
            dd = ((curr_p / rolling_max) - 1) * 100
            period_mdd = dd.min()
            
            summary_list.append({
                '종목': col,
                '구간 수익률 (%)': period_return,
                '구간 최대 낙폭 (MDD %)': period_mdd,
                '시작 가격': curr_p.iloc[0],
                '종료 가격': curr_p.iloc[-1]
            })
            
        stat_df = pd.DataFrame(summary_list).sort_values('구간 수익률 (%)', ascending=False)
        
        st.table(stat_df.style.format({
            '구간 수익률 (%)': '{:.2f}',
            '구간 최대 낙폭 (MDD %)': '{:.2f}',
            '시작 가격': '{:,.2f}',
            '종료 가격': '{:,.2f}'
        }))

        st.info("💡 **팁**: 차트 위의 슬라이더를 드래그하거나 확대하면 해당 날짜 구간에 대한 수익률과 하락률이 자동으로 재계산되어 아래 표에 표시됩니다.")

else:
    st.error("데이터 로드 실패")
