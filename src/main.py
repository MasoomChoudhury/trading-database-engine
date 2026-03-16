import time
import schedule
import datetime
from fetcher.upstox_client import UpstoxFetcher
from processor.indicator_engine import CalculationEngine
from database.supabase_client import RemoteDBWatcher

def resample_ohlc(data, interval='5min'):
    if not data or len(data) == 0:
        return []
    
    import pandas as pd
    # Upstox returns: [timestamp, open, high, low, close, volume, oi]
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Cast to numeric
    for col in ['open', 'high', 'low', 'close', 'volume', 'oi']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Resample
    # labeling='left' and closed='left' is standard for financial data (e.g., 09:15 bar contains 09:15-09:19)
    resampled = df.resample(interval, label='left', closed='left').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'oi': 'last'
    }).dropna()
    
    # Convert back to list of lists format for the rest of the engine
    result = []
    for timestamp, row in resampled.iterrows():
        # Format timestamp back to string
        ts_str = timestamp.strftime('%Y-%m-%dT%H:%M:%S+05:30')
        result.append([
            ts_str,
            row['open'],
            row['high'],
            row['low'],
            row['close'],
            int(row['volume']),
            int(row['oi'])
        ])
    return result

def run_5min_sync_job():
    print(f"--- Starting Sync Job at {datetime.datetime.now()} ---")
    
    # 1. Initialize Modules
    fetcher = UpstoxFetcher()
    processor = CalculationEngine()
    supabase = RemoteDBWatcher()
    
    # Configuration
    instrument_key = "NSE_INDEX|Nifty 50" # Example
    
    current_time = datetime.datetime.now()
    # Format time for Upstox (YYYY-MM-DD format usually for historical, or handle intraday limits)
    # For a real implementation, you'd calculate the exact 5-min boundary timestamp.
    
    # 2. Fetch Data
    print(f"Fetching 1-minute candles for {instrument_key} (to be resampled)...")
    raw_1min_candles = fetcher.get_intraday_candles(instrument_key=instrument_key, interval="1minute")
    
    # Resample to 5-minute
    candles = resample_ohlc(raw_1min_candles, '5min')
    
    if not candles:
        print("Warning: No candles retrieved. Skipping cycle.")
        return
        
    def get_next_nifty_expiry(current_date):
        # Nifty Options typically expire on Thursdays
        days_ahead = 3 - current_date.weekday()
        if days_ahead < 0: # Target day already happened this week
            days_ahead += 7
        return (current_date + datetime.timedelta(days_ahead)).strftime("%Y-%m-%d")

    # Get Options Chain for GEX
    print("Fetching option chains for Net GEX calculation...")
    expiry_date = get_next_nifty_expiry(current_time.date())
    option_chain_data = fetcher.get_option_chain("NSE_INDEX|Nifty 50", expiry_date)
    
    # Resolve Front-Month Nifty Futures Instrument Key
    print("Resolving Active Nifty Future Contract...")
    future_instrument_key = "NSE_FO|NIFTY_FUT" # Fallback placeholder
    try:
        expiries = fetcher.get_expiries("NSE_INDEX|Nifty 50")
        if expiries:
            # First expiry is sometimes weekly options, we need the monthly futures expiry.
            # In India, futures expire on the last Thursday of the month.
            # Upstox returns all expiries sorted. The get_future_contracts API 
            # only needs *a* valid expiry date that has a future contract.
            
            # Let's iterate through the next few nearest expiries to find the active future contract
            selected_expiry = None
            for exp in expiries[:4]: # Looking at max 1 month ahead
                f_contracts = fetcher.get_future_contracts("NSE_INDEX|Nifty 50", exp)
                if f_contracts and len(f_contracts) > 0:
                    # Found a valid future contract for this expiry!
                    future_instrument_key = f_contracts[0]['instrument_key']
                    selected_expiry = exp
                    print(f"✅ Found Active Future: {f_contracts[0]['trading_symbol']} ({future_instrument_key})")
                    break
                    
            if not selected_expiry:
                print("⚠ Could not resolve active future contract from nearest expiries.")
    except Exception as e:
        print(f"Error resolving Nifty Futures Key: {e}")

    print(f"Fetching 1-minute candles for Futures: {future_instrument_key} (to be resampled)...")
    raw_fut_1min_candles = fetcher.get_intraday_candles(instrument_key=future_instrument_key, interval="1minute")
    fut_candles = resample_ohlc(raw_fut_1min_candles, '5min')
    
    # 3. Process Data
    print("Processing standard indicators...")
    import pandas as pd
    
    # Convert UPSTOX raw list of lists into DataFrame
    # Example format: [timestamp, open, high, low, close, volume, oi]
    try:
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        
        # Ensure chronological order (oldest to newest) for accurate indicator calculation
        df['timestamp_dt'] = pd.to_datetime(df['timestamp'])
        df.sort_values('timestamp_dt', inplace=True)
        df.drop(columns=['timestamp_dt'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # Calculate Volume SMA for Momentum Burst
        df['vol_sma_20'] = df['volume'].rolling(window=20).mean()
        
        # Calculate Technicals
        df = processor.compute_standard_indicators(df)
        
        # Process futures data if available
        fut_df = pd.DataFrame()
        if fut_candles:
            fut_df = pd.DataFrame(fut_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            fut_df['close'] = pd.to_numeric(fut_df['close'])
            fut_df['timestamp_dt'] = pd.to_datetime(fut_df['timestamp'])
            fut_df.sort_values('timestamp_dt', inplace=True)
            fut_df.drop(columns=['timestamp_dt'], inplace=True)
            fut_df.reset_index(drop=True, inplace=True)
            
        # Net GEX is calculated after determining latest_close
        
        # Calculate CPR Status & Width & Key Intraday Levels
        # To get previous day's data, we make a quick historical fetch
        cpr_status = "Unknown"
        cpr_width = "Unknown"
        key_levels = {}
        today_str = current_time.strftime('%Y-%m-%d')
        # We need data from at least 30 days ago to ensure we capture 20 full trading days for Monthly SMA
        from_date_str = (current_time - datetime.timedelta(days=35)).strftime('%Y-%m-%d')
        
        print(f"Fetching previous daily candles from {from_date_str} for CPR & Monthly Basis calculation...")
        daily_candles = fetcher.get_historical_candles(instrument_key, "day", today_str, from_date_str)
        fut_daily_candles = fetcher.get_historical_candles(future_instrument_key, "day", today_str, from_date_str)
        
        fut_daily_df = pd.DataFrame()
        if fut_daily_candles:
            fut_daily_df = pd.DataFrame(fut_daily_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            fut_daily_df['close'] = pd.to_numeric(fut_daily_df['close'])
            fut_daily_df['timestamp_dt'] = pd.to_datetime(fut_daily_df['timestamp'])
            fut_daily_df.sort_values('timestamp_dt', inplace=True)
            
        spot_daily_df = pd.DataFrame()
        if daily_candles:
            spot_daily_df = pd.DataFrame(daily_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            spot_daily_df['close'] = pd.to_numeric(spot_daily_df['close'])
            spot_daily_df['timestamp_dt'] = pd.to_datetime(spot_daily_df['timestamp'])
            spot_daily_df.sort_values('timestamp_dt', inplace=True)
            
        if daily_candles and len(daily_candles) >= 1:
            # daily_candles comes back ordered newest to oldest usually, we need the *previous* trading day.
            # Upstox returns: [timestamp, open, high, low, close, volume, oi]
            # Depending on if today's candle is returned, we need to pick the one strictly before today.
            prev_day_candle = None
            for candle in daily_candles:
                candle_date = pd.to_datetime(candle[0]).date()
                if candle_date < current_time.date():
                    prev_day_candle = candle
                    break
            
            if prev_day_candle:
                prev_high = float(prev_day_candle[2])
                prev_low = float(prev_day_candle[3])
                prev_close = float(prev_day_candle[4])
                
                # We need the current price, which we get from the latest 5-min candle
                if len(df) > 1:
                    latest_close = float(df.iloc[-1]['close']) 
                else:
                    latest_close = float(df.iloc[0]['close'])
                    
                cpr_status = processor.compute_cpr_status(latest_close, prev_high, prev_low, prev_close)
                cpr_width = processor.compute_cpr_width(prev_high, prev_low, prev_close)
                key_levels = processor.compute_key_intraday_levels(latest_close, prev_high, prev_low)
            else:
                cpr_status = "Error: Prev Day Not Found"
                cpr_width = "Error: Prev Day Not Found"
                key_levels = {"error": "Prev Day Not Found"}
                
        # Extract the latest fully closed 5-min candle
        # Since df is sorted oldest to newest, df.iloc[-1] is the newest (likely forming)
        # and df.iloc[-2] is the latest fully closed candle.
        if len(df) > 1:
            latest = df.iloc[-2].to_dict() 
        else:
            latest = df.iloc[-1].to_dict()
            
        print(f"Latest metrics processed: Close={latest.get('close')}, RSI={latest.get('rsi_14')}")
        
        # 4. Sync Database
        print("Upserting final row to Supabase...")
        synthetic_ohlc = {
            'open': latest.get('open'),
            'high': latest.get('high'),
            'low': latest.get('low'),
            'close': latest.get('close'),
            'volume': latest.get('volume')
        }
        
        # Calculate VWAP Status, Momentum Burst, Institutional Context, Volume Profile, Tech Indicators & Derived Features
        vwap_status = processor.compute_vwap_status_dict(latest_close, latest.get('vwap'))
        momentum_burst = processor.compute_momentum_burst_dict(
            current_volume=latest.get('volume', 0), 
            avg_volume=latest.get('vol_sma_20', 0),
            current_timestamp=pd.to_datetime(latest['timestamp'])
        )
        volume_profile = processor.compute_volume_profile_dict(df, pd.to_datetime(latest['timestamp']))
        derived_features = processor.compute_derived_features_dict(df, pd.to_datetime(latest['timestamp']))
        technical_indicators = processor.compute_technical_indicators_dict(latest)
        meta = processor.compute_meta_dict(pd.to_datetime(latest['timestamp']), latest_close)
        
        # Calculate real Net Gamma Exposure using Upstox active chain data
        net_gex = processor.compute_net_gex(option_chain_data, latest_close)
        
        # We mapped prev_high and prev_low earlier from the daily candle for CPR
        # For safety if daily_candles fetch failed, we default to 0.0
        pdh = prev_high if 'prev_high' in locals() else 0.0
        pdl = prev_low if 'prev_low' in locals() else 0.0
        pdc = prev_close if 'prev_close' in locals() else 0.0
        
        catalyst_context = processor.compute_catalyst_context_dict(
            df=df,
            current_timestamp=pd.to_datetime(latest['timestamp']),
            prev_day_close=pdc
        )
        
        institutional_context = processor.compute_institutional_context_dict(
            current_price=latest_close,
            sma_200=latest.get('sma_200', 0.0),
            prev_day_high=pdh,
            prev_day_low=pdl
        )
        
        # Fetch Top 5 Heavyweights Live Quotes
        print("Fetching Top 5 Index Heavyweights...")
        heavyweights_keys = [
            "NSE_EQ|INE040A01034", # HDFCBANK
            "NSE_EQ|INE002A01018", # RELIANCE
            "NSE_EQ|INE090A01021", # ICICIBANK
            "NSE_EQ|INE009A01021", # INFY
            "NSE_EQ|INE467B01029", # TCS
        ]
        hm_quotes = fetcher.get_market_quote(heavyweights_keys)
        heavyweight_vs_vwap = processor.compute_heavyweight_vs_vwap(hm_quotes)
        
        # Fetch Live VIX
        print("Fetching Live India VIX...")
        vix_quote = fetcher.get_market_quote(["NSE_INDEX|India VIX"])
        vix_data = vix_quote.get("NSE_INDEX|India VIX", {})
        
        index_macro = processor.compute_index_macro_dict(vix_data)
        
        # Calculate IV Rank (VIX 20-Day Percentile)
        live_vix = float(index_macro.get("vix", {}).get("level", 0.0))
        historical_vix_array = supabase.get_historical_vix_array(days_back=20)
        
        if live_vix > 0 and len(historical_vix_array) > 0:
            from scipy import stats
            iv_rank_percentile = stats.percentileofscore(historical_vix_array, live_vix, kind='weak')
            index_macro["iv_rank_20d"] = round(iv_rank_percentile, 2)
            
            # Map LLM option spread parameters based on IV Rank 
            if iv_rank_percentile >= 80:
                index_macro["volatility_strategy"] = "High IV Rank (80+). Premium is Expensive. Favor Option Selling (Credit Spreads/Iron Condors)."
            elif iv_rank_percentile <= 20:
                index_macro["volatility_strategy"] = "Low IV Rank (20-). Premium is Cheap. Favor Option Buying (Debit Spreads/Naked Calls/Puts)."
            else:
                index_macro["volatility_strategy"] = "Average IV. Mixed Strategy Environment."
                
            # Quick 5-Day Volatility Trend (Expanding vs Crushing)
            recent_5d_vix = supabase.get_historical_vix_array(days_back=5)
            if len(recent_5d_vix) > 0:
                avg_5d_vix = sum(recent_5d_vix) / len(recent_5d_vix)
                vix_5d_percentile = stats.percentileofscore(recent_5d_vix, live_vix, kind='weak')
                
                if live_vix > (avg_5d_vix * 1.05):
                    index_macro["vix_5d_trend"] = "Expanding (Fear Increasing)"
                elif live_vix < (avg_5d_vix * 0.95):
                    index_macro["vix_5d_trend"] = "Crushing (Complacency)"
                else:
                    index_macro["vix_5d_trend"] = "Neutral (Sideways)"
                    
                # Explicit Prompt Signal
                if vix_5d_percentile <= 10:
                    index_macro["vix_state"] = f"VIX is {live_vix}, which is in the bottom 10% of the recent range, indicating extreme complacency."
                elif vix_5d_percentile >= 90:
                    index_macro["vix_state"] = f"VIX is {live_vix}, which is in the top 10% of the recent range, indicating extreme fear/panic."
                else:
                    index_macro["vix_state"] = f"VIX is {live_vix}, oscillating normally."
                
        else:
            index_macro["iv_rank_20d"] = None
            index_macro["volatility_strategy"] = "Insufficient Volatility History"
            index_macro["vix_5d_trend"] = "Insufficient Volatility History"
            index_macro["vix_state"] = "Insufficient Volatility History"
            
        vix_lvl = index_macro.get('vix', {}).get('level', 0.0)
        vix_chg_pts = index_macro.get('vix', {}).get('change', 0.0)
        vix_chg_pct = 0.0
        if vix_lvl > 0 and (vix_lvl - vix_chg_pts) > 0:
            vix_chg_pct = (vix_chg_pts / (vix_lvl - vix_chg_pts)) * 100
            
        vix_vel = index_macro.get('vix_velocity', 'Neutral')
        vix_context = f"VIX at {vix_lvl} ({vix_chg_pct:.2f}% trend, Trend: {vix_vel})"
            
        # Cost of Carry Evaluation
        cost_of_carry = processor.compute_cost_of_carry_dict(
            spot_5m_df=df,
            fut_5m_df=fut_df,
            spot_daily_df=spot_daily_df,
            fut_daily_df=fut_daily_df
        )
        
        # True VWAP on Futures
        true_vwap = processor.compute_true_vwap_dict(fut_5m_df=fut_df)
        # Options Macro (Net GEX and Live Max Pain)
        max_pain = processor.compute_max_pain(option_chain_data, latest_close)
        
        # Historical Max Pain Shift tracking via Database
        timestamp_24h_ago = (current_time - datetime.timedelta(days=1)).isoformat()
        timestamp_48h_ago = (current_time - datetime.timedelta(days=2)).isoformat()
        
        mp_24h = supabase.get_historical_max_pain(timestamp_24h_ago)
        mp_48h = supabase.get_historical_max_pain(timestamp_48h_ago)
        
        # Extract the live strike
        live_max_pain = max_pain.get("max_pain_strike", 0.0)
        
        # Calculate shifts safely, handling Day 1-3 empty database outputs
        shift_24h = live_max_pain - mp_24h if mp_24h > 0.0 else None
        shift_48h = mp_24h - mp_48h if (mp_24h > 0.0 and mp_48h > 0.0) else None
        
        # Attach the historical shift context
        max_pain["historical_shift"] = {
            "max_pain_24h_ago": mp_24h if mp_24h > 0.0 else None,
            "max_pain_48h_ago": mp_48h if mp_48h > 0.0 else None,
            "shift_24h": shift_24h,
            "shift_48h": shift_48h,
            "trend_signal": "Upward Floor Shift" if shift_24h and shift_24h > 0 else 
                            ("Downward Floor Shift" if shift_24h and shift_24h < 0 else "Stable Floor or Missing Data")
        }
        
        # PCR and 20-Day Percentile
        pcr_data = processor.compute_options_pcr(option_chain_data)
        live_pcr = pcr_data.get("live_pcr", 0.0)
        
        historical_pcr_array = supabase.get_historical_pcr_array(days_back=20)
        pcr_percentile = None
        
        if live_pcr > 0 and len(historical_pcr_array) > 0:
            from scipy import stats # Ensure we have stats available
            # Calculate the percentile of the current PCR against history
            pcr_percentile = stats.percentileofscore(historical_pcr_array, live_pcr, kind='weak')
            
        pcr_data["historical_20d_percentile"] = round(pcr_percentile, 2) if pcr_percentile is not None else None
        
        # Attach semantic signal for LLM
        if pcr_percentile is not None:
            if pcr_percentile >= 90:
                pcr_data["leverage_signal"] = "Historically Over-leveraged on Puts (High Short Covering Rally Probability)"
            elif pcr_percentile <= 10:
                pcr_data["leverage_signal"] = "Historically Over-leveraged on Calls (High Long Unwinding Risk)"
            else:
                pcr_data["leverage_signal"] = "Neutral Leverage"
        else:
             pcr_data["leverage_signal"] = "Insufficient History"
             
        # Extract Gamma Walls (Highest Call / Put OI Blocks)
        gamma_walls = processor.compute_gamma_walls(option_chain_data, latest_close)
        
        # Extract Gamma Flip Point (Zero transition)
        gamma_flip_point = processor.compute_gamma_flip_point(option_chain_data, latest_close)
        
        # Calculate Distance to Gamma Flip
        distance_to_gamma = "N/A"
        if gamma_flip_point > 0:
            diff_pts = gamma_flip_point - latest_close
            diff_pct = (diff_pts / latest_close) * 100
            sign = "+" if diff_pts > 0 else ""
            distance_to_gamma = f"{sign}{diff_pts:.2f} pts ({sign}{diff_pct:.2f}%)"
            
        # Determine Market Internals (Aligned Flow)
        vwap_val = latest.get('vwap', 0.0)
        if latest_close > vwap_val and net_gex > 0:
            market_internals = "Aligned Flow (Bullish)"
        elif latest_close < vwap_val and net_gex < 0:
            market_internals = "Aligned Flow (Bearish)"
        else:
            market_internals = "Mixed Flow"
            
        # Fetch Term Structure Liquidity & ATM Implied Volatility
        atm_strike = round(latest_close / 50) * 50
        
        print("Fetching full Option Contracts array to isolate next 5 expiries...")
        all_contracts = fetcher.get_option_contracts("NSE_INDEX|Nifty 50")
        
        valid_expiries = set()
        for c in all_contracts:
            expiry_str = c.get('expiry')
            if expiry_str:
                try:
                    if isinstance(expiry_str, str) and "-" in expiry_str:
                        dt = pd.to_datetime(expiry_str).date()
                    else:
                        dt = pd.to_datetime(int(expiry_str), unit='ms').date()
                    if dt >= current_time.date():
                        valid_expiries.add(dt.strftime('%Y-%m-%d'))
                except Exception:
                    pass
                    
        next_5_expiries = sorted(list(valid_expiries))[:5]
        front_expiry = next_5_expiries[0] if next_5_expiries else None

        atm_keys_for_iv = []
        term_structure_keys = []
        term_structure_meta = {}
        
        for c in all_contracts:
            if float(c.get('strike_price', 0.0)) == atm_strike:
                expiry_str = c.get('expiry')
                if expiry_str:
                    try:
                        if isinstance(expiry_str, str) and "-" in expiry_str:
                            dt = pd.to_datetime(expiry_str).date()
                        else:
                            dt = pd.to_datetime(int(expiry_str), unit='ms').date()
                        formatted_expiry = dt.strftime('%Y-%m-%d')
                        
                        key = c.get('instrument_key')
                        if key:
                            if formatted_expiry in next_5_expiries:
                                term_structure_keys.append(key)
                                term_structure_meta[key] = c
                                
                            if formatted_expiry == front_expiry:
                                atm_keys_for_iv.append(key)
                    except Exception:
                        pass
                        
        atm_iv = None
        if atm_keys_for_iv:
            print(f"Fetching Live Option Greeks for ATM Strike {atm_strike} (Front Expiry)...")
            greeks = fetcher.get_option_greeks(atm_keys_for_iv)
            ivs = []
            for k, greek_data in greeks.items():
                iv = greek_data.get('iv', None)
                if iv and float(iv) > 0:
                    ivs.append(float(iv) * 100) # Upstox returns as decimal
            if ivs:
                atm_iv = round(sum(ivs) / len(ivs), 2)
                
        term_structure_liquidity = []
        if term_structure_keys:
            print(f"Fetching vectorized market quotes for Term Structure Liquidity ({len(term_structure_keys)} instruments)...")
            market_quotes = fetcher.get_market_quote(term_structure_keys)
            term_structure_liquidity = processor.compute_term_structure_liquidity(market_quotes, term_structure_meta)

        # Fetch Intraday Options Chain (Front Expiry, ATM ± 5 Strikes -> 11 Strikes, Calls & Puts)
        options_intraday_chain = []
        if front_expiry:
            target_strikes = [atm_strike + (offset * 50) for offset in range(-5, 6)]
            intraday_keys_map = {} # Mapping: key -> (offset, option_type)
            
            for c in all_contracts:
                expiry_str = c.get('expiry')
                if expiry_str:
                    try:
                        if isinstance(expiry_str, str) and "-" in expiry_str:
                            dt = pd.to_datetime(expiry_str).date()
                        else:
                            dt = pd.to_datetime(int(expiry_str), unit='ms').date()
                            
                        # Only target front expiry
                        if dt.strftime('%Y-%m-%d') == front_expiry:
                            strike = float(c.get('strike_price', 0.0))
                            if strike in target_strikes:
                                offset = int((strike - atm_strike) / 50)
                                opt_type = c.get('instrument_type', '')
                                key = c.get('instrument_key')
                                if key:
                                    intraday_keys_map[key] = (offset, opt_type)
                    except Exception:
                        pass
                        
            if intraday_keys_map:
                intraday_keys_list = list(intraday_keys_map.keys())
                print(f"Fetching Live Option Greeks and Market Quotes for all {len(intraday_keys_map)} AI Matrix strikes...")
                
                intraday_greeks = fetcher.get_option_greeks(intraday_keys_list)
                intraday_quotes = fetcher.get_market_quote(intraday_keys_list)
                
                print(f"Fetching 5-minute intraday candles for front-expiry options instruments via ThreadPoolExecutor...")
                from concurrent.futures import ThreadPoolExecutor, as_completed
                
                def fetch_candle(key):
                    # Upstox supports interval='5minute' intraday fetch
                    return key, fetcher.get_intraday_candles(key, "5minute")
                    
                # Use max_workers=5 to avoid brutalizing the API rate limit while maintaining speed
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(fetch_candle, k): k for k in intraday_keys_map.keys()}
                    for future in as_completed(futures):
                        k = futures[future]
                        try:
                            key, candles = future.result()
                            if candles:
                                offset, opt_type = intraday_keys_map[key]
                                
                                # Enrich with Greeks & Quotes
                                greek_data = intraday_greeks.get(key, {}) if intraday_greeks else {}
                                quote_data = intraday_quotes.get(key, {}) if intraday_quotes else {}
                                
                                strike = atm_strike + (offset * 50)
                                ltp = quote_data.get('last_price', 0.0)
                                
                                # Calculate Intrinsic & Time Value
                                intrinsic_value = 0.0
                                if opt_type == 'CE':
                                    intrinsic_value = max(0, latest_close - strike)
                                elif opt_type == 'PE':
                                    intrinsic_value = max(0, strike - latest_close)
                                    
                                time_value = max(0, ltp - intrinsic_value) if ltp else 0.0
                                
                                options_intraday_chain.append({
                                    "strike_price": strike,
                                    "strike_offset": offset,
                                    "option_type": opt_type,
                                    "instrument_key": key,
                                    "ltp": ltp,
                                    "intrinsic_value": round(intrinsic_value, 2),
                                    "time_value": round(time_value, 2),
                                    "greeks": {
                                        "delta": greek_data.get("delta", 0.0),
                                        "theta": greek_data.get("theta", 0.0),
                                        "gamma": greek_data.get("gamma", 0.0),
                                        "vega": greek_data.get("vega", 0.0),
                                        "iv": greek_data.get("iv", 0.0)
                                    },
                                    "liquidity": {
                                        "volume": quote_data.get("volume", 0),
                                        "oi": quote_data.get("oi", 0.0),
                                        "oi_day_high": quote_data.get("oi_day_high", 0.0)
                                    },
                                    "candles_5m": candles
                                })
                        except Exception as e:
                            print(f"Error fetching intraday candles for {k}: {e}")
            
        indicators = {
            'rsi_14': latest.get('rsi_14'),
            'vwap': latest.get('vwap'),
            'ema_20': latest.get('ema_20'),
            'ema_50': latest.get('ema_50'),
            'opening_range_status': processor.compute_opening_range_status(df, pd.to_datetime(latest['timestamp'])),
            'cpr_relationship': cpr_status,
            'cpr_width': cpr_width,
            'vwap_status': vwap_status,
            'vwap_context': processor.compute_vwap_context_dict(fut_df, latest_close),
            'key_intraday_levels': key_levels,
            'momentum_burst': momentum_burst,
            'institutional_context': institutional_context,
            'catalyst_context': catalyst_context,
            'index_macro': index_macro,
            'cost_of_carry': cost_of_carry,
            'true_vwap': true_vwap,
            'volume_profile': volume_profile,
            'derived_features': derived_features,
            'technical_indicators': technical_indicators,
            'meta': meta,
            'max_pain': max_pain,
            'pcr': pcr_data,
            'gamma_walls': gamma_walls,
            'gamma_flip_point': gamma_flip_point,
            'distance_to_gamma': distance_to_gamma,
            'heavyweight_vs_vwap': heavyweight_vs_vwap,
            'market_internals': market_internals,
            'vix_context': vix_context,
            'atm_iv': atm_iv,
            'term_structure_liquidity': term_structure_liquidity,
            'options_decision_matrix': options_intraday_chain
        }
        
        # Use exact timestamp of the candle
        candle_timestamp = pd.to_datetime(latest['timestamp'])
        
        payload = processor.generate_5min_sync_payload(
            current_timestamp=candle_timestamp,
            synthetic_ohlc=synthetic_ohlc,
            net_gex=net_gex,
            indicators_dict=indicators
        )
        
        result = supabase.upsert_5min_summary(payload)
        if result:
            print("Successfully synced to Supabase!")
        else:
            print("Failed to sync.")
            
    except Exception as e:
        print(f"Error during job execution: {e}")

if __name__ == "__main__":
    print("Initializing Data Engine Orchestrator...")
    
    # Ensure timescaledb is initialized on startup if needed
    # from database.timescale_client import init_db
    # init_db()
    
    # Schedule the job every 5 minutes
    # It's usually best to offset it slightly to ensure the preceding candle is fully closed
    schedule.every(5).minutes.at(":05").do(run_5min_sync_job)
    
    # Run once immediately for testing/warmup
    run_5min_sync_job()
    
    print("Listening for 5-minute boundaries...")
    while True:
        schedule.run_pending()
        time.sleep(1)
