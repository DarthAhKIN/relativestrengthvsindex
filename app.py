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

# --- 데이터 로드 (KRX 서버 에러 방어) ---
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

# --- 세션 상태 초기화 (종목 유지용) ---
if 'symbols_dict' not in st.session_state:
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

# --- 1. 사이드바: 종목 검색 및 추가 ---
st.sidebar.header("🔍 종목 검색 및 추가")

if krx_df.empty:
    st.sidebar.warning("⚠️ 국내 종목 리스트 로드 실패. 코드를 직접 입력하세요 (예: 005930)")

search_input = st.sidebar.text_input("종목명 또는 코드 입력 (엔터)", key="search_ticker")

if search_input:
    target = search_input.strip().replace(" ", "").upper()
    found = False
    
    # 한국 리스트에서 검색
    if not krx_df.empty:
        temp_df = krx_df.copy()
        temp_df['MatchName'] = temp_df['Name'].str.replace(" ", "").str.upper()
        match = temp_df[(temp_df['Code'] == target) | (temp_df['MatchName'].str.contains(target))]
        
        if not match.empty:
            res = match.iloc[0]
            full_name = f"{res['Name']} ({res['Code']})"
            ticker = f"{res['Code']}.KS" if res['Market'] == 'KOSPI' else f"{res['Code']}.KQ"
            st.session_state.symbols_dict[full_name] = ticker
            st.session_state.market_dict[full_name] = res['Market']
            st.sidebar.success(f"✅ 추가됨: {full_name}")
            found = True

    # 검색 실패 시 수동 입력 모드
    if not found:
        if target.isdigit() and len(target) == 6:
            name_label = f"한국종목({target})"
            st.session_state.symbols_dict[name_label] = f"{target}.KS"
            st.session_state.market_dict[name_label] = "KR"
            st.sidebar.info(f"📍 한국 티커로 인식: {target}.KS")
        else:
            st.session_state.symbols_dict[target] = target
            st.session_state.market_dict[target] = "Global"
            st.sidebar.info(f"🌐 해외/지수 티커로 인식: {target}")

# --- 2. 메인 화면 ---
st.title("📈 주식 & 원자재 통합 분석 리포트")

# 분석 항목 선택
available_options = list(st.session_state.symbols_dict.keys())
selected_names = st.multiselect("분석할 항목을 선택하세요", options=available_options, default=available_options[-1:])

if selected_names:
    load_days = st.sidebar.number_input("데이터 조회 기간 (영업일)", 30, 1000, 60, 10)
    
    prices_dict = {}
    close_list = [] # 상관관계용
    
    with st.spinner('데이터 수집 중...'):
        for name in selected_names:
            ticker = st.session_state.symbols_dict[name]
            try:
                # yfinance 데이터 수집 (안정성 위주)
                df = yf.download(ticker, period="5y", auto_adjust=True, progress=False)
                if not df.empty:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    df.index = pd.to_datetime(df.index).date
                    
                    # 분석 기간만큼 자르기
                    target_df = df.tail(load_days).copy()
                    prices_dict[name] = target_df
                    
                    # 상관관계용 종가 데이터
                    s_close = target_df['Close'].copy()
                    s_close.name = name
                    close_list.append(s_close)
            except:
                st.error(f"❌ {name} 데이터를 불러올 수 없습니다.")

    if prices_dict:
        # --- 3. 통합 그래프 (수익률 & MDD) ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                            subplot_titles=("🚀 누적 수익률 (%)", "📉 최고가 대비 하락률 (MDD %)"), 
                            row_heights=[0.6, 0.4])
        
        colors = px.colors.qualitative.Alphabet
        summary_data = []

        for i, name in enumerate(selected_names):
            if name not in prices_dict: continue
            df = prices_dict[name]
            color = colors[i % len(colors)]
            
            # 수익률 계산
            base_p = float(df['Close'].iloc[0])
            rets = (df['Close'] / base_p - 1) * 100
            
            # MDD 계산
            dd = (df['Close'] / df['Close'].cummax() - 1) * 100
            
            # 그래프 추가
            fig.add_trace(go.Scatter(x=df.index, y=rets, name=name, line=dict(color=color, width=2.5)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=dd, name=name, showlegend=False, fill='tozeroy', line=dict(color=color, width=1.5)), row=2, col=1)
            
            # 요약용 데이터 준비
            curr_ret = rets.iloc[-1]
            max_ret = rets.max()
            summary_data.append({
                '시장': st.session_state.market_dict.get(name, "N/A"),
                '항목': name,
                '현재수익률 (%)': curr_ret,
                '최고수익률 (%)': max_ret,
                '고점대비 하락(%)': max_ret - curr_ret,
                '변동성 (%)': df['Close'].pct_change().std() * np.sqrt(252) * 100
            })

        fig.update_layout(height=750, template='plotly_white', hovermode='x unified',
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)

        # --- 4. 하단 상세 분석 (상관관계 & 요약표) ---
        st.divider()
        col_l, col_r = st.columns([1, 1])

        with col_l:
            st.subheader("🔗 항목 간 상관관계")
            if len(close_list) > 1:
                corr_df = pd.concat(close_list, axis=1).pct_change().corr()
                fig_corr = px.imshow(corr_df, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                st.plotly_chart(fig_corr, use_container_width=True)
            else:
                st.info("2개 이상의 종목을 선택하면 상관관계를 분석합니다.")

        with col_r:
            st.subheader("📊 성과 요약")
            sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
            
            # 하이라이트 함수
            def highlight_status(row):
                diff = row['고점대비 하락(%)']
                styles = ['' for _ in row]
                idx = sum_df.columns.get_loc('현재수익률 (%)')
                
                if diff < 0.01: # 신고가
                    styles[idx] = 'color: red; font-weight: bold'
                elif diff <= 5.0: # 5% 이내 근접
                    styles[idx] = 'color: blue; font-weight: bold'
                return styles

            st.dataframe(
                sum_df.style.apply(highlight_status, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '고점대비 하락(%)', '변동성 (%)']),
                use_container_width=True, hide_index=True
            )
            
            # CSV 다운로드
            csv = sum_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 성과 요약 다운로드", csv, "summary.csv", "text/csv")
else:
    st.info("왼쪽 사이드바에서 종목을 추가하고 분석 항목을 선택해 주세요.")
