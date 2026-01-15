import streamlit as st
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# 0. 페이지 설정
st.set_page_config(page_title="주식 & 원자재 통합 분석기", layout="wide")

# --- 데이터 로드 (KRX) ---
@st.cache_data
def get_krx_list():
    try:
        df = fdr.StockListing('KRX')
        return df[['Code', 'Name', 'Market']]
    except:
        return pd.DataFrame()

krx_df = get_krx_list()

# --- 세션 상태 초기화 ---
if 'symbols_dict' not in st.session_state:
    # 초기 기본 리스트 (원자재 및 지수)
    st.session_state.symbols_dict = {
        'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'KOSPI': '^KS11', 
        '금 (Gold)': 'GC=F', '은 (Silver)': 'SI=F', 'WTI 원유': 'CL=F'
    }
    st.session_state.market_dict = {
        'S&P 500': 'US', 'Nasdaq 100': 'US', 'KOSPI': 'Index', 
        '금 (Gold)': 'Comm', '은 (Silver)': 'Comm', 'WTI 원유': 'Comm'
    }

# --- 종목 검색 함수 ---
def search_stock(query, df):
    query_clean = query.strip().replace(" ", "").upper()
    if df.empty:
        return None, None, None
    
    # 1. 코드로 정확히 일치 확인
    match = df[df['Code'] == query_clean]
    
    # 2. 이름으로 검색 (포함 확인)
    if match.empty:
        temp_df = df.copy()
        temp_df['NameClean'] = temp_df['Name'].str.replace(" ", "").str.upper()
        match = temp_df[temp_df['NameClean'].str.contains(query_clean, na=False)]
        
    if not match.empty:
        res = match.iloc[0]
        display_name = f"{res['Name']} ({res['Code']})"
        ticker = f"{res['Code']}.KS" if res['Market'] == 'KOSPI' else f"{res['Code']}.KQ"
        return display_name, ticker, res['Market']
    
    return None, None, None

# --- 1. 사이드바 ---
st.sidebar.header("🔍 종목 추가")
search_input = st.sidebar.text_input("종목명 또는 코드 입력 (엔터)", key="search_box")

if search_input:
    d_name, ticker, market = search_stock(search_input, krx_df)
    
    if d_name:
        st.session_state.symbols_dict[d_name] = ticker
        st.session_state.market_dict[d_name] = market
        st.sidebar.success(f"추가 완료: {d_name}")
    else:
        # 한국 시장에 없으면 해외 티커로 시도
        st.session_state.symbols_dict[search_input.upper()] = search_input.upper()
        st.session_state.market_dict[search_input.upper()] = "Global"
        st.sidebar.info(f"해외 티커로 추가됨: {search_input.upper()}")

# --- 2. 메인 설정 ---
st.title("📈 주식 & 원자재 통합 분석 리포트")

# 현재 저장된 종목들 중 분석할 항목 선택
options = list(st.session_state.symbols_dict.keys())
selected_names = st.multiselect("분석 항목 선택", options=options, default=options[:4])

if selected_names:
    load_days = st.sidebar.number_input("데이터 로드 범위 (영업일)", 30, 1000, 120, 10)
    
    prices_dict = {}
    with st.spinner('데이터 다운로드 중...'):
        for name in selected_names:
            ticker = st.session_state.symbols_dict[name]
            df = yf.download(ticker, period="2y", auto_adjust=True, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index).date
                prices_dict[name] = df.tail(load_days)

    if prices_dict:
        # --- 3. 그래프 (음영 및 수익률) ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭", "📉 최고가 대비 하락률 (MDD %)"), 
                            row_heights=[0.6, 0.4])
        
        colors = px.colors.qualitative.Safe
        summary_list = []
        close_list = []

        # [수정] 현재 '선택된' 종목들에 대해서만 그래프를 그림 (잔상 방지)
        for i, name in enumerate(selected_names):
            if name not in prices_dict: continue
            df = prices_dict[name]
            color = colors[i % len(colors)]
            
            base_p = float(df['Close'].iloc[0])
            norm_c = (df['Close'] / base_p - 1) * 100
            norm_h = (df['High'] / base_p - 1) * 100
            norm_l = (df['Low'] / base_p - 1) * 100
            
            # (1) 변동폭 음영 추가
            fig.add_trace(go.Scatter(
                x=list(df.index) + list(df.index)[::-1],
                y=list(norm_h.values) + list(norm_l.values)[::-1],
                fill='toself', fillcolor=color, line=dict(color='rgba(0,0,0,0)'),
                opacity=0.15, name=name, showlegend=False, hoverinfo='skip'
            ), row=1, col=1)
            
            # (2) 메인 수익률 선
            fig.add_trace(go.Scatter(x=df.index, y=norm_c, name=name, line=dict(color=color, width=2.5)), row=1, col=1)
            
            # (3) MDD 그래프
            dd = (df['Close'] / df['Close'].cummax() - 1) * 100
            fig.add_trace(go.Scatter(x=df.index, y=dd, name=name, showlegend=False, line=dict(color=color, width=1.2), fill='tozeroy'), row=2, col=1)
            
            # 요약용 데이터
            summary_list.append({
                '시장': st.session_state.market_dict.get(name, "N/A"),
                '항목': name,
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

        # --- 4. 상관관계 및 성과 요약 ---
        st.divider()
        col_l, col_r = st.columns([1, 1.2])

        with col_l:
            st.subheader("🔗 상관관계 분석")
            if len(close_list) > 1:
                corr_df = pd.concat(close_list, axis=1).pct_change().corr()
                st.plotly_chart(px.imshow(corr_df, text_auto=".2f", color_continuous_scale='RdBu_r'), use_container_width=True)
            else:
                st.info("비교를 위해 2개 이상의 종목을 선택하세요.")

        with col_r:
            st.subheader("📊 성과 요약")
            sum_df = pd.DataFrame(summary_list).sort_values('현재수익률 (%)', ascending=False)
            
            def highlight(row):
                diff = row['최고수익률 (%)'] - row['현재수익률 (%)']
                styles = ['' for _ in row]
                idx = sum_df.columns.get_loc('현재수익률 (%)')
                if diff < 0.01: styles[idx] = 'color: red; font-weight: bold'
                elif diff <= 5.0: styles[idx] = 'color: blue; font-weight: bold'
                return styles

            st.dataframe(
                sum_df.style.apply(highlight, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '변동성 (%)']),
                use_container_width=True, hide_index=True
            )
