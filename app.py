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

# --- 1. 사이드바 설정 ---
st.sidebar.header("🔍 기본 설정")
load_days = st.sidebar.slider("데이터 로드 범위 (최대 영업일)", 30, 500, 150)

default_symbols = {
    'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Dow Jones': '^DJI', 
    'Russell 2000': '^RUT', 'KOSPI': '^KS11', 'KOSDAQ': '^KQ11',
    '금 (Gold)': 'GC=F', '은 (Silver)': 'SI=F', '구리 (Copper)': 'HG=F',
    'WTI 원유': 'CL=F', '철광석 (Iron Ore)': 'TIO=F'
}

krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "", placeholder="예: 삼성전자, TSLA, NVDA")

symbols = default_symbols.copy()
if added_stocks:
    for s in added_stocks.split(','):
        name = s.strip()
        if name: symbols[name] = get_ticker(name, krx_df)

# --- 2. 데이터 로드 ---
prices_dict = {}
with st.spinner('데이터를 수집 및 정제 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                temp_df = pd.DataFrame(index=df.index)
                for col in ['Close', 'High', 'Low']:
                    col_data = df[col]
                    temp_df[col] = col_data.iloc[:, 0] if isinstance(col_data, pd.DataFrame) else col_data
                temp_df = temp_df.reset_index()
                temp_df['Date'] = pd.to_datetime(temp_df['Date']).dt.date
                temp_df.set_index('Date', inplace=True)
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    st.title("📈 주식 & 원자재 통합 분석 리포트")
    selected_symbols = st.multiselect("분석 항목 선택", options=list(prices_dict.keys()), default=list(prices_dict.keys())[:5])
    
    available_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    min_d, max_d = min(available_dates), max(available_dates)
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, value=(max_d - pd.Timedelta(days=load_days), max_d))
    start_date, end_date = user_date[0], user_date[1]

    if selected_symbols:
        # 상관관계 계산을 위한 종가 데이터프레임 생성
        close_df = pd.concat([prices_dict[s]['Close'].rename(s) for s in selected_symbols], axis=1).loc[start_date:end_date]
        close_df = close_df.interpolate(method='linear', limit_direction='both')
        
        # --- 3. 그래프 생성 ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭", "📉 최고가 대비 하락률 (Drawdown %)"), row_heights=[0.6, 0.4])
        colors = px.colors.qualitative.Alphabet 
        all_min_dd = []

        for i, col in enumerate(selected_symbols):
            color = colors[i % len(colors)]
            df_sym = prices_dict[col].loc[start_date:end_date].copy()
            if df_sym.empty: continue
            
            base_p = df_sym['Close'].iloc[0]
            norm_c, norm_h, norm_l = (df_sym['Close']/base_p-1)*100, (df_sym['High']/base_p-1)*100, (df_sym['Low']/base_p-1)*100
            
            # 상단: 변동폭 및 수익률
            fig.add_trace(go.Scatter(x=list(norm_h.index)+list(norm_l.index)[::-1], y=list(norm_h.values)+list(norm_l.values)[::-1], fill='toself', fillcolor=color, line=dict(color='rgba(0,0,0,0)'), opacity=0.15, name=col, legendgroup=col, showlegend=False, hoverinfo='skip'), row=1, col=1)
            fig.add_trace(go.Scatter(x=norm_c.index, y=norm_c, name=col, legendgroup=col, mode='lines', line=dict(width=2.5, color=color)), row=1, col=1)
            
            # 하단: Drawdown
            dd = (df_sym['Close'] / df_sym['Close'].cummax() - 1) * 100
            all_min_dd.append(float(dd.min()))
            fig.add_trace(go.Scatter(x=dd.index, y=dd, name=col, legendgroup=col, showlegend=False, mode='lines', line=dict(width=1.5, color=color), fill='tozeroy'), row=2, col=1)

        fig.update_layout(hovermode='x unified', template='plotly_white', height=800)
        fig.update_yaxes(range=[min(all_min_dd)*1.1 if all_min_dd else -10, 2], row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # --- 4. 하단 분석 리포트 (복구 및 개선) ---
        st.divider()
        col_l, col_r = st.columns([1, 1])

        with col_l:
            st.subheader("🔗 항목 간 상관관계")
            if len(selected_symbols) > 1:
                corr = close_df.pct_change().corr()
                fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                st.plotly_chart(fig_corr, use_container_width=True)
                

        with col_r:
            st.subheader("📊 기간 성과 요약")
            summary = []
            for s in selected_symbols:
                df_s = prices_dict[s].loc[start_date:end_date]
                rets = (df_s['Close'] / df_s['Close'].iloc[0] - 1) * 100
                summary.append({'항목': s, '현재수익률 (%)': rets.iloc[-1], '최고수익률 (%)': rets.max(), '구간 MDD (%)': ((df_s['Close']/df_s['Close'].cummax()-1)*100).min()})
            
            sum_df = pd.DataFrame(summary).sort_values('현재수익률 (%)', ascending=False)
            st.dataframe(sum_df.style.format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '구간 MDD (%)']), hide_index=True, use_container_width=True)

else:
    st.error("데이터 로드 실패")
