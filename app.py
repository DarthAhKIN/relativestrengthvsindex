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

# --- 캐싱된 데이터 로드 ---
@st.cache_data
def get_krx_list():
    """한국거래소 종목 리스트 수집"""
    try: 
        return fdr.StockListing('KRX')[['Code', 'Name', 'Market']]
    except: 
        return pd.DataFrame()

def get_ticker_info(input_val, krx_df):
    """
    [개선된 검색 로직]
    1. .KS, .KQ 등 접미사가 있어도 코드를 인식
    2. 띄어쓰기가 달라도 이름을 인식 (예: KODEX은선물 -> KODEX 은선물)
    """
    if krx_df.empty: 
        return input_val, "N/A", input_val
    
    # 입력값 정리 (좌우 공백 제거)
    target = input_val.strip()
    
    # [1단계] 코드로 검색 (접미사 제거 후 비교)
    # 예: "144600.KS" -> "144600"으로 변환하여 검색
    target_code = target.split('.')[0]  # 점(.) 뒤에 있는 건 날림
    
    row = pd.DataFrame()
    # 숫자로만 구성되어 있다면 코드 검색 시도
    if target_code.isdigit():
        row = krx_df[krx_df['Code'] == target_code]

    # [2단계] 이름으로 검색 (기존 로직)
    if row.empty:
        row = krx_df[krx_df['Name'] == target]
        
    # [3단계] 부분 일치 및 '공백 무시' 검색 (핵심 수정)
    if row.empty:
        # 3-1. 일반적인 포함 검색 (예: "삼성" -> "삼성전자")
        mask = krx_df['Name'].str.contains(target, case=False, regex=False)
        if mask.any():
            row = krx_df[mask].head(1)
        
        # 3-2. 띄어쓰기 무시 검색 (예: "KODEX은선물" -> "KODEX 은선물")
        if row.empty:
            # 입력값에서 모든 공백 제거
            target_nospace = target.replace(" ", "").upper()
            
            # 데이터프레임의 이름들도 공백을 제거하고 비교해야 함
            # (속도를 위해 전체를 변환하기보다, 반복문으로 빠르게 찾음)
            found_idx = None
            for idx, name in zip(krx_df.index, krx_df['Name']):
                if target_nospace in name.replace(" ", "").upper():
                    found_idx = idx
                    break
            
            if found_idx is not None:
                row = krx_df.loc[[found_idx]]

    # 검색 성공 시 데이터 반환
    if not row.empty:
        code = row.iloc[0]['Code']
        name = row.iloc[0]['Name']
        market = row.iloc[0]['Market']
        
        # 야후 파이낸스용 접미사 결정
        suffix = ".KS" if market == 'KOSPI' else ".KQ"
        
        # 실제 데이터 요청에 쓸 티커 (예: 144600.KS)
        yf_ticker = f"{code}{suffix}"
        
        # 화면에 보여줄 정식 명칭 (예: KODEX 은선물(H) (144600))
        display_name = f"{name} ({code})"
        
        return yf_ticker, market, display_name
    
    # 4. 끝내 못 찾으면 해외 종목으로 간주
    return target, "US/Global", target

# --- 1. 사이드바 설정 ---
st.sidebar.header("🔍 기본 설정")

if 'load_days' not in st.session_state:
    st.session_state.load_days = 60

load_days_input = st.sidebar.number_input(
    "데이터 로드 범위 (최대 영업일)", 
    min_value=30, 
    max_value=1000, 
    value=st.session_state.load_days, 
    step=10
)

# 기본 지수 및 주요 자산 리스트
default_symbols = {
    'S&P 500': '^GSPC', 'Nasdaq 100': '^NDX', 'Dow Jones': '^DJI', 
    'Russell 2000': '^RUT', 'KOSPI': '^KS11', 'KOSDAQ': '^KQ11',
    '금 (Gold)': 'GC=F', '은 (Silver)': 'SI=F', '구리 (Copper)': 'HG=F',
    'WTI 원유': 'CL=F', '철광석 (Iron Ore)': 'TIO=F'
}

krx_df = get_krx_list()
added_stocks = st.sidebar.text_input("종목 추가 (한글명/코드/부분명)", "", placeholder="예: 삼성전자, 144600.KS, KODEX은선물")

# 종목별 시장 정보를 관리할 딕셔너리
market_info_dict = {name: "Index/Global" for name in default_symbols}
symbols = default_symbols.copy()

if added_stocks:
    input_list = [s.strip() for s in added_stocks.split(',') if s.strip()]
    for item in input_list:
        # [핵심] 개선된 get_ticker_info 함수 호출
        ticker, market, display_name = get_ticker_info(item, krx_df)
        
        # 딕셔너리의 키(Key)를 '정식 명칭'으로 저장하여 UI 통일
        symbols[display_name] = ticker
        market_info_dict[display_name] = market

