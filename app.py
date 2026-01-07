import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

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

# --- 2. 데이터 로드 및 정제 ---
prices_dict = {}
with st.spinner('데이터를 수집 및 정제 중입니다...'):
    for name, sym in symbols.items():
        try:
            # 기간을 충분히 넉넉하게 가져와서 필터링
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                temp_df = pd.DataFrame(index=df.index)
                for col in ['Close', 'High', 'Low']:
                    if col in df.columns:
                        col_data = df[col]
                        temp_df[col] = col_data.iloc[:, 0] if isinstance(col_data, pd.DataFrame) else col_data
                
                # 핵심 수정: 인덱스를 확실하게 datetime.date 객체로 통일
                temp_df.index = pd.to_datetime(temp_df.index).date
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    st.title("📈 주식 & 원자재 통합 분석 리포트")
    selected_symbols = st.multiselect("분석 항목 선택", options=list(prices_dict.keys()), default=list(prices_dict.keys())[:5])
    
    # 가용 날짜 범위 계산
    all_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    min_d, max_d = all_dates[0], all_dates[-1]
    
    # 사이드바 기간 선택 슬라이더
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, 
                                  value=(max_d - timedelta(days=load_days), max_d))
    start_date, end_date = user_date[0], user_date[1]

    if selected_symbols:
        # 에러 방지용 필터링 방식 변경: .loc 대신 불리언 인덱싱 사용
        def filter_by_date(df, start, end):
            return df[(df.index >= start) & (df.index <= end)]

        # 상관관계용 종가 데이터프레임 합치기
        close_list = []
        for s in selected_symbols:
            filtered = filter_by_date(prices_dict[s], start_date, end_date)
            if not filtered.empty:
                close_list.append(filtered['Close'].rename(s))
        
        if close_list:
            close_df = pd.concat(close_list, axis=1).interpolate(method='linear', limit_direction='both')
            
            # --- 3. 메인 통합 그래프 ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, 
                                subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭", "📉 최고가 대비 하락률 (Drawdown %)"), row_heights=[0.6, 0.4])
            colors = px.colors.qualitative.Alphabet 
            all_min_dd = []

            for i, col in enumerate(selected_symbols):
                color = colors[i % len(colors)]
                df_sym = filter_by_date(prices_dict[col], start_date, end_date).copy()
                if df_sym.empty: continue
                
                base_p = df_sym['Close'].iloc[0]
                norm_c, norm_h, norm_l = (df_sym['Close']/base_p-1)*100, (df_sym['High']/base_p-1)*100, (df_sym['Low']/base_p-1)*100
                
                # 상단 변동폭 그림자
                fig.add_trace(go.Scatter(x=list(norm_h.index)+list(norm_l.index)[::-1], y=list(norm_h.values)+list(norm_l.values)[::-1], 
                                         fill='toself', fillcolor=color, line=dict(color='rgba(0,0,0,0)'), opacity=0.15, 
                                         name=col, legendgroup=col, showlegend=False, hoverinfo='skip'), row=1, col=1)
                # 종가 실선
                fig.add_trace(go.Scatter(x=norm_c.index, y=norm_c, name=col, legendgroup=col, mode='lines', 
                                         line=dict(width=2.5, color=color), hovertemplate='%{y:.2f}%'), row=1, col=1)
                
                # 하단 Drawdown
                dd = (df_sym['Close'] / df_sym['Close'].cummax() - 1) * 100
                all_min_dd.append(float(dd.min()))
                fig.add_trace(go.Scatter(x=dd.index, y=dd, name=col, legendgroup=col, showlegend=False, mode='lines', 
                                         line=dict(width=1.5, color=color), fill='tozeroy', hovertemplate='%{y:.2f}%'), row=2, col=1)

            fig.update_layout(hovermode='x unified', template='plotly_white', height=800, 
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            fig.update_yaxes(ticksuffix="%", row=1, col=1)
            fig.update_yaxes(ticksuffix="%", range=[min(all_min_dd)*1.1 if all_min_dd else -10, 2], row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # --- 4. 하단 분석 리포트 ---
            st.divider()
            col_l, col_r = st.columns([1, 1])

            with col_l:
                st.subheader("🔗 항목 간 상관관계")
                if len(selected_symbols) > 1:
                    corr = close_df.pct_change().corr()
                    fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                    st.plotly_chart(fig_corr, use_container_width=True)

            with col_r:
                st.subheader("📊 성과 요약")
                summary_data = []
                for s in selected_symbols:
                    df_s = filter_by_date(prices_dict[s], start_date, end_date)
                    if df_s.empty: continue
                    daily_rets = df_s['Close'].pct_change()
                    rets = (df_s['Close'] / df_s['Close'].iloc[0] - 1) * 100
                    summary_data.append({
                        '항목': s,
                        '현재수익률 (%)': rets.iloc[-1],
                        '최고수익률 (%)': rets.max(),
                        '일평균 변동성 (%)': daily_rets.std() * 100,
                        '선택기간 변동률 (%)': daily_rets.std() * np.sqrt(len(df_s)) * 100
                    })
                
                sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
                
                def highlight_status(row):
                    curr, max_r = row['현재수익률 (%)'], row['최고수익률 (%)']
                    is_max = abs(curr - max_r) < 1e-9
                    is_near = (max_r - curr) <= 5.0
                    styles = []
                    for val in row:
                        if val == curr:
                            if is_max: styles.append('color: red; font-weight: bold')
                            elif is_near: styles.append('color: blue; font-weight: bold')
                            else: styles.append('')
                        else: styles.append('')
                    return styles

                st.dataframe(sum_df.style.apply(highlight_status, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '일평균 변동성 (%)', '선택기간 변동률 (%)']), 
                             hide_index=True, use_container_width=True)
                
                csv = sum_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(label="📥 성과 요약 CSV 다운로드", data=csv, file_name=f"performance_{start_date}_{end_date}.csv", mime="text/csv")
        else:
            st.warning("선택한 기간에 해당하는 데이터가 없습니다.")
else:
    st.error("데이터 로드 실패")
