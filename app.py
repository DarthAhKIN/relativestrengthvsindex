import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date, timedelta

# 0. 페이지 기본 설정
st.set_page_config(page_title="주식 & 원자재 통합 분석기", layout="wide")

@st.cache_data
def get_krx_list():
    try: return fdr.StockListing('KRX')[['Code', 'Name', 'Market']]
    except: return pd.DataFrame()

def get_ticker(name, krx_df):
    if krx_df.empty: return name
    target_name = name.strip()
    row = krx_df[krx_df['Name'] == target_name]
    if not row.empty:
        code = row.iloc[0]['Code']
        market = row.iloc[0]['Market']
        suffix = ".KS" if market == 'KOSPI' else ".KQ"
        return f"{code}{suffix}"
    return name

# --- 1. 사이드바 설정 ---
st.sidebar.header("🔍 기본 설정")
if 'load_days' not in st.session_state:
    st.session_state.load_days = 250

load_days_input = st.sidebar.number_input(
    "데이터 로드 범위 (최대 영업일)", 
    min_value=30, max_value=1000, 
    value=st.session_state.load_days, 
    step=10
)

default_symbols = {
    'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'KOSPI': '^KS11',
    '금 (Gold)': 'GC=F', 'WTI 원유': 'CL=F'
}

krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "", placeholder="예: 삼성전자, TSLA, NVDA")

symbols = default_symbols.copy()
if added_stocks:
    input_list = [s.strip() for s in added_stocks.split(',') if s.strip()]
    for item in input_list:
        symbols[item] = get_ticker(item, krx_df)

# --- 2. 데이터 로드 및 VWAP 계산 ---
prices_dict = {}
with st.spinner('데이터를 수집 및 분석 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='5y', auto_adjust=False, progress=False) # VWAP 위해 auto_adjust=False
            if not df.empty:
                df = df.tail(load_days_input)
                # 다중 인덱스 처리 (yfinance 최신 버전 대응)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                temp_df = df[['Close', 'High', 'Low', 'Volume']].copy()
                
                # VWAP 계산: (고+저+종)/3 * 거래량의 누적합 / 거래량 누적합
                if 'Volume' in temp_df.columns and temp_df['Volume'].sum() > 0:
                    tp = (temp_df['High'] + temp_df['Low'] + temp_df['Close']) / 3
                    temp_df['VWAP'] = (tp * temp_df['Volume']).cumsum() / temp_df['Volume'].cumsum()
                else:
                    temp_df['VWAP'] = np.nan
                
                temp_df.index = pd.to_datetime(temp_df.index).date
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    # --- 3. 기간 선택 슬라이더 ---
    all_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    min_d, max_d = all_dates[0], all_dates[-1]

    st.sidebar.subheader("📅 분석 기간 선택")
    user_date = st.sidebar.slider("분석 범위 조절", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD")
    start_date, end_date = user_date[0], user_date[1]

    selected_range_df = pd.DataFrame(index=all_dates)
    actual_days = len(selected_range_df[(selected_range_df.index >= start_date) & (selected_range_df.index <= end_date)])
    st.sidebar.info(f"현재 선택된 분석 기간은 **{actual_days}** 영업일입니다.")

    st.title("📈 주식 & 원자재 통합 분석 리포트 (VWAP 포함)")
    selected_symbols = st.multiselect("분석 항목 선택", options=list(prices_dict.keys()), default=list(prices_dict.keys())[:3])

    if selected_symbols:
        def filter_by_date(df, start, end):
            return df[(df.index >= start) & (df.index <= end)]

        # --- 4. 통합 그래프 생성 ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, 
                            subplot_titles=("🚀 누적 수익률 (%) 및 VWAP", "📉 최고가 대비 하락률 (Drawdown %)"), row_heights=[0.6, 0.4])
        colors = px.colors.qualitative.Alphabet 
        all_min_dd = []

        for i, col in enumerate(selected_symbols):
            color = colors[i % len(colors)]
            df_sym = filter_by_date(prices_dict[col], start_date, end_date).copy()
            if df_sym.empty: continue
            
            base_p = df_sym['Close'].iloc[0]
            norm_c = (df_sym['Close']/base_p-1)*100
            
            # 종가 실선
            fig.add_trace(go.Scatter(x=norm_c.index, y=norm_c, name=col, legendgroup=col, mode='lines', 
                                     line=dict(width=2.5, color=color), hovertemplate='%{y:.2f}%'), row=1, col=1)
            
            # VWAP 점선 (데이터가 있는 경우에만)
            if not df_sym['VWAP'].isnull().all():
                norm_vwap = (df_sym['VWAP']/base_p-1)*100
                fig.add_trace(go.Scatter(x=norm_vwap.index, y=norm_vwap, name=f"{col} (VWAP)", legendgroup=col, 
                                         mode='lines', line=dict(width=1.5, color=color, dash='dot'), 
                                         hovertemplate='VWAP: %{y:.2f}%', showlegend=False), row=1, col=1)
            
            # 하단 Drawdown
            dd = (df_sym['Close'] / df_sym['Close'].cummax() - 1) * 100
            all_min_dd.append(float(dd.min()))
            fig.add_trace(go.Scatter(x=dd.index, y=dd, name=col, legendgroup=col, showlegend=False, mode='lines', 
                                     line=dict(width=1.5, color=color), fill='tozeroy', hovertemplate='%{y:.2f}%'), row=2, col=1)

        fig.update_layout(hovermode='x unified', template='plotly_white', height=800, 
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", range=[min(all_min_dd)*1.1 if all_min_dd else -10, 2], row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. 하단 분석 리포트 ---
        st.divider()
        col_l, col_r = st.columns([1, 1])

        with col_l:
            st.subheader("🔗 항목 간 상관관계")
            if len(selected_symbols) > 1:
                close_list = [filter_by_date(prices_dict[s], start_date, end_date)['Close'].rename(s) for s in selected_symbols]
                close_df = pd.concat(close_list, axis=1).interpolate(method='linear', limit_direction='both')
                corr = close_df.pct_change().corr()
                fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                st.plotly_chart(fig_corr, use_container_width=True)

        with col_r:
            st.subheader("📊 성과 요약")
            summary_data = []
            for s in selected_symbols:
                df_s = filter_by_date(prices_dict[s], start_date, end_date)
                if df_s.empty: continue
                daily_rets = df_s['Close'].pct_change()
                rets = (df_s['Close'] / df_s['Close'].iloc[0] - 1) * 100
                summary_data.append({
                    '항목': s,
                    '현재수익률 (%)': rets.iloc[-1],
                    '최고수익률 (%)': rets.max(),
                    '일평균 변동성 (%)': daily_rets.std() * 100,
                    '선택기간 변동률 (%)': daily_rets.std() * np.sqrt(len(df_s)) * 100
                })
            
            sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
            st.dataframe(sum_df.style.format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '일평균 변동성 (%)', '선택기간 변동률 (%)']), 
                         hide_index=True, use_container_width=True)
else:
    st.error("데이터 로드 실패")
