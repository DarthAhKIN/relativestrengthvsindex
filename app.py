import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="주식 & 원자재 분석기", layout="wide")

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

# 1. 설정 및 데이터 로드
st.sidebar.header("🔍 기본 설정")
load_days = st.sidebar.slider("데이터 로드 범위 (최대 영업일)", 30, 500, 120)

# 기본 인덱스: 기존 6대 지수 + 요청하신 5대 원자재
default_symbols = {
    'S&P 500': '^GSPC', 
    'Nasdaq 100': '^NDX', 
    'Dow Jones': '^DJI', 
    'Russell 2000': '^RUT',
    'KOSPI': '^KS11',
    'KOSDAQ': '^KQ11',
    '금 (Gold)': 'GC=F',
    '은 (Silver)': 'SI=F',
    '구리 (Copper)': 'HG=F',
    'WTI 원유': 'CL=F',
    '철광석 (Iron Ore)': 'TIO=F'  # 철도 산업과 밀접한 철광석 선물
}

krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "", placeholder="예: 삼성전자, TSLA")

symbols = default_symbols.copy()
if added_stocks:
    for s in added_stocks.split(','):
        name = s.strip()
        if name: symbols[name] = get_ticker(name, krx_df)

prices_dict = {}
with st.spinner('데이터를 정제 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                df = df.reset_index()
                df['Date'] = pd.to_datetime(df['Date']).dt.date
                close_col = 'Close' if 'Close' in df.columns else df.columns[1]
                temp_df = pd.DataFrame({
                    'Date': df['Date'],
                    name: df[close_col].iloc[:,0] if isinstance(df[close_col], pd.DataFrame) else df[close_col]
                }).set_index('Date')
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    # 데이터 통합 및 선형 보간 (휴장일 점선 효과)
    df_merged = pd.concat(prices_dict.values(), axis=1).sort_index()
    df_merged = df_merged.interpolate(method='linear', limit_direction='both')
    df_merged = df_merged.tail(load_days)
    
    st.title("📈 주식 & 원자재 수익률 분석")
    st.markdown("### 👁️ 분석 대상 선택")
    
    selected_symbols = st.multiselect(
        "그래프에 표시할 항목을 선택하세요",
        options=list(df_merged.columns),
        default=list(df_merged.columns)
    )
    
    st.sidebar.subheader("📅 분석 범위 (0% 리셋)")
    min_d, max_d = df_merged.index.min(), df_merged.index.max()
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD")

    start_date, end_date = user_date[0], user_date[1]
    
    if not selected_symbols:
        st.warning("항목을 선택해주세요.")
    else:
        filtered_prices = df_merged.loc[start_date:end_date, selected_symbols].copy()
        norm_df = (filtered_prices / filtered_prices.iloc[0] - 1) * 100
        daily_rets = filtered_prices.pct_change()
        
        st.success(f"✅ **분석 범위:** {start_date} ~ {end_date} (**총 {len(filtered_prices)} 영업일**)")
        
        fig = go.Figure()
        colors = px.colors.qualitative.Alphabet # 종목이 많아져 색상 팔레트 확장

        for i, col in enumerate(filtered_prices.columns):
            color = colors[i % len(colors)]
            y_values = norm_df[col]
            
            fig.add_trace(go.Scatter(
                x=norm_df.index, y=y_values,
                name=col, legendgroup=col,
                mode='lines', 
                line=dict(width=2.5, color=color),
                connectgaps=True 
            ))
            
            max_yield, max_date = y_values.max(), y_values.idxmax()
            fig.add_trace(go.Scatter(
                x=[max_date], y=[max_yield],
                name=col, legendgroup=col,
                mode='markers+text', text=[f"👑 {col}"],
                textposition="top center",
                marker=dict(size=10, symbol='star', color=color, line=dict(width=1, color='black')),
                showlegend=False
            ))

        fig.add_hline(y=0, line_dash="dash", line_color="black")
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showgrid=True)
        fig.update_layout(hovermode='x unified', template='plotly_white', height=650)
        st.plotly_chart(fig, use_container_width=True)

        st.divider()
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("항목 간 상관관계")
            if len(selected_symbols) > 1:
                corr_matrix = daily_rets.dropna(how='all').corr()
                fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                st.plotly_chart(fig_corr, use_container_width=True)

        with col_right:
            st.subheader("📊 성과 요약")
            summary_data = []
            for col in filtered_prices.columns:
                summary_data.append({
                    '항목': col,
                    '현재수익률 (%)': norm_df[col].iloc[-1],
                    '기간변동성 (%)': daily_rets[col].std() * np.sqrt(252) * 100
                })
            st.dataframe(pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False), hide_index=True, use_container_width=True)
else:
    st.error("데이터 로드 실패")
