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

# --- 2. 데이터 로드 (고가, 저가, 종가 포함) ---
prices_dict = {}
with st.spinner('데이터를 수집 및 정제 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='2y', auto_adjust=True, progress=False)
            if not df.empty:
                # 멀티인덱스 방지 및 필요한 컬럼만 추출
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
    
    selected_symbols = st.multiselect(
        "그래프에 표시할 항목을 선택하세요",
        options=list(prices_dict.keys()),
        default=list(prices_dict.keys())[:5]
    )
    
    # 날짜 범위 설정
    available_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    min_d, max_d = min(available_dates), max(available_dates)
    user_date = st.sidebar.slider("기간 선택", min_value=min_d, max_value=max_d, 
                                  value=(max_d - pd.Timedelta(days=load_days), max_d), format="YYYY-MM-DD")
    
    start_date, end_date = user_date[0], user_date[1]
    
    if not selected_symbols:
        st.warning("항목을 선택해 주세요.")
    else:
        # 통합 그래프 생성 (Subplots)
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.1,
            subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭 (H-L)", "📉 최고가 대비 하락률 (Drawdown %)"),
            row_heights=[0.6, 0.4]
        )

        colors = px.colors.qualitative.Alphabet 
        all_min_dd = []

        for i, col in enumerate(selected_symbols):
            color = colors[i % len(colors)]
            # 선택한 기간의 데이터 필터링
            df_sym = prices_dict[col].loc[start_date:end_date].copy()
            if df_sym.empty: continue
            
            # 수익률 계산 (시작일 종가 기준 정규화)
            base_price = df_sym['Close'].iloc[0]
            norm_close = (df_sym['Close'] / base_price - 1) * 100
            norm_high = (df_sym['High'] / base_price - 1) * 100
            norm_low = (df_sym['Low'] / base_price - 1) * 100

            # 1) 수익률 데이터 (상단)
            # 변동폭 영역 (High-Low Fill)
            fig.add_trace(go.Scatter(
                x=list(norm_high.index) + list(norm_low.index)[::-1],
                y=list(norm_high.values) + list(norm_low.values)[::-1],
                fill='toself',
                fillcolor=color,
                line=dict(color='rgba(255,255,255,0)'),
                opacity=0.15, # 배경 영역 투명도
                name=f"{col} 변동폭",
                legendgroup=col,
                showlegend=False,
                hoverinfo='skip'
            ), row=1, col=1)

            # 종가 실선
            fig.add_trace(go.Scatter(
                x=norm_close.index, y=norm_close,
                name=col, 
                legendgroup=col,
                mode='lines', line=dict(width=2.5, color=color),
                hovertemplate='%{x}<br>종가 수익률: %{y:.2f}%'
            ), row=1, col=1)

            # 최고점 별표
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
            
            # 에러 방지: 단일 float 값으로 변환
            min_val = float(drawdown.min())
            all_min_dd.append(min_val)
            
            fig.add_trace(go.Scatter(
                x=drawdown.index, y=drawdown,
                name=col, 
                legendgroup=col, 
                showlegend=False,
                mode='lines', line=dict(width=1.5, color=color),
                fill='tozeroy',
                hovertemplate='%{x}<br>하락률: %{y:.2f}%'
            ), row=2, col=1)

            # 신고가 포인트
            is_high = drawdown.abs() < 1e-6
            df_high_pts = drawdown[is_high]
            fig.add_trace(go.Scatter(
                x=df_high_pts.index, y=df_high_pts,
                legendgroup=col, mode='markers',
                marker=dict(size=8, symbol='diamond', color=color, line=dict(width=1, color='white')),
                showlegend=False, hoverinfo='skip'
            ), row=2, col=1)

        # 레이아웃 설정
        min_y_limit = min(all_min_dd) if all_min_dd else -10
        y_range_bottom = min(min_y_limit * 1.1, -5.0)

        fig.update_layout(
            hovermode='x unified', 
            template='plotly_white', 
            height=850,
            margin=dict(t=50, b=50),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )

        fig.update_xaxes(range=[start_date, end_date], showgrid=True)
        fig.update_yaxes(title_text="수익률 (%)", row=1, col=1)
        fig.update_yaxes(title_text="하락률 (%)", range=[y_range_bottom, 2], autorange=False, row=2, col=1)
        
        fig.add_hline(y=0, line_dash="dash", line_color="black", row=1, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5, row=2, col=1)

        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # --- 5. 성과 리포트 ---
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.subheader("📊 성과 요약")
            summary_data = []
            for col in selected_symbols:
                df_sum = prices_dict[col].loc[start_date:end_date]
                if df_sum.empty: continue
                ret = (df_sum['Close'].iloc[-1] / df_sum['Close'].iloc[0] - 1) * 100
                mdd = (((df_sum['Close'] / df_sum['Close'].cummax()) - 1) * 100).min()
                summary_data.append({
                    '항목': col,
                    '구간 수익률 (%)': ret,
                    '구간 MDD (%)': mdd
                })
            
            sum_df = pd.DataFrame(summary_data).sort_values('구간 수익률 (%)', ascending=False)
            st.dataframe(sum_df.style.format({'구간 수익률 (%)': '{:.2f}', '구간 MDD (%)': '{:.2f}'}), 
                         hide_index=True, use_container_width=True)

        with col_right:
            st.subheader("💡 분석 팁")
            st.info("""
            - **진한 선**: 시작일 대비 누적 수익률입니다.
            - **연한 그림자**: 당일의 고가와 저가 범위(변동성)를 보여줍니다.
            - **범례 클릭**: 특정 종목을 클릭하면 상/하단 그래프에서 동시에 제거/표시됩니다.
            """)
else:
    st.error("데이터 수집에 실패했습니다.")