# --- 2. 데이터 로드 및 정제 ---
prices_dict = {}
with st.spinner('데이터를 수집 중입니다...'):
    for name, sym in symbols.items():
        try:
            df = yf.download(sym, period='5y', auto_adjust=True, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                df = df.loc[:, ~df.columns.duplicated()].copy()
                df = df[~df.index.duplicated(keep='first')]
                
                df = df.tail(load_days_input)
                df.index = pd.to_datetime(df.index).date
                prices_dict[name] = df
        except: continue

if prices_dict:
    # --- 3. 기간 선택 슬라이더 ---
    all_dates = sorted(list(set().union(*(d.index for d in prices_dict.values()))))
    if not all_dates:
        st.error("데이터 로드에 실패했습니다. (검색된 종목의 데이터가 없거나 티커 오류일 수 있습니다)")
        st.stop()

    min_d, max_d = all_dates[0], all_dates[-1]

    st.sidebar.subheader("📅 분석 기간 선택")
    user_date = st.sidebar.slider("분석 범위 조절", min_value=min_d, max_value=max_d, value=(min_d, max_d), format="YYYY-MM-DD")
    start_date, end_date = user_date[0], user_date[1]

    # 실제 표시되는 영업일 수 안내
    selected_range_df = pd.DataFrame(index=all_dates)
    actual_days = len(selected_range_df[(selected_range_df.index >= start_date) & (selected_range_df.index <= end_date)])
    st.sidebar.info(f"현재 선택된 분석 기간은 **{actual_days}** 영업일입니다.")

    st.title("📈 주식 & 원자재 통합 분석 리포트")
    selected_symbols = st.multiselect("분석 항목 선택", options=list(prices_dict.keys()), default=list(prices_dict.keys())[:5])

    if selected_symbols:
        def filter_by_date(df, start, end):
            return df[(df.index >= start) & (df.index <= end)]

        # --- 4. 통합 그래프 생성 ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, 
                            subplot_titles=("🚀 누적 수익률 (%) 및 당일 변동폭", "📉 최고가 대비 하락률 (Drawdown %)"), 
                            row_heights=[0.6, 0.4])
        
        colors = px.colors.qualitative.Alphabet 
        all_min_dd = []
        close_list = []

        for i, col in enumerate(selected_symbols):
            color = colors[i % len(colors)]
            df_sym = filter_by_date(prices_dict[col], start_date, end_date).copy()
            if df_sym.empty: continue
            
            try:
                base_p = float(df_sym['Close'].iloc[0])
            except: continue

            norm_c = (df_sym['Close'] / base_p - 1) * 100
            norm_h = (df_sym['High'] / base_p - 1) * 100
            norm_l = (df_sym['Low'] / base_p - 1) * 100
            
            s_close = df_sym['Close'].copy()
            s_close.name = str(col)
            close_list.append(s_close)
            
            fig.add_trace(go.Scatter(
                x=list(norm_h.index) + list(norm_l.index)[::-1], 
                y=list(norm_h.values) + list(norm_l.values)[::-1], 
                fill='toself', fillcolor=color, line=dict(color='rgba(0,0,0,0)'), 
                opacity=0.15, name=col, legendgroup=col, showlegend=False, hoverinfo='skip'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(
                x=norm_c.index, y=norm_c, name=col, legendgroup=col, mode='lines', 
                line=dict(width=2.5, color=color), hovertemplate='%{y:.2f}%'
            ), row=1, col=1)
            
            dd = (df_sym['Close'] / df_sym['Close'].cummax() - 1) * 100
            all_min_dd.append(float(dd.min()))
            fig.add_trace(go.Scatter(
                x=dd.index, y=dd, name=col, legendgroup=col, showlegend=False, mode='lines', 
                line=dict(width=1.5, color=color), fill='tozeroy', hovertemplate='%{y:.2f}%'
            ), row=2, col=1)

        fig.update_layout(hovermode='x unified', template='plotly_white', height=800, 
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig.update_yaxes(ticksuffix="%", row=1, col=1)
        fig.update_yaxes(ticksuffix="%", range=[min(all_min_dd)*1.1 if all_min_dd else -10, 2], row=2, col=1)
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. 하단 분석 리포트 ---
        st.divider()
        col_l, col_r = st.columns([1, 1])

        with col_l:
            st.subheader("🔗 항목 간 상관관계")
            if len(close_list) > 1:
                close_df = pd.concat(close_list, axis=1).interpolate(method='linear', limit_direction='both')
                corr = close_df.pct_change().corr()
                fig_corr = px.imshow(corr, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1])
                st.plotly_chart(fig_corr, use_container_width=True)
            else:
                st.info("상관관계를 보려면 2개 이상의 종목을 선택하세요.")

        with col_r:
            st.subheader("📊 성과 요약")
            summary_data = []
            for s in selected_symbols:
                df_s = filter_by_date(prices_dict[s], start_date, end_date)
                if df_s.empty: continue
                
                base_val = float(df_s['Close'].iloc[0])
                rets = (df_s['Close'] / base_val - 1) * 100
                
                summary_data.append({
                    '시장': market_info_dict.get(s, "US/Global"),
                    '항목': s,
                    '현재수익률 (%)': float(rets.iloc[-1]),
                    '최고수익률 (%)': float(rets.max()),
                    '일평균 변동성 (%)': float(df_s['Close'].pct_change().std() * 100),
                    '선택기간 변동률 (%)': float(df_s['Close'].pct_change().std() * np.sqrt(len(df_s)) * 100)
                })
            
            sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
            
            def highlight_status(row):
                curr = row['현재수익률 (%)']
                max_r = row['최고수익률 (%)']
                diff = max_r - curr
                
                styles = ['' for _ in row]
                idx = sum_df.columns.get_loc('현재수익률 (%)')
                
                if diff <= 0.01: 
                    styles[idx] = 'color: red; font-weight: bold'
                elif diff <= 5.0:
                    styles[idx] = 'color: blue; font-weight: bold'
                    
                return styles

            st.dataframe(
                sum_df.style.apply(highlight_status, axis=1).format('{:.2f}', subset=['현재수익률 (%)', '최고수익률 (%)', '일평균 변동성 (%)', '선택기간 변동률 (%)']), 
                hide_index=True, use_container_width=True
            )
            
            csv = sum_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(label="📥 성과 요약 CSV 다운로드", data=csv, file_name=f"performance_{start_date}_{end_date}.csv", mime="text/csv")
else:
    st.error("데이터 로드 실패 또는 데이터가 없습니다.")
