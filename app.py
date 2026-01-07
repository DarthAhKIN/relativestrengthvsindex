import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go

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
        fig = go.Figure()
        colors = px.colors.qualitative.Plotly

        for i, col in enumerate(filtered_prices.columns):
            color = colors[i % len(colors)]
            y_values = norm_df[col]
            
            # 1. 메인 라인 그래프 추가 (그룹명 지정)
            fig.add_trace(go.Scatter(
                x=norm_df.index, y=y_values,
                name=col, 
                legendgroup=col, # 종목명을 그룹ID로 사용
                mode='lines',
                line=dict(width=2, color=color),
                hovertemplate='%{x}<br>%{y:.2f}%'
            ))
            
            # 최고점 계산
            max_yield = y_values.max()
            max_date = y_values.idxmax()
            
            # 2. 최고점 마커 추가 (동일한 legendgroup 지정)
            fig.add_trace(go.Scatter(
                x=[max_date], y=[max_yield],
                name=col, 
                legendgroup=col, # 위 라인과 동일한 그룹ID
                mode='markers+text',
                text=[f"👑 {col}"],
                textposition="top center",
                marker=dict(size=12, symbol='star', color=color, line=dict(width=1, color='black')),
                showlegend=False, # 범례 목록에는 중복 표시 안 함
                hoverinfo='skip'
            ))

            rets = daily_rets[col].dropna()
            summary_data.append({
                '종목': col,
                '최고수익률 (%)': max_yield,
                '현재수익률 (%)': y_values.iloc[-1],
                '기간변동성 (%)': rets.std() * np.sqrt(len(rets)) * 100
            })
        
        sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)

        st.title("📈 주식 수익률 & 상관계수 분석")
        st.success(f"✅ **분석 범위:** {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} (**총 {actual_business_days} 영업일**)")
        
        # 가로선 추가
        fig.add_hline(y=0, line_dash="dash", line_color="black")
        
        # 레이아웃 설정 (범례 연동 핵심 설정 추가)
        fig.update_layout(
            hovermode='x unified', template='plotly_white', height=600,
            xaxis=dict(title="날짜"), yaxis=dict(title="수익률 (%)"),
            legend=dict(
                itemclick="toggle",      # 클릭 시 토글
                itemdoubleclick="toggleothers" # 더블클릭 시 나머지 숨김
            )
        )
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("종목 간 상관관계")
            corr_matrix = daily_rets.corr()
            fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
            fig_corr.update_layout(height=450)
            st.plotly_chart(fig_corr, use_container_width=True)
            
            csv = sum_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📊 분석 결과 CSV 저장", data=csv, file_name=f'stock_analysis.csv', mime='text/csv')

        with col_right:
            st.subheader(f"📊 성과 요약")
            st.dataframe(sum_df.style.format(precision=2), hide_index=True, use_container_width=True)

else:
    st.error("데이터를 수집하지 못했습니다.")
