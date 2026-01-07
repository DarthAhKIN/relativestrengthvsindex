with col_right:
            st.subheader("📊 성과 요약")
            summary_data = []
            for col in filtered_prices.columns:
                # 일일 수익률의 표준편차 (일일 변동성)
                daily_vol = daily_rets[col].std() * 100 
                # 연율화 변동성 (영업일 252일 기준)
                annual_vol = daily_rets[col].std() * np.sqrt(252) * 100
                
                summary_data.append({
                    '항목': col,
                    '현재수익률 (%)': norm_df[col].iloc[-1],
                    '최고수익률 (%)': norm_df[col].max(),
                    '일평균 변동성 (%)': daily_vol,
                    '연간 환산 변동성 (%)': annual_vol
                })
            
            # 데이터프레임 생성 및 소수점 2자리 포맷팅
            sum_df = pd.DataFrame(summary_data).sort_values('현재수익률 (%)', ascending=False)
            st.dataframe(
                sum_df.style.format({
                    '현재수익률 (%)': '{:.2f}',
                    '최고수익률 (%)': '{:.2f}',
                    '일평균 변동성 (%)': '{:.2f}',
                    '연간 환산 변동성 (%)': '{:.2f}'
                }), 
                hide_index=True, 
                use_container_width=True
            )
            
            st.info("💡 **변동성 안내**: 일평균 변동성이 높을수록 하루 주가 움직임이 크다는 것을 의미합니다.")
