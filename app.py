import streamlit as st
import yfinance as yf
import pandas as pd
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 0. 페이지 설정
st.set_page_config(page_title="주식 분석기", layout="wide")

# --- 데이터 로드 (캐싱) ---
@st.cache_data
def load_krx_data():
    return fdr.StockListing('KRX')[['Code', 'Name', 'Market']]

krx_df = load_krx_data()

# --- 세션 상태 초기화 ---
if 'symbols_dict' not in st.session_state:
    # 초기 기본 종목 세팅
    st.session_state.symbols_dict = {
        'S&P 500': '^GSPC', 
        'Nasdaq 100': '^NDX', 
        'KOSPI 지수': '^KS11', 
        '삼성전자 (005930)': '005930.KS'
    }
if 'market_dict' not in st.session_state:
    st.session_state.market_dict = {
        'S&P 500': 'US', 'Nasdaq 100': 'US', 'KOSPI 지수': 'Index', '삼성전자 (005930)': 'KOSPI'
    }

# --- 1. 사이드바: 종목 추가 로직 ---
st.sidebar.header("🔍 종목 검색 및 추가")
search_input = st.sidebar.text_input("종목명 또는 코드 입력 후 엔터", key="search_ticker")

if search_input:
    target = search_input.strip().replace(" ", "").upper()
    
    # 한국 시장 검색 (공백 제거 후 비교)
    temp_df = krx_df.copy()
    temp_df['MatchName'] = temp_df['Name'].str.replace(" ", "").str.upper()
    
    # 1. 코드로 찾기 or 2. 이름으로 찾기
    match = temp_df[(temp_df['Code'] == target) | (temp_df['MatchName'].str.contains(target))]
    
    if not match.empty:
        res = match.iloc[0]
        full_name = f"{res['Name']} ({res['Code']})"
        ticker = f"{res['Code']}.KS" if res['Market'] == 'KOSPI' else f"{res['Code']}.KQ"
        
        # 세션에 저장
        st.session_state.symbols_dict[full_name] = ticker
        st.session_state.market_dict[full_name] = res['Market']
        st.sidebar.success(f"✅ 추가됨: {full_name}")
    else:
        # 한국 시장에 없으면 미국 티커로 간주 시도
        st.session_state.symbols_dict[search_input] = search_input
        st.session_state.market_dict[search_input] = "Global"
        st.sidebar.warning(f"⚠️ 국내 목록에 없어 해외 티커로 추가: {search_input}")

# --- 2. 메인 화면 설정 ---
st.title("📈 주식 & 원자재 통합 분석 리포트")

# 분석 대상 선택 (현재 세션에 담긴 종목들 중 선택)
available_options = list(st.session_state.symbols_dict.keys())
selected_names = st.multiselect("분석할 항목을 선택하세요", options=available_options, default=available_options[-1:])

if selected_names:
    load_days = st.sidebar.slider("데이터 조회 기간 (일)", 30, 730, 120)
    
    prices_dict = {}
    with st.spinner('데이터 다운로드 중...'):
        for name in selected_names:
            ticker = st.session_state.symbols_dict[name]
            df = yf.download(ticker, period=f"{load_days}d", auto_adjust=True, progress=False)
            if not df.empty:
                # 데이터 정리
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index).date
                prices_dict[name] = df

    if prices_dict:
        # 그래프 그리기
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=("수익률 추이 (%)", "MDD (%)"), row_heights=[0.7, 0.3])
        
        summary_data = []

        for name in selected_names:
            if name not in prices_dict: continue
            df = prices_dict[name]
            
            # 수익률 계산
            base_price = df['Close'].iloc[0]
            returns = (df['Close'] / base_price - 1) * 100
            
            # MDD 계산
            cummax = df['Close'].cummax()
            drawdown = (df['Close'] / cummax - 1) * 100
            
            # 그래프 추가
            fig.add_trace(go.Scatter(x=df.index, y=returns, name=name), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=drawdown, name=name, showlegend=False, fill='tozeroy'), row=2, col=1)
            
            # 성과 요약 데이터 수집
            curr_ret = returns.iloc[-1]
            high_ret = returns.max()
            summary_data.append({
                '시장': st.session_state.market_dict.get(name, "N/A"),
                '항목': name,
                '현재수익률 (%)': curr_ret,
                '최고수익률 (%)': high_ret,
                '최고가대비 하락': high_ret - curr_ret
            })

        fig.update_layout(height=600, template='plotly_white', hovermode='x unified')
        st.plotly_chart(fig, use_container_width=True)

        # --- 성과 요약 표 ---
        st.subheader("📊 성과 요약")
        sum_df = pd.DataFrame(summary_data)
        
        def apply_color(row):
            diff = row['최고가대비 하락']
            styles = ['' for _ in row]
            target_idx = sum_df.columns.get_loc('현재수익률 (%)')
            
            if diff < 0.01: # 사실상 최고가
                styles[target_idx] = 'color: red; font-weight: bold'
            elif diff <= 5.0: # 5% 이내 근접
                styles[target_idx] = 'color: blue; font-weight: bold'
            return styles

        st.dataframe(
            sum_df.style.apply(apply_color, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '최고가대비 하락']),
            use_container_width=True, hide_index=True
        )
else:
    st.info("왼쪽 사이드바에서 종목을 검색하여 추가하거나, 분석 항목을 선택해 주세요.")
