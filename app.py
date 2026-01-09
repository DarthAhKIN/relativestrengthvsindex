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
load_days_input = st.sidebar.number_input("데이터 로드 범위 (최대 영업일)", min_value=30, max_value=1000, value=250, step=10)

default_symbols = {'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'KOSPI': '^KS11', '삼성전자': '005930.KS', 'Tesla': 'TSLA'}
krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/티커)", "", placeholder="예: 삼성전자, TSLA, NVDA")

symbols = default_symbols.copy()
if added_stocks:
    for s in [x.strip() for x in added_stocks.split(',') if x.strip()]:
        symbols[s] = get_ticker(s, krx_df)

# --- 2. 데이터 로드 및 일일 VWAP 계산 ---
prices_dict = {}
with st.spinner('데이터 수집 중...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='5y', auto_adjust=False, progress=False)
            if not df.empty:
                df = df.tail(load_days_input)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                temp_df = df[['Close', 'High', 'Low', 'Volume']].copy()
                
                # [수정] 누적합이 아닌 당일 기준 VWAP 계산 (Typical Price)
                # 일봉 기준이므로 당일의 (H+L+C)/3을 해당일의 거래량 가중치로 간주
                # (사실상 일봉에서는 Typical Price 자체가 해당 일의 가중평균값 역할을 합니다)
                if 'Volume' in temp_df.columns and temp_df['Volume'].sum() > 0:
                    temp_df['Daily_VWAP'] = (temp_df['High'] + temp_df['Low'] + temp_df['Close']) / 3
                else:
                    temp_df['Daily_VWAP'] = np.nan
                
                temp_df.index = pd.to_datetime(temp_df.index).date
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    # --- 3. 날짜 및 종목 선택 ---
    all_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    min_d, max_d = all_dates[0], all_dates[-1]
    user_date = st.sidebar.slider("분석 범위", min_value=min_d, max_value=max_d, value=(min_d, max_d))
    start_date, end_date = user_date[0], user_date[1]

    st.title("📈 주식 & 원자재 통합 분석 리포트")
    selected_symbols = st.multiselect("분석 항목 선택", options=list(prices_dict.keys()), default=list(prices_dict.keys())[:3])

    if selected_symbols:
        def filter_by_date(df, start, end): return df[(df.index >= start) & (df.index <= end)]

        # --- 4. 그래프 생성 ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, 
                            subplot_titles=("🚀 수익률 (%) 및 일일 VWAP", "📉 최고가 대비 하락률 (DD %)"), row_heights=[0.6, 0.4])
        colors = px.colors.qualitative.Alphabet 
        all_min_dd = []

        for i, col in enumerate(selected_symbols):
            color = colors[i % len(colors)]
            df_sym = filter_by_date(prices_dict[col], start_date, end_date).copy()
            if df_sym.empty: continue
            
            base_p = df_sym['Close'].iloc[0]
            norm_c = (df_sym['Close']/base_p-1)*100
            
            # 종가 실선
            fig.add_trace(go.Scatter(x=norm_c.index, y=norm_c, name=col, legendgroup=col, 
                                     line=dict(width=2.5, color=color), hovertemplate='%{y:.2f}%'), row=1, col=1)
            
            # [변경] 일일 VWAP 점선
            if not df_sym['Daily_VWAP'].isnull().all():
                norm_vwap = (df_sym['Daily_VWAP']/base_p-1)*100
                fig.add_trace(go.Scatter(x=norm_vwap.index, y=norm_vwap, name=f"{col} VWAP", legendgroup=col, 
                                         line=dict(width=1, color=color, dash='dot'), 
                                         hovertemplate='VWAP: %{y:.2f}%', showlegend=False), row=1, col=1)
            
            dd = (df_sym['Close'] / df_sym['Close'].cummax() - 1) * 100
            all_min_dd.append(dd.min())
            fig.add_trace(go.Scatter(x=dd.index, y=dd, name=col, legendgroup=col, showlegend=False, 
                                     line=dict(width=1.5, color=color), fill='tozeroy'), row=2, col=1)

        fig.update_layout(hovermode='x unified', template='plotly_white', height=800)
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", range=[min(all_min_dd)*1.1 if all_min_dd else -10, 2], row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. 성과 요약 리포트 (기존 로직 유지) ---
        st.divider()
        summary_data = []
        for s in selected_symbols:
            df_s = filter_by_date(prices_dict[s], start_date, end_date)
            if df_s.empty: continue
            rets = (df_s['Close'] / df_s['Close'].iloc[0] - 1) * 100
            summary_data.append({
                '항목': s, '현재수익률 (%)': rets.iloc[-1], '최고수익률 (%)': rets.max(),
                '일평균 변동성 (%)': df_s['Close'].pct_change().std() * 100,
                '선택기간 변동률 (%)': df_s['Close'].pct_change().std() * np.sqrt(len(df_s)) * 100
            })
        
        sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
        
        def highlight_status(row):
            curr, max_r = row['현재수익률 (%)'], row['최고수익률 (%)']
            is_max, is_near = abs(curr - max_r) < 1e-9, (max_r - curr) <= 5.0
            return ['color: red; font-weight: bold' if is_max and i==1 else 
                    'color: blue; font-weight: bold' if is_near and not is_max and i==1 else '' 
                    for i, v in enumerate(row)]

        st.subheader("📊 성과 요약")
        st.dataframe(sum_df.style.apply(highlight_status, axis=1).format('{:.2f}', subset=sum_df.columns[1:]), 
                     hide_index=True, use_container_width=True)
        
        csv = sum_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 성과 요약 CSV 다운로드", csv, f"performance_{start_date}_{end_date}.csv", "text/csv")
