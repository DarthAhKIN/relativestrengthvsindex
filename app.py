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

# --- [보완] 주요 종목 수동 매핑 (KRX 서버 에러 대비) ---
fallback_dict = {
    "005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER", "035720": "카카오",
    "005380": "현대차", "000270": "기아", "068270": "셀트리온", "105560": "KB금융",
    "461590": "PLUS K방산레버리지", "144600": "KODEX 은선물(H)"
}

@st.cache_data
def load_krx_data():
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty:
            return df[['Code', 'Name', 'Market']]
        return pd.DataFrame()
    except:
        return pd.DataFrame()

krx_df = load_krx_data()

# --- 세션 상태 관리 ---
if 'symbols_dict' not in st.session_state:
    # 1. 기본 인덱스 및 원자재 리스트 복구
    st.session_state.symbols_dict = {
        'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'KOSPI': '^KS11', 
        '금 (Gold)': 'GC=F', '은 (Silver)': 'SI=F', 'WTI 원유': 'CL=F'
    }
    st.session_state.market_dict = {
        'S&P 500': 'US', 'Nasdaq 100': 'US', 'KOSPI': 'Index', 
        '금 (Gold)': 'Commodity', '은 (Silver)': 'Commodity', 'WTI 원유': 'Commodity'
    }

# --- 검색 함수 정의 ---
def find_stock(target, df):
    target = target.strip().replace(" ", "").upper()
    # 1. KRX 데이터프레임 검색
    if not df.empty:
        temp = df.copy()
        temp['MatchName'] = temp['Name'].str.replace(" ", "").str.upper()
        match = temp[(temp['Code'] == target) | (temp['MatchName'].str.contains(target))]
        if not match.empty:
            res = match.iloc[0]
            return f"{res['Name']} ({res['Code']})", f"{res['Code']}.KS" if res['Market'] == 'KOSPI' else f"{res['Code']}.KQ", res['Market']
    
    # 2. 수동 매핑(fallback) 검색
    clean_target = target.replace(".KS", "").replace(".KQ", "")
    if clean_target in fallback_dict:
        name = fallback_dict[clean_target]
        return f"{name} ({clean_target})", f"{clean_target}.KS", "KR"
        
    # 3. 해외 티커 직접 입력
    return target, target, "Global"

# --- 1. 사이드바 ---
st.sidebar.header("🔍 종목 추가")
search_input = st.sidebar.text_input("종목명/코드 입력 (예: 삼성전자, 144600, TSLA)", key="search_ticker")

if search_input:
    display_name, ticker, market = find_stock(search_input, krx_df)
    st.session_state.symbols_dict[display_name] = ticker
    st.session_state.market_dict[display_name] = market
    st.sidebar.success(f"추가됨: {display_name}")

# --- 2. 메인 설정 ---
st.title("📈 주식 & 원자재 통합 분석 리포트")

all_options = list(st.session_state.symbols_dict.keys())
selected_names = st.multiselect("분석 항목 선택", options=all_options, default=all_options[:4])

if selected_names:
    load_days = st.sidebar.number_input("데이터 기간 (영업일)", 30, 1000, 120, 10)
    
    prices_dict = {}
    with st.spinner('데이터를 불러오는 중...'):
        for name in selected_names:
            ticker = st.session_state.symbols_dict[name]
            try:
                # yfinance로 넉넉하게 가져와서 자르기
                df = yf.download(ticker, period="2y", auto_adjust=True, progress=False)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df.index = pd.to_datetime(df.index).date
                    prices_dict[name] = df.tail(load_days)
            except: pass

    if prices_dict:
        # --- 3. 그래프 그리기 (음영 포함) ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=("🚀 누적 수익률 (%) 및 변동폭", "📉 최고가 대비 하락률 (MDD %)"), 
                            row_heights=[0.6, 0.4])
        
        colors = px.colors.qualitative.Safe
        summary_list = []
        close_list = []

        for i, name in enumerate(selected_names):
            if name not in prices_dict: continue
            df = prices_dict[name]
            color = colors[i % len(colors)]
            
            # 기준가 및 수익률 계산
            base_p = float(df['Close'].iloc[0])
            norm_c = (df['Close'] / base_p - 1) * 100
            norm_h = (df['High'] / base_p - 1) * 100
            norm_l = (df['Low'] / base_p - 1) * 100
            
            # 3-1. 수익률 음영 (High-Low 변동폭)
            fig.add_trace(go.Scatter(
                x=list(df.index) + list(df.index)[::-1],
                y=list(norm_h.values) + list(norm_l.values)[::-1],
                fill='toself', fillcolor=color, line=dict(color='rgba(0,0,0,0)'),
                opacity=0.15, name=name, showlegend=False, hoverinfo='skip'
            ), row=1, col=1)
            
            # 3-2. 수익률 메인 선
            fig.add_trace(go.Scatter(x=df.index, y=norm_c, name=name, line=dict(color=color, width=2.5)), row=1, col=1)
            
            # 3-3. MDD 그래프
            dd = (df['Close'] / df['Close'].cummax() - 1) * 100
            fig.add_trace(go.Scatter(x=df.index, y=dd, name=name, showlegend=False, line=dict(color=color, width=1), fill='tozeroy'), row=2, col=1)
            
            # 상관관계 및 요약용 데이터
            s_close = df['Close'].copy()
            s_close.name = name
            close_list.append(s_close)
            
            summary_list.append({
                '시장': st.session_state.market_dict.get(name, "N/A"),
                '종목명': name,
                '현재수익률 (%)': norm_c.iloc[-1],
                '최고수익률 (%)': norm_c.max(),
                '변동성 (%)': df['Close'].pct_change().std() * np.sqrt(252) * 100
            })

        fig.update_layout(height=800, template='plotly_white', hovermode='x unified',
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

        # --- 4. 하단 상세 리포트 ---
        st.divider()
        col_l, col_r = st.columns([1, 1.2])

        with col_l:
            st.subheader("🔗 상관관계 분석")
            if len(close_list) > 1:
                corr_df = pd.concat(close_list, axis=1).pct_change().corr()
                st.plotly_chart(px.imshow(corr_df, text_auto=".2f", color_continuous_scale='RdBu_r'), use_container_width=True)
            else:
                st.info("두 개 이상의 종목을 선택하세요.")

        with col_r:
            st.subheader("📊 성과 요약")
            sum_df = pd.DataFrame(summary_list).sort_values('현재수익률 (%)', ascending=False)
            
            def highlight_fn(row):
                styles = ['' for _ in row]
                diff = row['최고수익률 (%)'] - row['현재수익률 (%)']
                idx = sum_df.columns.get_loc('현재수익률 (%)')
                if diff < 0.01: styles[idx] = 'color: red; font-weight: bold'
                elif diff <= 5.0: styles[idx] = 'color: blue; font-weight: bold'
                return styles

            st.dataframe(
                sum_df.style.apply(highlight_fn, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '변동성 (%)']),
                use_container_width=True, hide_index=True
            )
