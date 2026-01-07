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

# --- 1. 설정 및 데이터 로드 (사이드바) ---
st.sidebar.header("🔍 기본 설정")
load_days = st.sidebar.slider("데이터 로드 범위 (최대 영업일)", 30, 500, 120)

default_symbols = {'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Dow Jones': '^DJI', 'Russell 2000': '^RUT'}
krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "삼성전자, TSLA, NVDA, AAPL, MSFT, GOOGL")

symbols = default_symbols.copy()
if added_stocks:
    for s in added_stocks.split(','):
        name = s.strip()
        if name: symbols[name] = get_ticker(name, krx_df)

# 데이터 불러오기
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
    
    # --- 2. 메인 화면 상단: 종목 선택 레이아웃 (개선 포인트) ---
    st.title("📈 주식 수익률 & 상관계수 분석")
    
    st.markdown("### 👁️ 분석할 종목 선택")
    # 멀티셀렉트를 메인 화면에 크게 배치 (스크롤 없이 가로로 확장됨)
    selected_symbols = st.multiselect(
        "그래프에 표시할 종목을 선택하세요 (여러 개 선택 가능)",
        options=list(df_merged.columns),
        default=list(df_merged.columns),
        help="종목을 클릭하여 추가하거나 X를 눌러 제외하세요."
    )
    
    # 3. 분석 범위 설정 (사이드바)
    st.sidebar.subheader("📅 분석 범위 (0% 리셋)")
    min_d = df_merged.index.min().to_pydatetime()
    max_d = df_merged.index.max().to_pydatetime()
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD")

    # 4. 데이터 필터링
    start_date, end_date = pd.to_datetime(user_date[0]), pd.to_datetime(user_date[1])
    
    if not selected_symbols:
        st.warning("위의 선택창에서 최소 하나 이상의 종목을 선택해주세요.")
    else:
        filtered_prices = df_merged.loc[start_date:end_date, selected_symbols].copy()
        actual_business_days = len(filtered_prices)
        
        # 수익률 및 지표 계산
        norm_df = (filtered_prices / filtered_prices.iloc[0] - 1) * 100
        daily_rets = filtered_prices.pct_change()
        
        # --- 5. 그래프 및 결과 출력 ---
        st.success(f"✅ **분석 범위:** {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} (**총 {actual_business_days} 영업일**)")
        
        fig = go.Figure()
        colors = px.colors.qualitative.Plotly

        for i, col in enumerate(filtered_prices.columns):
            color = colors[i % len(colors)]
            y_values = norm_df[col]
            
            # 메인 라인 및 최고점 그룹화
            fig.add_trace(go.Scatter(
                x=norm_df.index, y=y_values,
                name=col, legendgroup=col,
                mode='lines', line=dict(width=2, color=color)
            ))
            
            max_yield, max_date = y_values.max(), y_values.idxmax()
            fig.add_trace(go.Scatter(
                x=[max_date], y=[max_yield],
                name=col, legendgroup=col,
                mode='markers+text', text=[f"👑 {col}"],
                textposition="top center",
                marker=dict(size=12, symbol='star', color=color, line=dict(width=1, color='black')),
                showlegend=False
            ))

        fig.add_hline(y=0, line_dash="dash", line_color="black")
        fig.update_layout(hovermode='x unified', template='plotly_white', height=600, margin=dict(t=30))
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("종목 간 상관관계")
            if len(selected_symbols) > 1:
                corr_matrix = daily_rets.corr()
                fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                st.plotly_chart(fig_corr, use_container_width=True)
            else:
                st.info("상관관계를 보려면 2개 이상의 종목을 선택하세요.")

        with col_right:
            st.subheader("📊 성과 요약")
            summary_data = []
            for col in filtered_prices.columns:
                summary_data.append({
                    '종목': col,
                    '최고수익률 (%)': norm_df[col].max(),
                    '현재수익률 (%)': norm_df[col].iloc[-1],
                    '기간변동성 (%)': daily_rets[col].std() * np.sqrt(len(daily_rets[col].dropna())) * 100
                })
            sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
            st.dataframe(sum_df.style.format(precision=2), hide_index=True, use_container_width=True)
            
            csv = sum_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📊 분석 결과 CSV 저장", csv, "stock_analysis.csv", "text/csv")

else:
    st.error("데이터를 수집하지 못했습니다.")
