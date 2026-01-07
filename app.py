import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np

st.set_page_config(page_title="주식 수익률 비교 분석기", layout="wide")

@st.cache_data
def get_krx_list():
    try:
        return fdr.StockListing('KRX')
    except:
        return pd.DataFrame()

def get_ticker(name, krx_df):
    if krx_df.empty: return name
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
# 데이터 수집 진행 상황 표시
with st.spinner('야후 파이낸스에서 데이터를 불러오고 있습니다...'):
    for name, sym in symbols.items():
        try:
            # 기간을 여유있게 가져옴
            df = yf.download(sym, period='1y', auto_adjust=True, progress=False)
            if not df.empty:
                df = df.tail(base_days + 5)
                df = df.reset_index()
                
                # [핵심 수정] 어떤 형태의 데이터프레임에서도 'Close' 열을 안전하게 추출
                if 'Close' in df.columns:
                    # Multi-index인 경우 첫 번째 Close 컬럼 선택
                    close_val = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
                else:
                    # 컬럼명에 'Close'가 포함된 열 찾기
                    close_cols = [c for c in df.columns if 'Close' in str(c)]
                    close_val = df[close_cols[0]] if close_cols else df.iloc[:, 1]

                tmp = pd.DataFrame({
                    'Date': pd.to_datetime(df['Date']),
                    'Close': close_val.astype(float),
                    'Symbol': name
                }).dropna()
                all_data.append(tmp)
        except Exception as e:
            st.error(f"{name} 데이터를 가져오지 못했습니다: {e}")

if all_data:
    df_main = pd.concat(all_data).reset_index(drop=True)
    st.title("📈 주식 수익률 비교 분석기")

    # 사이드바 날짜 선택기
    min_date = df_main['Date'].min().to_pydatetime()
    max_date = df_main['Date'].max().to_pydatetime()
    
    st.sidebar.subheader("📅 범위 재계산")
    selected_range = st.sidebar.date_input("분석 날짜 선택", value=(min_date, max_date))

    if isinstance(selected_range, tuple) and len(selected_range) == 2:
        start_date, end_date = pd.to_datetime(selected_range[0]), pd.to_datetime(selected_range[1])
        filtered_df = df_main[(df_main['Date'] >= start_date) & (df_main['Date'] <= end_date)].copy()
        
        if not filtered_df.empty:
            norm_list, summary_list = [], []
            for sym in filtered_df['Symbol'].unique():
                target = filtered_df[filtered_df['Symbol'] == sym].sort_values('Date').copy()
                if len(target) > 0:
                    first_val = target['Close'].iloc[0]
                    target['수익률 (%)'] = ((target['Close'] / first_val) - 1) * 100
                    norm_list.append(target)
                    
                    daily_ret = target['Close'].pct_change()
                    summary_list.append({
                        '종목': sym,
                        '수익률 (%)': target['수익률 (%)'].iloc[-1],
                        '기간변동성 (%)': daily_ret.std() * np.sqrt(len(daily_ret)) * 100,
                        '일평균변동폭 (%)': daily_ret.abs().mean() * 100
                    })

            if norm_list:
                final_df = pd.concat(norm_list)
                fig = px.line(final_df, x='Date', y='수익률 (%)', color='Symbol', markers=True,
                               title=f"재계산된 수익률 (기준일: {start_date.strftime('%Y-%m-%d')})")
                fig.add_hline(y=0, line_dash="dash", line_color="black")
                fig.update_layout(hovermode='x unified', template='plotly_white', height=600,
                                  legend=dict(x=1.02, y=1))
                st.plotly_chart(fig, use_container_width=True)

                st.subheader("📊 투자 성과 요약")
                sum_df = pd.DataFrame(summary_list).sort_values('수익률 (%)', ascending=False)
                st.table(sum_df.style.format({'수익률 (%)': '{:.2f}', '기간변동성 (%)': '{:.2f}', '일평균변동폭 (%)': '{:.2f}'}))
else:
    st.error("데이터 수집에 실패했습니다. 사이드바에서 종목을 다시 확인하거나 잠시 후 시도해주세요.")
