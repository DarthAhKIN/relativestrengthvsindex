import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 0. 페이지 기본 설정
st.set_page_config(page_title="주식 & 원자재 통합 분석기", layout="wide")

@st.cache_data
def get_krx_list():
    """한국거래소 종목 리스트 수집"""
    try: 
        return fdr.StockListing('KRX')[['Code', 'Name', 'Market']]
    except: 
        return pd.DataFrame()

def get_ticker_info(input_val, krx_df):
    """이름 또는 코드를 입력받아 (티커, 시장명) 반환"""
    if krx_df.empty: 
        return input_val, "N/A"
    
    target = input_val.strip()
    
    # 1. 이름으로 검색
    row = krx_df[krx_df['Name'] == target]
    
    # 2. 이름이 없으면 코드로 검색 (숫자 6자리 대응)
    if row.empty:
        row = krx_df[krx_df['Code'] == target]
    
    if not row.empty:
        code = row.iloc[0]['Code']
        market = row.iloc[0]['Market']
        suffix = ".KS" if market == 'KOSPI' else ".KQ"
        return f"{code}{suffix}", market
    
    # 3. 한국 리스트에 없으면 미국/글로벌 티커로 간주
    return target, "US/Global"

# --- 1. 사이드바 설정 ---
st.sidebar.header("🔍 기본 설정")

# [수정] 기본 로드 범위를 60으로 설정
if 'load_days' not in st.session_state:
    st.session_state.load_days = 60

load_days_input = st.sidebar.number_input(
    "데이터 로드 범위 (최대 영업일)", 
    min_value=30, 
    max_value=1000, 
    value=st.session_state.load_days, 
    step=10
)

default_symbols = {
    'S&P 500': '^GSPC', 
    'Nasdaq 100': '^NDX', 
    'KOSPI': '^KS11', 
    '삼성전자': '005930.KS', 
    'Tesla': 'TSLA'
}

krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/코드)", "", placeholder="예: 삼성전자, 005930, TSLA")

# 종목별 시장 정보를 관리할 딕셔너리
market_info_dict = {name: "Index/Global" for name in default_symbols}
symbols = default_symbols.copy()

if added_stocks:
    input_list = [s.strip() for s in added_stocks.split(',') if s.strip()]
    for item in input_list:
        ticker, market = get_ticker_info(item, krx_df)
        symbols[item] = ticker
        market_info_dict[item] = market

# --- 2. 데이터 로드 ---
prices_dict = {}
with st.spinner('데이터를 수집 중입니다...'):
    for name, sym in symbols.items():
        try:
            # 수정주가 반영을 위해 auto_adjust=True
            df = yf.download(sym, period='5y', auto_adjust=True, progress=False)
            if not df.empty:
                # yfinance 최신 버전 다중 인덱스 방지
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                df = df.tail(load_days_input)
                df.index = pd.to_datetime(df.index).date
                prices_dict[name] = df
        except: continue

