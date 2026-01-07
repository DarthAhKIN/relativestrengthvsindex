import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np

st.set_page_config(page_title="주식 수익률 분석기", layout="wide")

@st.cache_data
def get_krx_list():
    try: return fdr.StockListing('KRX')
    except: return pd.DataFrame()

def get_ticker(name, krx_df):
    if krx_df.empty: return name
    row = krx_df[krx_df['Name'] == name]
    if not row.empty:
        code = row.iloc[0]['Code']
        market = row.iloc[0]['Market']
        return f"{code}.KS" if market == 'KOSPI' else f"{code}.KQ"
    return name

# 1. 사이드바 설정
st.sidebar.header("🔍 설정")
# 기본 로드 기간은 처음 데이터를 가져오는 양을 결정합니다.
load_days = st.sidebar.slider("데이터 로드 범위 (최대 영업일)", 30, 500, 120)

symbols = {'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Dow Jones': '^DJI', 'Russell 2000': '^RUT'}
krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "삼성전자, TSLA")

if added_stocks:
    for s in added_stocks.split(','):
        name = s.strip()
        if name: symbols[name] = get_ticker(name, krx_df)

# 2. 데이터 불러오기
all_data = []
with st.spinner('데이터를 분석 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                df = df.reset_index()
                close_col = 'Close' if 'Close' in df.columns else df.columns[1]
                tmp = pd.DataFrame({
                    'Date': pd.to_datetime(df['Date']),
                    'Price': df[close_col].iloc[:,0] if isinstance(df[close_col], pd.DataFrame) else df[close_col],
                    'Symbol': name
                }).dropna()
                all_data.append(tmp.tail(load_days)) # 설정한 로드 범위만큼 가져옴
        except: continue

if all_data:
    df_main = pd.concat(all_data).reset_index(drop=True)
    
    # 3. 사이드바 날짜 슬라이더
    st.sidebar.subheader("📅 분석 범위 설정 (0% 리셋)")
    min_d = df_main['Date'].min().to_pydatetime()
    max_d = df_main['Date'].max().to_pydatetime()
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD")

    # 4. 데이터 필터링 및 재계산
    start_date, end_date = pd.to_datetime(user_date[0]), pd.to_datetime(user_date[1])
    filtered = df_main[(df_main['Date'] >= start_date) & (df_main['Date'] <= end_date)].copy()

    if not filtered.empty:
        norm_data = []
        summary = []
        
        # 선택된 범위의 실제 영업일수 계산 (종목 중 하나를 기준으로 함)
        sample_sym = filtered['Symbol'].unique()[0]
        actual_business_days = len(filtered[filtered['Symbol'] == sample_sym])

        for sym in filtered['Symbol'].unique():
            target = filtered[filtered['Symbol'] == sym].sort_values('Date').copy()
            if not target.empty:
                base_price = target['Price'].iloc[0]
                target['수익률 (%)'] = ((target['Price'] / base_price) - 1) * 100
                norm_data.append(target)
                
                rets = target['Price'].pct_change()
                summary.append({
                    '종목': sym,
                    '수익률 (%)': target['수익률 (%)'].iloc[-1],
                    '기간변동성 (%)': rets.std() * np.sqrt(len(rets)) * 100,
                    '일평균변동폭 (%)': rets.abs().mean() * 100
                })

        # 5. 화면 출력
        st.title("📈 기간별 수익률 재계산 분석기")
        
        # [핵심 추가] 현재 분석 중인 영업일수와 기간을 상단에 표시
        st.success(f"✅ **현재 분석 기간:** {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} (**총 {actual_business_days} 영업일**)")
        
        final_df = pd.concat(norm_data)
        fig = px.line(final_df, x='Date', y='수익률 (%)', color='Symbol', markers=True)
        fig.add_hline(y=0, line_dash="dash", line_color="black")
        fig.update_layout(hovermode='x unified', template='plotly_white', height=550,
                          xaxis=dict(title="날짜"), yaxis=dict(title="수익률 (%)"))
        st.plotly_chart(fig, use_container_width=True)

        st.subheader(f"📊 {actual_business_days}영업일간의 성과 요약")
        st.table(pd.DataFrame(summary).sort_values('수익률 (%)', ascending=False).style.format(precision=2))
