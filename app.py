import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np

# 페이지 설정
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

# 사이드바 설정
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

# 데이터 로드
all_data = []
for name, sym in symbols.items():
    try:
        # auto_adjust=True로 데이터 구조 단순화
        df = yf.download(sym, period='1y', auto_adjust=True, progress=False)
        if not df.empty:
            df = df.tail(base_days + 1)
            # [수정포인트] 인덱스(Date)를 컬럼으로 빼내기
            df = df.reset_index()
            
            # 종가(Close) 컬럼 추출 (MultiIndex 대응)
            if 'Close' in df.columns:
                close_data = df['Close']
            else:
                close_data = df.iloc[:, 1] # 첫 번째 데이터 컬럼 사용

            tmp = pd.DataFrame({
                'Date': pd.to_datetime(df['Date']),
                'Close': close_data.astype(float),
                'Symbol': name
            })
            all_data.append(tmp)
    except Exception as e:
        continue

if all_data:
    df_main = pd.concat(all_data).reset_index(drop=True)
    
    st.title("📈 주식 수익률 비교 분석기")
    st.info("💡 하단 슬라이더를 조절하면 시작점이 0%로 자동 재계산됩니다.")

    # 날짜 범위 선택
    min_date = df_main['Date'].min().to_pydatetime()
    max_date = df_main['Date'].max().to_pydatetime()
    selected_range = st.sidebar.date_input("분석 날짜 범위", value=(min_date, max_date))

    if len(selected_range) == 2:
        start_date, end_date = pd.to_datetime(selected_range[0]), pd.to_datetime(selected_range[1])
        
        # 필터링
        mask = (df_main['Date'] >= start_date) & (df_main['Date'] <= end_date)
        filtered_df = df_main.loc[mask].copy()
        
        if not filtered_df.empty:
            norm_list, summary_list = [], []
            for sym in filtered_df['Symbol'].unique():
                target = filtered_df[filtered_df['Symbol'] == sym].sort_values('Date')
                if len(target) > 0:
                    first_val = target['Close'].iloc[0]
                    target['수익률 (%)'] = ((target['Close'] / first_val) - 1) * 100
                    norm_list.append(target)
                    
                    # 지표 계산
                    daily_ret = target['Close'].pct_change()
                    summary_list.append({
                        '종목': sym,
                        '수익률 (%)': target['수익률 (%)'].iloc[-1],
                        '기간변동성 (%)': daily_ret.std() * np.sqrt(len(daily_ret)) * 100,
                        '일평균변동폭 (%)': daily_ret.abs().mean() * 100
                    })

            final_df = pd.concat(norm_list)
            
            # 그래프
            fig_norm = px.line(final_df, x='Date', y='수익률 (%)', color='Symbol', markers=True,
                               title=f"재계산된 수익률 (기준일: {start_date.strftime('%Y-%m-%d')})")
            fig_norm.add_hline(y=0, line_dash="dash", line_color="black")
            fig_norm.update_layout(hovermode='x unified', template='plotly_white',
                                  legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02))
            st.plotly_chart(fig_norm, use_container_width=True)

            # 요약 표
            st.subheader("📊 투자 성과 요약")
            sum_df = pd.DataFrame(summary_list).sort_values('수익률 (%)', ascending=False)
            st.table(sum_df.style.format({'수익률 (%)': '{:.2f}', '기간변동성 (%)': '{:.2f}', '일평균변동폭 (%)': '{:.2f}'}))
else:
    st.warning("데이터를 불러오는 중입니다. 잠시만 기다려주세요.")
