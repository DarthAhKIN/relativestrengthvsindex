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

# --- 2. 데이터 로드 및 정제 (High/Low 추가 수집) ---
prices_dict = {}
with st.spinner('데이터를 수집 및 정제 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                df = df.reset_index()
                df['Date'] = pd.to_datetime(df['Date']).dt.date
                # 시작일 종가 기준으로 정규화하기 위해 Close, High, Low 모두 저장
                temp_df = df[['Date', 'Close', 'High', 'Low']].copy()
                temp_df.set_index('Date', inplace=True)
                prices_dict[name] = temp_df
        except: continue

if prices_dict:
    # 날짜 기준 통합
    all_dates = pd.date_range(start=min(d.index.min() for d in prices_dict.values()), 
                              end=max(d.index.max() for d in prices_dict.values())).date
    
    # --- 3. 메인 화면 ---
    st.title("📈 주식 & 원자재 통합 분석 (수익률 변동폭 포함)")
    
    selected_symbols = st.multiselect(
        "그래프에 표시할 항목을 선택하세요",
        options=list(prices_dict.keys()),
        default=list(prices_dict.keys())[:5]
    )
    
    # 분석 범위 설정
    available_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    min_d, max_d = min(available_dates), max(available_dates)
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, value=(max_d - pd.Timedelta(days=load_days), max_d))
    
    start_date, end_date = user_date[0], user_date[1]
    
    if not selected_symbols:
        st.warning("항목을 선택해 주세요.")
    else:
        # 서브플롯 생성
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.08,
            subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭 (H-L)", "📉 최고가 대비 하락률 (Drawdown %)"),
            row_heights=[0.6, 0.4]
        )

        colors = px.colors.qualitative.Alphabet 
        all_min_dd = []

        for i, col in enumerate(selected_symbols):
            color = colors[i % len(colors)]
            df_sym = prices_dict[col].loc[start_date:end_date].copy()
            if df_sym.empty: continue
            
            # 정규화 (첫 거래일 종가 기준)
            base_price = df_sym['Close'].iloc[0]
            norm_close = (df_sym['Close'] / base_price - 1) * 100
            norm_high = (df_sym['High'] / base_price - 1) * 100
            norm_low = (df_sym['Low'] / base_price - 1) * 100

            # 1) 수익률 데이터 (상단)
            # 변동폭 영역 (High-Low)
            fig.add_trace(go.Scatter(
                x=list(norm_high.index) + list(norm_low.index)[::-1],
                y=list(norm_high.values) + list(norm_low.values)[::-1],
                fill='toself',
                fillcolor=color,
                line=dict(color='rgba(255,255,255,0)'), # 영역 테두리는 투명하게
                opacity=0.2, # 배경 영역은 아주 연하게
                name=f"{col} 변동폭",
                legendgroup=col,
                showlegend=False,
                hoverinfo='skip'
            ), row=1, col=1)

            # 종가 라인 (두껍게)
            fig.add_trace(go.Scatter(
                x=norm_close.index, y=norm_close,
                name=col, 
                legendgroup=col,
                mode='lines', line=dict(width=3, color=color),
                hovertemplate='%{x}<br>종가 수익률: %{y:.2f}%'
            ), row=1, col=1)

            # 최고 수익률 스타 마크
            max_val = norm_close.max()
            max_date = norm_close.idxmax()
            fig.add_trace(go.Scatter(
                x=[max_date], y=[max_val],
                legendgroup=col, mode='markers',
                marker=dict(size=10, symbol='star', color=color),
                showlegend=False, hoverinfo='skip'
            ), row=1, col=1)

            # 2) Drawdown 데이터 (하단)
            rolling_high = df_sym['Close'].cummax()
            drawdown = ((df_sym['Close'] / rolling_high) - 1) * 100
            all_min_dd.append(drawdown.min())
            
            fig.add_trace(go.Scatter(
                x=drawdown.index, y=drawdown,
                name=col, 
                legendgroup=col, 
                showlegend=False,
                mode='lines', line=dict(width=1.5, color=color),
                fill='tozeroy',
                hovertemplate='%{x}<br>하락률: %{y:.2f}%'
            ), row=2, col=1)

            # 신고가 다이아몬드
            is_high = drawdown.abs() < 1e-6
            df_high_pts = drawdown[is_high]
            fig.add_trace(go.Scatter(
                x=df_high_pts.index, y=df_high_pts,
                legendgroup=col, mode='markers',
                marker=dict(size=8, symbol='diamond', color=color, line=dict(width=1, color='white')),
                showlegend=False, hoverinfo='skip'
            ), row=2, col=1)

        # 레이아웃 고도화
        min_y_limit = min(all_min_dd) if all_min_dd else -10
        y_range_bottom = min(min_y_limit * 1.1, -5.0)

        fig.update_layout(
            hovermode='x unified', 
            template='plotly_white', 
            height=850,
            margin=dict(t=50, b=50),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        fig.update_xaxes(range=[start_date, end_date], showgrid=True, gridcolor='rgba(200,200,200,0.3)')
        fig.update_yaxes(title_text="수익률 (%)", row=1, col=1)
        fig.update_yaxes(title_text="하락률 (%)", range=[y_range_bottom, 2], row=2, col=1)
        
        fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5, row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)

        # --- 성과 요약 리포트 ---
        st.divider()
        st.subheader("📊 기간 성과 요약")
        summary_list = []
        for col in selected_symbols:
            df_sum = prices_dict[col].loc[start_date:end_date]
            if df_sum.empty: continue
            ret = (df_sum['Close'].iloc[-1] / df_sum['Close'].iloc[0] - 1) * 100
            max_dd = (((df_sum['Close'] / df_sum['Close'].cummax()) - 1) * 100).min()
            
            summary_list.append({
                '항목': col,
                '구간 수익률 (%)': ret,
                '구간 MDD (%)': max_dd,
                '최종가': df_sum['Close'].iloc[-1]
            })
        
        st.table(pd.DataFrame(summary_list).sort_values('구간 수익률 (%)', ascending=False))

else:
    st.error("데이터를 불러올 수 없습니다.")
