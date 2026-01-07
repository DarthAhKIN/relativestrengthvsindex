import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np

st.set_page_config(page_title="주식 수익률 & 상관계수 분석기", layout="wide")

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
load_days = st.sidebar.slider("데이터 로드 범위 (최대 영업일)", 30, 500, 120)

symbols = {'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Dow Jones': '^DJI', 'Russell 2000': '^RUT'}
krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "삼성전자, TSLA")

if added_stocks:
    for s in added_stocks.split(','):
        name = s.strip()
        if name: symbols[name] = get_ticker(name, krx_df)

# 2. 데이터 불러오기
prices_dict = {}
with st.spinner('데이터를 분석 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                df = df.reset_index()
                close_col = 'Close' if 'Close' in df.columns else df.columns[1]
                temp_df = pd.DataFrame({
                    'Date': pd.to_datetime(df['Date']),
                    name: df[close_col].iloc[:,0] if isinstance(df[close_col], pd.DataFrame) else df[close_col]
                }).set_index('Date')
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    # 날짜 기준 데이터 통합
    df_merged = pd.concat(prices_dict.values(), axis=1).sort_index().tail(load_days)
    
    # 3. 사이드바 날짜 슬라이더
    st.sidebar.subheader("📅 분석 범위 설정 (0% 리셋)")
    min_d = df_merged.index.min().to_pydatetime()
    max_d = df_merged.index.max().to_pydatetime()
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD")

    # 4. 데이터 필터링 및 계산
    start_date, end_date = pd.to_datetime(user_date[0]), pd.to_datetime(user_date[1])
    filtered_prices = df_merged.loc[start_date:end_date].copy()

    if not filtered_prices.empty:
        actual_business_days = len(filtered_prices)
        norm_df = (filtered_prices / filtered_prices.iloc[0] - 1) * 100
        daily_rets = filtered_prices.pct_change()
        
        summary_data = []
        for col in filtered_prices.columns:
            rets = daily_rets[col].dropna()
            summary_data.append({
                '종목': col,
                '수익률 (%)': norm_df[col].iloc[-1],
                '기간변동성 (%)': rets.std() * np.sqrt(len(rets)) * 100,
                '일평균변동폭 (%)': rets.abs().mean() * 100
            })
        sum_df = pd.DataFrame(summary_data).sort_values('수익률 (%)', ascending=False)

        # --- 화면 레이아웃 구성 ---
        st.title("📈 주식 수익률 & 상관계수 분석")
        st.success(f"✅ **분석 범위:** {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} (**총 {actual_business_days} 영업일**)")
        
        # [상단] 수익률 그래프
        st.subheader("수익률 추이 (0% 기준 재계산)")
        plot_df = norm_df.reset_index().melt(id_vars='Date', var_name='Symbol', value_name='수익률 (%)')
        fig = px.line(plot_df, x='Date', y='수익률 (%)', color='Symbol', markers=True)
        fig.add_hline(y=0, line_dash="dash", line_color="black")
        fig.update_layout(hovermode='x unified', template='plotly_white', height=600)
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # [하단] 2열 배치
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("종목 간 상관관계")
            corr_matrix = daily_rets.corr()
            fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
            fig_corr.update_layout(height=450)
            st.plotly_chart(fig_corr, use_container_width=True)
            
            # 다운로드 버튼 추가
            csv = sum_df.to_csv(index=False).encode('utf-8-sig') # 한글 깨짐 방지 utf-8-sig
            st.download_button(
                label="📊 분석 결과 CSV로 저장",
                data=csv,
                file_name=f'stock_analysis_{start_date.strftime("%Y%m%d")}.csv',
                mime='text/csv',
            )

        with col_right:
            st.subheader(f"📊 {actual_business_days}영업일 성과 요약")
            st.dataframe(sum_df.style.format(precision=2), hide_index=True, use_container_width=True)
            st.info("※ **기간변동성**: 선택한 전체 기간의 누적 위험도\n\n※ **일평균변동폭**: 하루 평균 주가 움직임의 크기")

else:
    st.error("데이터를 수집하지 못했습니다.")