if prices_dict:
    # --- 3. 기간 선택 슬라이더 ---
    all_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    min_d, max_d = all_dates[0], all_dates[-1]

    st.sidebar.subheader("📅 분석 기간 선택")
    user_date = st.sidebar.slider(
        "분석 범위 조절",
        min_value=min_d,
        max_value=max_d,
        value=(min_d, max_d),
        format="YYYY-MM-DD"
    )
    start_date, end_date = user_date[0], user_date[1]

    # 실제 표시되는 영업일 수 안내
    selected_range_df = pd.DataFrame(index=all_dates)
    actual_days = len(selected_range_df[(selected_range_df.index >= start_date) & (selected_range_df.index <= end_date)])
    st.sidebar.info(f"현재 선택된 분석 기간은 **{actual_days}** 영업일입니다.")

    st.title("📈 주식 & 원자재 통합 분석 리포트")
    selected_symbols = st.multiselect("분석 항목 선택", options=list(prices_dict.keys()), default=list(prices_dict.keys())[:3])

    if selected_symbols:
        def filter_by_date(df, start, end):
            return df[(df.index >= start) & (df.index <= end)]

        # --- 4. 통합 그래프 생성 ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, 
                            subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭", "📉 최고가 대비 하락률 (Drawdown %)"), 
                            row_heights=[0.6, 0.4])
        
        colors = px.colors.qualitative.Alphabet 
        all_min_dd = []

        for i, col in enumerate(selected_symbols):
            color = colors[i % len(colors)]
            df_sym = filter_by_date(prices_dict[col], start_date, end_date).copy()
            if df_sym.empty: continue
            
            base_p = df_sym['Close'].iloc[0]
            norm_c = (df_sym['Close'] / base_p - 1) * 100
            norm_h = (df_sym['High'] / base_p - 1) * 100
            norm_l = (df_sym['Low'] / base_p - 1) * 100
            
            # 상단 수익률 및 고/저가 음영
            fig.add_trace(go.Scatter(
                x=list(norm_h.index) + list(norm_l.index)[::-1], 
                y=list(norm_h.values) + list(norm_l.values)[::-1], 
                fill='toself', fillcolor=color, line=dict(color='rgba(0,0,0,0)'), 
                opacity=0.15, name=col, legendgroup=col, showlegend=False, hoverinfo='skip'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=norm_c.index, y=norm_c, name=col, legendgroup=col, mode='lines', 
                line=dict(width=2.5, color=color), hovertemplate='%{y:.2f}%'
            ), row=1, col=1)
            
            # 하단 MDD
            dd = (df_sym['Close'] / df_sym['Close'].cummax() - 1) * 100
            all_min_dd.append(float(dd.min()))
            fig.add_trace(go.Scatter(
                x=dd.index, y=dd, name=col, legendgroup=col, showlegend=False, mode='lines', 
                line=dict(width=1.5, color=color), fill='tozeroy', hovertemplate='%{y:.2f}%'
            ), row=2, col=1)

        fig.update_layout(hovermode='x unified', template='plotly_white', height=800, 
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", range=[min(all_min_dd)*1.1 if all_min_dd else -10, 2], row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. 성과 요약 리포트 ---
        st.divider()
        st.subheader("📊 성과 요약")
        summary_data = []
        for s in selected_symbols:
            df_s = filter_by_date(prices_dict[s], start_date, end_date)
            if df_s.empty: continue
            
            rets = (df_s['Close'] / df_s['Close'].iloc[0] - 1) * 100
            daily_rets = df_s['Close'].pct_change()
            
            summary_data.append({
                '시장': market_info_dict.get(s, "US/Global"),
                '항목': s,
                '현재수익률 (%)': rets.iloc[-1],
                '최고수익률 (%)': rets.max(),
                '일평균 변동성 (%)': daily_rets.std() * 100,
                '선택기간 변동률 (%)': daily_rets.std() * np.sqrt(len(df_s)) * 100
            })
        
        sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
        
        # 스타일링 함수: 전고점 근처 확인
        def highlight_status(row):
            curr, max_r = row['현재수익률 (%)'], row['최고수익률 (%)']
            is_max = abs(curr - max_r) < 1e-9
            is_near = (max_r - curr) <= 5.0
            styles = ['' for _ in row]
            idx = sum_df.columns.get_loc('현재수익률 (%)')
            if is_max: styles[idx] = 'color: red; font-weight: bold'
            elif is_near: styles[idx] = 'color: blue; font-weight: bold'
            return styles

        st.dataframe(
            sum_df.style.apply(highlight_status, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '일평균 변동성 (%)', '선택기간 변동률 (%)']), 
            hide_index=True, use_container_width=True
        )
        
        csv = sum_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="📥 성과 요약 CSV 다운로드", data=csv, file_name=f"performance_{start_date}_{end_date}.csv", mime="text/csv")
else:
    st.error("데이터 로드 실패 또는 데이터가 없습니다.")
