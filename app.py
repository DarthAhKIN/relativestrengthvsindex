import streamlit as st
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# 0. 페이지 기본 설정
st.set_page_config(page_title="주식 & 원자재 통합 분석기", layout="wide")

# --- 데이터 로드 함수 (캐싱) ---
@st.cache_data
def get_krx_list():
    try: 
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']]
    except: 
        return pd.DataFrame()

def get_ticker_info(input_val, krx_df):
    """입력값(이름, 코드, 티커)을 분석하여 정식 정보 반환"""
    if krx_df.empty: return input_val, "N/A", input_val
    
    target = input_val.strip().replace(" ", "").upper()
    target_code = target.split('.')[0] # .KS 등 접미사 제거
    
    # 1. 코드로 검색
    row = krx_df[krx_df['Code'] == target_code]
    
    # 2. 이름으로 검색 (공백 무시)
    if row.empty:
        temp_df = krx_df.copy()
        temp_df['NameClean'] = temp_df['Name'].str.replace(" ", "").str.upper()
        row = temp_df[temp_df['NameClean'].str.contains(target, na=False)].head(1)
        
    if not row.empty:
        code = row.iloc[0]['Code']
        name = row.iloc[0]['Name']
        market = row.iloc[0]['Market']
        suffix = ".KS" if market == 'KOSPI' else ".KQ"
        return f"{code}{suffix}", market, f"{name} ({code})"
    
    # 3. 해외 티커
    return input_val, "Global", input_val

# --- 1. 사이드바 설정 ---
st.sidebar.header("🔍 기본 설정")
load_days = st.sidebar.number_input("데이터 로드 범위 (영업일)", 30, 1000, 120, 10)

# 기본 지수 및 자산
default_assets = {
    'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'KOSPI': '^KS11',
    '금 (Gold)': 'GC=F', 'WTI 원유': 'CL=F'
}

krx_df = get_krx_list()
added_input = st.sidebar.text_input("종목 추가 (예: 삼성전자, 144600, TSLA)", "")

# 세션 상태로 종목 관리 (중복 방지 및 유지)
if 'symbols' not in st.session_state:
    st.session_state.symbols = default_assets.copy()
    st.session_state.markets = {k: "Index/Global" for k in default_assets}

if added_input:
    ticker, market, display_name = get_ticker_info(added_input, krx_df)
    st.session_state.symbols[display_name] = ticker
    st.session_state.markets[display_name] = market

# --- 2. 데이터 다운로드 ---
prices_dict = {}
with st.spinner('데이터 수집 중...'):
    for name, sym in st.session_state.symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index).date
                prices_dict[name] = df.tail(load_days)
        except: continue

if prices_dict:
    st.title("📈 주식 & 원자재 통합 분석 리포트")
    
    # 분석 항목 선택
    selected_names = st.multiselect("분석 항목 선택", options=list(prices_dict.keys()), default=list(prices_dict.keys())[:5])

    if selected_names:
        # --- 3. 통합 그래프 ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, 
                            subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭", "📉 최고가 대비 하락률 (MDD %)"), 
                            row_heights=[0.6, 0.4])
        
        colors = px.colors.qualitative.Safe
        summary_list = []
        close_list = []

        for i, name in enumerate(selected_names):
            df = prices_dict[name]
            color = colors[i % len(colors)]
            
            base_p = float(df['Close'].iloc[0])
            norm_c = (df['Close'] / base_p - 1) * 100
            norm_h = (df['High'] / base_p - 1) * 100
            norm_l = (df['Low'] / base_p - 1) * 100
            
            # (1) 음영 (변동폭) - legendgroup으로 선과 연결하여 동시 On/Off 가능
            fig.add_trace(go.Scatter(
                x=list(df.index) + list(df.index)[::-1], 
                y=list(norm_h.values) + list(norm_l.values)[::-1], 
                fill='toself', fillcolor=color, line=dict(color='rgba(0,0,0,0)'), 
                opacity=0.15, name=name, legendgroup=name, showlegend=False, hoverinfo='skip'
            ), row=1, col=1)
            
            # (2) 메인 수익률 선
            fig.add_trace(go.Scatter(
                x=df.index, y=norm_c, name=name, legendgroup=name, mode='lines', 
                line=dict(width=2.5, color=color), hovertemplate='%{y:.2f}%'
            ), row=1, col=1)
            
            # (3) MDD 그래프
            dd = (df['Close'] / df['Close'].cummax() - 1) * 100
            fig.add_trace(go.Scatter(
                x=dd.index, y=dd, name=name, legendgroup=name, showlegend=False, 
                line=dict(width=1.5, color=color), fill='tozeroy', hovertemplate='%{y:.2f}%'
            ), row=2, col=1)
            
            # 성과 데이터 요약
            summary_list.append({
                '시장': st.session_state.markets.get(name, "N/A"),
                '이름': name,
                '현재수익률 (%)': norm_c.iloc[-1],
                '최고수익률 (%)': norm_c.max(),
                '변동성 (%)': df['Close'].pct_change().std() * np.sqrt(252) * 100
            })
            
            s_close = df['Close'].copy()
            s_close.name = name
            close_list.append(s_close)

        fig.update_layout(height=800, template='plotly_white', hovermode='x unified',
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

        # --- 4. 상관관계 및 성과요약표 ---
        st.divider()
        col1, col2 = st.columns([1, 1.2])

        with col1:
            st.subheader("🔗 상관관계 분석")
            if len(close_list) > 1:
                corr = pd.concat(close_list, axis=1).pct_change().corr()
                st.plotly_chart(px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r'), use_container_width=True)

        with col2:
            st.subheader("📊 성과 요약")
            sum_df = pd.DataFrame(summary_list).sort_values('현재수익률 (%)', ascending=False)
            
            def highlight_status(row):
                diff = row['최고수익률 (%)'] - row['현재수익률 (%)']
                styles = ['' for _ in row]
                idx = sum_df.columns.get_loc('현재수익률 (%)')
                if diff < 0.01: styles[idx] = 'color: red; font-weight: bold'
                elif diff <= 5.0: styles[idx] = 'color: blue; font-weight: bold'
                return styles

            st.dataframe(
                sum_df.style.apply(highlight_status, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '변동성 (%)']),
                hide_index=True, use_container_width=True
            )
else:
    st.info("데이터를 불러올 수 없습니다. 티커를 확인해 주세요.")
