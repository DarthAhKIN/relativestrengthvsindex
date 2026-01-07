import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np

st.set_page_config(page_title="주식 수익률 비교 분석기", layout="wide")

@st.cache_data
def get_krx_list():
    return fdr.StockListing('KRX')

def get_ticker(name, krx_df):
    row = krx_df[krx_df['Name'] == name]
    if not row.empty:
        code = row.iloc[0]['Code']
        market = row.iloc[0]['Market']
        return f"{code}.KS" if market == 'KOSPI' else f"{code}.KQ"
    return name

st.sidebar.header("🔍 설정")
base_days = st.sidebar.slider("분석 기간 (영업일)", 10, 252, 60)

symbols = {
    'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX',
    'Dow Jones': '^DJI', 'Russell 2000': '^RUT'
}

st.sidebar.subheader("➕ 종목 추가")
krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("한글 종목명 또는 티커 (쉼표로 구분)", "삼성전자, TSLA, BTC-USD")

if added_stocks:
    for s in added_stocks.split(','):
        name = s.strip()
        if name:
            symbols[name] = get_ticker(name, krx_df)

all_data = []
for name, sym in symbols.items():
    df = yf.download(sym, period='1y', progress=False)
    if not df.empty:
        df = df.tail(base_days + 1)
        close_col = df['Close']
        series = close_col.iloc[:, 0] if isinstance(close_col, pd.DataFrame) else close_col
        all_data.append(pd.DataFrame({'Date': df.index, 'Close': series, 'Symbol': name}))

if all_data:
    df_main = pd.concat(all_data)
    st.title("📈 주식 수익률 비교 분석기")
    
    min_date, max_date = df_main['Date'].min().to_pydatetime(), df_main['Date'].max().to_pydatetime()
    selected_range = st.slider("분석 범위 선택 (시작점이 0%로 재계산됩니다)", min_value=min_date, max_value=max_date, value=(min_date, max_date))

    filtered_df = df_main[(df_main['Date'] >= selected_range[0]) & (df_main['Date'] <= selected_range[1])].copy()
    
    norm_list, summary_list = [], []
    for sym in filtered_df['Symbol'].unique():
        target = filtered_df[filtered_df['Symbol'] == sym].sort_values('Date')
        if not target.empty:
            first_val = target['Close'].iloc[0]
            target['수익률 (%)'] = ((target['Close'] / first_val) - 1) * 100
            norm_list.append(target)
            daily_ret = target['Close'].pct_change()
            summary_list.append({
                '종목': sym, '수익률 (%)': target['수익률 (%)'].iloc[-1],
                '기간변동성 (%)': daily_ret.std() * np.sqrt(len(daily_ret)) * 100,
                '일평균변동폭 (%)': daily_ret.abs().mean() * 100
            })

    fig_norm = px.line(pd.concat(norm_list), x='Date', y='수익률 (%)', color='Symbol', markers=True)
    fig_norm.add_hline(y=0, line_dash="dash", line_color="black")
    st.plotly_chart(fig_norm, use_container_width=True)

    st.subheader("📊 투자 성과 요약")
    st.table(pd.DataFrame(summary_list).sort_values('수익률 (%)', ascending=False))
