import logging
import pandas as pd
import pandas_ta as ta

# Module constant: NIFTY lot size (standard for Indian markets)
# Updated January 2026: NSE reduced lot size from 75 to 65 shares per lot
LOT_SIZE = 65

logger = logging.getLogger(__name__)


class CalculationEngine:
    def __init__(self):
        logger.info("Initialized 5-Min Calculation Engine.")

    def compute_standard_indicators(self, df: pd.DataFrame):
        """
        Calculates standard technical indicators using pandas-ta.
        Requires a DataFrame with 'open', 'high', 'low', 'close', 'volume' columns.
        """
        if not isinstance(df, pd.DataFrame):
            logger.error(f"[compute_standard_indicators] Invalid input: expected DataFrame, got {type(df)}")
            return df
        if df.empty or len(df) < 20: # Need enough data for EMAs
            return df

        # Create a copy to avoid mutating the caller's DataFrame
        df = df.copy()

        # Ensure column names are correct for pandas-ta
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)

        try:
            # Calculate RSI
            df.ta.rsi(length=14, append=True)

            # Calculate EMAs and SMAs
            df.ta.ema(length=20, append=True) # Keep 20 if used elsewhere
            df.ta.ema(length=21, append=True)
            df.ta.ema(length=50, append=True)
            df.ta.sma(length=200, append=True)

            # Calculate MACD
            df.ta.macd(fast=12, slow=26, signal=9, append=True)

            # Calculate Bollinger Bands
            df.ta.bbands(length=20, std=2.0, append=True)

            # Calculate Supertrend
            # length=7, multiplier=3.0 are common intraday settings
            df.ta.supertrend(length=7, multiplier=3.0, append=True)

            # Calculate Stochastic RSI
            # length=14, rsi_length=14, k=3, d=3
            df.ta.stochrsi(length=14, rsi_length=14, k=3, d=3, append=True)

            # Calculate ADX
            # length=14 is standard
            df.ta.adx(length=14, append=True)

            # Calculate ATR
            # length=14 is standard
            df.ta.atr(length=14, append=True)
        except Exception as e:
            logger.error(f"[compute_standard_indicators] Error calculating indicators: {e}")

        # Calculate VWAP
        try:
            # VWAP requires datetime index
            if not isinstance(df.index, pd.DatetimeIndex):
                if 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
            df.ta.vwap(append=True)
        except Exception as e:
            logger.error(f"[compute_standard_indicators] Failed to calculate VWAP: {e}")

        # Revert column names back to lowercase for database mapping
        df.columns = df.columns.str.lower()
        return df

    def compute_net_gex(self, option_chain_data: list, spot_price: float):
        """
        Calculates Net Gamma Exposure (Net GEX) using live Upstox JSON chain.
        Requires a list of option strikes directly from Upstox /option/chain.
        
        Formula:
        Call GEX = Call Gamma * Call OI * Spot Price * Lot Size
        Put GEX = Put Gamma * Put OI * Spot Price * Lot Size * -1
        Net GEX = Sum(Call GEX) + Sum(Put GEX)
        """
        if not option_chain_data:
            logger.warning("[compute_net_gex] Missing Option Chain data, returning Net GEX 0.0.")
            return 0.0

        total_net_gex = 0.0

        try:
            for strike_data in option_chain_data:
                # Call Evaluation
                c_options = strike_data.get('call_options')
                if c_options:
                    c_greeks = c_options.get('option_greeks', {})
                    c_market = c_options.get('market_data', {})
                    
                    c_gamma = c_greeks.get('gamma')
                    c_oi = c_market.get('oi')
                    
                    if c_gamma is not None and c_oi is not None:
                        total_net_gex += (c_gamma * c_oi * spot_price * LOT_SIZE)
                
                # Put Evaluation
                p_options = strike_data.get('put_options')
                if p_options:
                    p_greeks = p_options.get('option_greeks', {})
                    p_market = p_options.get('market_data', {})
                    
                    p_gamma = p_greeks.get('gamma')
                    p_oi = p_market.get('oi')
                    
                    if p_gamma is not None and p_oi is not None:
                        # Negative multiplier for puts (dealer delta hedging acts against trend)
                        total_net_gex += (p_gamma * p_oi * spot_price * LOT_SIZE * -1.0)
                        
            return round(total_net_gex, 4)
            
        except Exception as e:
            logger.error(f"[compute_net_gex] Error computing Net GEX from live options: {e}")
            return 0.0

    def compute_opening_range_status(self, df: pd.DataFrame, current_timestamp: pd.Timestamp, range_minutes: int = 15):
        """
        Calculates the Opening Range Breakout (ORB) status.
        Market open is assumed to be 09:15 AM IST.
        """
        if df.empty or 'high' not in df.columns or 'low' not in df.columns or 'close' not in df.columns:
            return "Error: Missing Data"
            
        working_df = df.copy()
        if not isinstance(working_df.index, pd.DatetimeIndex):
            if 'timestamp' in working_df.columns:
                working_df['timestamp'] = pd.to_datetime(working_df['timestamp'])
                working_df.set_index('timestamp', inplace=True)
            else:
                return "Error: No Timestamp index"

        # Filter for the current day
        current_date_str = current_timestamp.strftime('%Y-%m-%d')
        try:
            today_df = working_df.loc[current_date_str]
        except KeyError:
            return "Error: No Data for Today"
            
        if today_df.empty:
            return "Error: No Data for Today"
            
        market_open_time = pd.Timestamp(f"{current_date_str} 09:15:00")
        range_end_time = market_open_time + pd.Timedelta(minutes=range_minutes)
        
        if current_timestamp <= range_end_time:
            return "Forming"
            
        # Get candles strictly within the opening range (e.g., 09:15 to 09:29:59)
        end_time_str = (range_end_time - pd.Timedelta(seconds=1)).strftime('%H:%M:%S')
        or_df = today_df.between_time('09:15', end_time_str)
        
        if or_df.empty:
            return "Error: Missing Opening Candles"
            
        or_high = float(or_df['high'].max())
        or_low = float(or_df['low'].min())
        
        try:
            latest_candle = today_df.loc[:current_timestamp].iloc[-1]
            latest_close = float(latest_candle['close'])
        except Exception:
            latest_close = float(today_df.iloc[-1]['close'])
            
        if latest_close > or_high:
            return "Breakout Up"
        elif latest_close < or_low:
            return "Breakout Down"
        else:
            return "Inside Range"

    def compute_cpr_status(self, current_price: float, prev_day_high: float, prev_day_low: float, prev_day_close: float):
        """
        Calculates the Central Pivot Range (CPR) based on the previous day's data,
        and determines if the current price is Above, Below, or Inside the CPR.
        
        Formula:
        Pivot (P) = (High + Low + Close) / 3
        Bottom Central (BC) = (High + Low) / 2
        Top Central (TC) = (Pivot - BC) + Pivot
        """
        try:
            pivot = (prev_day_high + prev_day_low + prev_day_close) / 3.0
            bc = (prev_day_high + prev_day_low) / 2.0
            tc = (pivot - bc) + pivot
            
            highest_cpr = max(tc, bc)
            lowest_cpr = min(tc, bc)
            
            if current_price > highest_cpr:
                return "Above CPR"
            elif current_price < lowest_cpr:
                return "Below CPR"
            else:
                return "Inside CPR"
        except Exception as e:
            logger.error(f"[compute_cpr_status] Error calculating CPR: {e}")
            return "Error: Calc Failed"

    def compute_cpr_width(self, prev_day_high: float, prev_day_low: float, prev_day_close: float):
        """
        Calculates the width of the Central Pivot Range (CPR) as a percentage of the Pivot price.
        Thresholds for NIFTY/BankNIFTY generally:
        - Narrow: < 0.15% width
        - Average: 0.15% - 0.35% width
        - Wide: > 0.35% width
        """
        try:
            pivot = (prev_day_high + prev_day_low + prev_day_close) / 3.0

            # Check for division by zero
            if pivot == 0:
                logger.error("[compute_cpr_width] Pivot is 0, cannot calculate CPR width")
                return "Error"

            bc = (prev_day_high + prev_day_low) / 2.0
            tc = (pivot - bc) + pivot

            cpr_top = max(tc, bc)
            cpr_bottom = min(tc, bc)

            # Calculate width as a percentage of the central pivot
            cpr_width_pct = ((cpr_top - cpr_bottom) / pivot) * 100

            if cpr_width_pct < 0.15:
                return "Narrow"
            elif cpr_width_pct > 0.35:
                return "Wide"
            else:
                return "Average"
        except Exception as e:
            logger.error(f"[compute_cpr_width] Error calculating CPR Width: {e}")
            return "Error: Calc Failed"

    def compute_vwap_status_dict(self, current_price: float, current_vwap: float):
        """
        Returns a dictionary for vwap_status containing:
        - "price_vs_vwap": "Above" or "Below" or "At"
        - "vwap_dist_pct": Percentage distance from VWAP
        """
        if not current_vwap or pd.isna(current_vwap):
            return {
                "price_vs_vwap": "Unknown",
                "vwap_dist_pct": 0.0
            }
            
        try:
            if current_price > current_vwap:
                status = "Above"
            elif current_price < current_vwap:
                status = "Below"
            else:
                status = "At"
                
            dist_pct = ((current_price - current_vwap) / current_vwap) * 100.0
            
            return {
                "price_vs_vwap": status,
                "vwap_dist_pct": round(dist_pct, 4)
            }
        except Exception as e:
            logger.error(f"[compute_vwap_status_dict] Error calculating VWAP status: {e}")
            return {
                "price_vs_vwap": "Error",
                "vwap_dist_pct": 0.0
            }

    def compute_vwap_context_dict(self, df: pd.DataFrame, current_price: float):
        """
        Calculates the VWAP context, specifically anchored from 15:00 of the previous session
        (or current session if past 15:00), which acts as the BTST (Buy Today Sell Tomorrow)
        institutional accumulation baseline.
        """
        result = {
            "current_price": round(current_price, 2) if current_price else 0.0,
            "anchored_vwap_1500": 0.0,
            "divergence": "N/A",
            "reversion_probability": "Unknown"
        }
        
        try:
            if df is None or df.empty or len(df) == 0:
                return result
                
            # Make sure timestamp is datetime format
            temp_ts = pd.to_datetime(df['timestamp'])
            latest_time = temp_ts.iloc[-1]
            
            # Determine the target 15:00 anchor point
            # If current time is >= 15:00, anchor is today at 15:00
            # If current time is < 15:00, anchor is previous trading day at 15:00
            if latest_time.hour >= 15:
                anchor_date = latest_time.date()
            else:
                # Find the previous trading day in the dataframe
                unique_dates = temp_ts.dt.date.unique()
                if len(unique_dates) > 1:
                    # Previous day is the second to last date
                    anchor_date = unique_dates[-2]
                else:
                    return result

            # Construct the exact anchor timestamp
            import datetime
            anchor_timestamp = datetime.datetime.combine(anchor_date, datetime.time(15, 0))
            if temp_ts.dt.tz is not None:
                anchor_timestamp = anchor_timestamp.replace(tzinfo=temp_ts.dt.tz)
                
            # Filter df from anchor_timestamp onwards
            anchored_df = df[temp_ts >= anchor_timestamp].copy()
            
            if len(anchored_df) == 0:
                return result
                
            # Calculate Anchored VWAP
            anchored_df['typical_price'] = (anchored_df['high'] + anchored_df['low'] + anchored_df['close']) / 3
            anchored_df['tp_v'] = anchored_df['typical_price'] * anchored_df['volume']
            
            cum_tp_v = anchored_df['tp_v'].sum()
            cum_v = anchored_df['volume'].sum()
            
            if cum_v > 0:
                anchored_vwap = round(float(cum_tp_v / cum_v), 2)
                result["anchored_vwap_1500"] = anchored_vwap
                
                # Calculate Divergence
                divergence = current_price - anchored_vwap
                result["divergence"] = round(divergence, 2)

                # Calculate Reversion Probability base on divergence distance
                # Check for division by zero
                if anchored_vwap == 0:
                    divergence_pct = 0.0
                else:
                    divergence_pct = abs(divergence) / anchored_vwap * 100
                
                if divergence_pct > 1.0: # > 1% away from BTST VWAP is extremely extended intraday
                    result["reversion_probability"] = "Extremely High (Extended)"
                elif divergence_pct > 0.5:
                    result["reversion_probability"] = "High (Mean Reversion Likely)"
                elif divergence_pct > 0.2:
                    result["reversion_probability"] = "Moderate"
                else:
                    result["reversion_probability"] = "Low (Consolidating at VWAP)"
            
            return result
            
        except Exception as e:
            logger.error(f"[compute_vwap_context_dict] Error calculating Anchored VWAP 15:00: {e}")
            return result
            
    def compute_key_intraday_levels(self, current_price: float, prev_day_high: float, prev_day_low: float):
        """
        Returns a dictionary for key_intraday_levels containing:
        - "prev_day_high": The high of the previous day
        - "prev_day_low": The low of the previous day
        - "distance_to_pdh_pct": Percentage distance from the current price to the PDH
        """
        try:
            # Validate prev_day_high before division
            if not prev_day_high or prev_day_high == 0:
                logger.error("[compute_key_intraday_levels] prev_day_high is 0 or None")
                return {
                    "prev_day_high": 0.0,
                    "prev_day_low": 0.0,
                    "distance_to_pdh_pct": 0.0
                }

            dist_pct = ((current_price - prev_day_high) / prev_day_high) * 100.0

            return {
                "prev_day_high": float(prev_day_high),
                "prev_day_low": float(prev_day_low) if prev_day_low else 0.0,
                "distance_to_pdh_pct": round(dist_pct, 4)
            }
        except Exception as e:
            logger.error(f"[compute_key_intraday_levels] Error calculating Key Intraday Levels: {e}")
            return {
                "prev_day_high": 0.0,
                "prev_day_low": 0.0,
                "distance_to_pdh_pct": 0.0
            }

    def compute_momentum_burst_dict(self, current_volume: float, avg_volume: float, current_timestamp: pd.Timestamp = None):
        """
        Returns a dictionary for momentum_burst containing:
        - "last_5m_volume_vs_avg": formatted string like "1.96x"
        - "moc_volume_spike": boolean triggering if Volume is >2x after 15:00
        """
        try:
            if not avg_volume or avg_volume == 0 or pd.isna(avg_volume):
                return {
                    "last_5m_volume_vs_avg": "0.00x",
                    "moc_volume_spike": False
                }
                
            ratio = float(current_volume) / float(avg_volume)
            
            # Check for MOC (Market On Close) volume spike
            moc_spike = False
            if current_timestamp is not None:
                if current_timestamp.hour >= 15 and ratio >= 2.0:
                    moc_spike = True
            
            return {
                "last_5m_volume_vs_avg": f"{ratio:.2f}x",
                "moc_volume_spike": moc_spike
            }
        except Exception as e:
            logger.error(f"[compute_momentum_burst_dict] Error calculating Momentum Burst: {e}")
            return {
                "last_5m_volume_vs_avg": "0.00x",
                "moc_volume_spike": False
            }

    def compute_institutional_context_dict(self, current_price: float, sma_200: float, prev_day_high: float, prev_day_low: float):
        """
        Returns a dictionary for institutional_context containing:
        - "trend_bias": formatted string like "Bullish (Above 200 SMA)"
        - "sma_200": float
        - "pdh": float
        - "pdl": float
        """
        try:
            if not sma_200 or pd.isna(sma_200):
                bias = "Unknown (Missing 200 SMA)"
                sma_200 = 0.0
            elif current_price > sma_200:
                bias = "Bullish (Above 200 SMA)"
            elif current_price < sma_200:
                bias = "Bearish (Below 200 SMA)"
            else:
                bias = "Neutral (At 200 SMA)"

            return {
                "trend_bias": bias,
                "sma_200": round(float(sma_200), 2) if sma_200 else 0.0,
                "pdh": float(prev_day_high) if prev_day_high else 0.0,
                "pdl": float(prev_day_low) if prev_day_low else 0.0
            }
        except Exception as e:
            logger.error(f"[compute_institutional_context_dict] Error calculating Institutional Context: {e}")
            return {
                "trend_bias": "Error",
                "sma_200": 0.0,
                "pdh": 0.0,
                "pdl": 0.0
            }

    def compute_heavyweight_vs_vwap(self, quotes: dict):
        """
        Calculates the live VWAP vs Price state for the top 5 NIFTY heavyweights.
        """
        result = {}
        try:
            if not isinstance(quotes, dict):
                logger.error(f"[compute_heavyweight_vs_vwap] Invalid quotes type: {type(quotes)}")
                return result

            heavyweights = {
                "NSE_EQ|INE040A01034": "HDFCBANK",
                "NSE_EQ|INE002A01018": "RELIANCE",
                "NSE_EQ|INE090A01021": "ICICIBANK",
                "NSE_EQ|INE009A01021": "INFY",
                "NSE_EQ|INE467B01029": "TCS"
            }

            for key, symbol in heavyweights.items():
                if key in quotes:
                    data = quotes[key]
                    last_price = float(data.get('last_price', 0.0) or 0)
                    vwap = float(data.get('average_price', 0.0) or 0)

                    if last_price > vwap and vwap > 0:
                        result[symbol] = "Above VWAP (Bullish)"
                    elif last_price < vwap and vwap > 0:
                        result[symbol] = "Below VWAP (Bearish)"
                    else:
                        result[symbol] = "Neutral"
                else:
                    result[symbol] = "Unknown"

        except Exception as e:
            logger.error(f"[compute_heavyweight_vs_vwap] Error calculating heavyweight vs VWAP: {e}")
            return {}

        return result

    def compute_volume_profile_dict(self, df: pd.DataFrame, current_timestamp: pd.Timestamp):
        """
        Calculates the Volume Profile for the current day up to the current timestamp.
        Returns a dictionary containing:
        - "poc": Point of Control (Price with highest volume)
        - "vah": Value Area High
        - "val": Value Area Low
        - "total_volume": Total volume for the current day
        """
        try:
            working_df = df.copy()
            if 'timestamp' in working_df.columns:
                working_df['timestamp'] = pd.to_datetime(working_df['timestamp'])
                working_df.set_index('timestamp', inplace=True)

            # Filter for the current day up to current timestamp
            current_date_str = current_timestamp.strftime('%Y-%m-%d')
            try:
                today_df = working_df.loc[current_date_str]
                today_df = today_df.loc[:current_timestamp]
            except KeyError:
                return {"poc": 0.0, "vah": 0.0, "val": 0.0, "total_volume": 0}

            if today_df.empty:
                return {"poc": 0.0, "vah": 0.0, "val": 0.0, "total_volume": 0}

            total_vol = float(today_df['volume'].sum())
            if total_vol == 0:
                return {"poc": 0.0, "vah": 0.0, "val": 0.0, "total_volume": 0}

            # Create price bins
            min_price = today_df['low'].min()
            max_price = today_df['high'].max()
            
            # Use ~50 bins for intraday resolution
            num_bins = 50
            if max_price == min_price:
                return {
                    "poc": float(min_price), 
                    "vah": float(min_price), 
                    "val": float(min_price), 
                    "total_volume": int(total_vol)
                }

            bin_size = (max_price - min_price) / num_bins
            bins = [min_price + i * bin_size for i in range(num_bins + 1)]
            vol_profile = {tuple([bins[i], bins[i+1]]): 0.0 for i in range(num_bins)}

            # Distribute volume
            for _, row in today_df.iterrows():
                high = row['high']
                low = row['low']
                vol = row['volume']
                
                # Find overlapping bins
                overlapping_bins = []
                for b_range in vol_profile.keys():
                    # Bins have exclusive upper bounds [lower, upper). Use strict inequalities
                    # so bins that only touch at a point (low == b_range[1]) are not included.
                    if b_range[1] > low and b_range[0] < high:
                        overlapping_bins.append(b_range)
                
                if overlapping_bins:
                    vol_per_bin = vol / len(overlapping_bins)
                    for b_range in overlapping_bins:
                        vol_profile[b_range] += vol_per_bin

            # Find POC
            poc_bin = max(vol_profile, key=vol_profile.get)
            poc_price = (poc_bin[0] + poc_bin[1]) / 2.0

            # Calculate Value Area (70%)
            target_vol = total_vol * 0.70
            
            # Sort bins by volume descending
            sorted_bins = sorted(vol_profile.items(), key=lambda x: x[1], reverse=True)
            
            value_area_bins = [poc_bin]
            current_va_vol = vol_profile[poc_bin]
            
            # Simple expansion from POC
            bin_list = list(vol_profile.keys())
            poc_idx = bin_list.index(poc_bin)
            
            upper_idx = poc_idx + 1
            lower_idx = poc_idx - 1
            
            while current_va_vol < target_vol and (upper_idx < len(bin_list) or lower_idx >= 0):
                vol_up = vol_profile[bin_list[upper_idx]] if upper_idx < len(bin_list) else -1
                vol_down = vol_profile[bin_list[lower_idx]] if lower_idx >= 0 else -1
                
                if vol_up > vol_down:
                    value_area_bins.append(bin_list[upper_idx])
                    current_va_vol += vol_up
                    upper_idx += 1
                else:
                    value_area_bins.append(bin_list[lower_idx])
                    current_va_vol += vol_down
                    lower_idx -= 1

            val_price = min([b[0] for b in value_area_bins])
            vah_price = max([b[1] for b in value_area_bins])

            return {
                "poc": round(float(poc_price), 2),
                "vah": round(float(vah_price), 2),
                "val": round(float(val_price), 2),
                "total_volume": int(total_vol)
            }
        except Exception as e:
            logger.error(f"[compute_volume_profile_dict] Error calculating Volume Profile: {e}")
            return {"poc": 0.0, "vah": 0.0, "val": 0.0, "total_volume": 0}

    def compute_derived_features_dict(self, df: pd.DataFrame, current_timestamp: pd.Timestamp):
        """
        Calculates intraday derived features (currently swing pivots).
        Returns a dictionary containing a 'pivots' list.
        """
        try:
            working_df = df.copy()
            if 'timestamp' in working_df.columns:
                working_df['timestamp'] = pd.to_datetime(working_df['timestamp'])
                working_df.set_index('timestamp', inplace=True)

            # Filter for the current day up to current timestamp
            current_date_str = current_timestamp.strftime('%Y-%m-%d')
            try:
                today_df = working_df.loc[current_date_str]
                today_df = today_df.loc[:current_timestamp]
            except KeyError:
                return {"pivots": []}

            if today_df.empty or len(today_df) < 5:
                return {"pivots": []}

            pivots = []
            
            # Simple Swing Point algorithm
            # Lookback and Lookforward periods (e.g., 2 bars left, 2 bars right)
            left_bars = 2
            right_bars = 2
            
            # We need absolute index values to match user format "index": 1658
            # In live pandas, standard reset_index gives 0...N. 
            # We'll use the original dataframe index if it's integer, else just a counter
            
            today_reset = today_df.reset_index()
            # If the original dataframe had an integer index before we set timestamp, let's try to pass it 
            # otherwise we just generate a sequential one
            for i in range(left_bars, len(today_reset) - right_bars):
                window = today_reset.iloc[i - left_bars : i + right_bars + 1]
                
                current_high = today_reset.iloc[i]['high']
                current_low = today_reset.iloc[i]['low']
                current_ts = today_reset.iloc[i]['timestamp']
                
                # Check for Swing High
                if current_high == window['high'].max() and current_high > today_reset.iloc[i-1]['high'] and current_high > today_reset.iloc[i+1]['high']:
                    pivots.append({
                        "type": "high",
                        "price": round(float(current_high), 2),
                        "index": int(i), # Using local daily index or we could try global index if needed
                        "ts": current_ts.isoformat()
                    })
                    
                # Check for Swing Low
                elif current_low == window['low'].min() and current_low < today_reset.iloc[i-1]['low'] and current_low < today_reset.iloc[i+1]['low']:
                    pivots.append({
                        "type": "low",
                        "price": round(float(current_low), 2),
                        "index": int(i),
                        "ts": current_ts.isoformat()
                    })
                    
            return {"pivots": pivots}
            
        except Exception as e:
            logger.error(f"[compute_derived_features_dict] Error calculating Derived Features (Pivots): {e}")
            return {"pivots": []}

    def compute_meta_dict(self, current_timestamp: pd.Timestamp, latest_close: float):
        """
        Generates the 'meta' dictionary containing operational data,
        ticker info, and the calculated intraday session phase.
        """
        # Calculate session phase based on NSE market hours (09:15 to 15:30)
        market_time = current_timestamp.time()
        
        # Default
        phase = "Unknown"
        
        from datetime import time
        
        if market_time < time(9, 15):
            phase = "Pre-market"
        elif time(9, 15) <= market_time < time(10, 0):
            phase = "Morning Volatility (Opening Range)"
        elif time(10, 0) <= market_time < time(12, 0):
            phase = "Morning Trend Establishment"
        elif time(12, 0) <= market_time < time(13, 30):
            phase = "Mid-day (Institutional Grind)"
        elif time(13, 30) <= market_time < time(15, 0):
            phase = "Afternoon Breakout / Reversal"
        elif time(15, 0) <= market_time <= time(15, 30):
            phase = "Closing Volatility (Position Squaring)"
        else:
            phase = "Post-market"
            
        return {
            "ticker": "NIFTY",
            "live_price": float(latest_close),
            "is_index": True,
            "timestamp": current_timestamp.isoformat(),
            "market_time": current_timestamp.strftime("%H:%M:%S"),
            "session_phase": phase
        }

    def compute_catalyst_context_dict(self, df: pd.DataFrame, current_timestamp: pd.Timestamp, prev_day_close: float):
        """
        Calculates the day's gap percentage and categorization.
        Returns a dictionary for 'catalyst_context'.
        """
        if not prev_day_close or prev_day_close == 0.0:
            return {
                "day_type": "Unknown",
                "gap_pct": 0.0,
                "gap_fade_probability": "Unknown"
            }
            
        try:
            working_df = df.copy()
            if 'timestamp' in working_df.columns:
                working_df['timestamp'] = pd.to_datetime(working_df['timestamp'])
                working_df.set_index('timestamp', inplace=True)
                
            current_date_str = current_timestamp.strftime('%Y-%m-%d')
            try:
                today_df = working_df.loc[current_date_str]
            except KeyError:
                today_df = pd.DataFrame()
            
            if today_df.empty:
                return {
                    "day_type": "Unknown",
                    "gap_pct": 0.0,
                    "gap_fade_probability": "Unknown"
                }
                
            today_open = float(today_df.iloc[0]['open'])
            # Ensure prev_day_close is not zero before division
            if prev_day_close == 0:
                logger.error("[compute_catalyst_context_dict] prev_day_close is 0, cannot calculate gap_pct")
                return {
                    "day_type": "Unknown",
                    "gap_pct": 0.0,
                    "gap_fade_probability": "Unknown"
                }
            gap_pct = ((today_open - prev_day_close) / prev_day_close) * 100.0
            gap_pct = round(gap_pct, 2)
            
            if gap_pct >= 0.25:
                day_type = "GAP_UP"
            elif gap_pct <= -0.25:
                day_type = "GAP_DOWN"
            else:
                day_type = "NORMAL_FLOW"
                
            # Fade probability heuristic: large gaps are more likely to fade partially
            if abs(gap_pct) >= 0.8:
                fade_prob = "High"
            elif abs(gap_pct) >= 0.4:
                fade_prob = "Medium"
            else:
                fade_prob = "Low"
                
            return {
                "day_type": day_type,
                "gap_pct": gap_pct,
                "gap_fade_probability": fade_prob
            }
            
        except Exception as e:
            logger.error(f"[compute_catalyst_context_dict] Error calculating Catalyst Context: {e}")
            return {
                "day_type": "Error",
                "gap_pct": 0.0,
                "gap_fade_probability": "Unknown"
            }

    def compute_index_macro_dict(self, vix_data: dict):
        """
        Returns the 'index_macro' dictionary containing 'vix' data, velocity and crush state.
        Uses live India VIX data fetched from Upstox.
        """
        vix_level = float(vix_data.get('last_price', 0.0))
        vix_change = float(vix_data.get('net_change', 0.0))
        
        # Determine velocity
        if vix_change > 1.0:
            vix_velocity = "Aggressive Spiking"
        elif vix_change > 0.5:
            vix_velocity = "Spiking"
        elif vix_change < -1.0:
            vix_velocity = "Aggressive Crushing"
        elif vix_change < -0.5:
            vix_velocity = "Falling"
        else:
            vix_velocity = "Neutral"
            
        if vix_level == 0.0:
            vix_velocity = "Unknown"
            
        # Determine strict intraday volatility crush
        vix_crush_detected = False
        if vix_level > 0 and vix_change < 0:
            # Backtrack to opening price limit
            bod_vix = vix_level - vix_change
            if bod_vix > 0:
                drop_pct = (abs(vix_change) / bod_vix) * 100
                if drop_pct >= 5.0: # Intraday VIX drop of more than 5% triggers crush signal
                    vix_crush_detected = True
            
        return {
            "vix": {
                "level": round(vix_level, 2),
                "change": round(vix_change, 2)
            },
            "vix_velocity": vix_velocity,
            "vix_crush_detected": vix_crush_detected
        }

    def compute_cost_of_carry_dict(self, spot_5m_df: pd.DataFrame, fut_5m_df: pd.DataFrame, spot_daily_df: pd.DataFrame, fut_daily_df: pd.DataFrame):
        """
        Calculates the Cost of Carry (Basis) Trend.
        Basis = Future Price - Spot Price
        Analyzes 15-minute momentum and 5-day SMA trend.
        """
        # Default empty return
        result = {
            "current_premium": 0.0,
            "15m_basis_change": 0.0,
            "20d_sma_baseline": 0.0,
            "premium_trend": "Unknown",
            "interpretation": "Unknown"
        }

        try:
            # Initialize live_basis outside the conditional block for later use
            live_basis = None

            # 1. Calculate 15m Momentum (using 5-min candles, i.e., 3 candles ago)
            if not spot_5m_df.empty and not fut_5m_df.empty and len(spot_5m_df) >= 4 and len(fut_5m_df) >= 4:
                live_spot = float(spot_5m_df.iloc[-1]['close'])
                live_fut = float(fut_5m_df.iloc[-1]['close'])

                spot_15m = float(spot_5m_df.iloc[-4]['close'])
                fut_15m = float(fut_5m_df.iloc[-4]['close'])

                live_basis = live_fut - live_spot
                basis_15m = fut_15m - spot_15m
                basis_15m_change = live_basis - basis_15m

                result["current_premium"] = round(live_basis, 2)
                result["15m_basis_change"] = round(basis_15m_change, 2)

                if basis_15m_change >= 10.0:
                    result["interpretation"] = "Aggressive Institutional Buying (Premium Expansion)"
                elif basis_15m_change <= -10.0:
                    result["interpretation"] = "Aggressive Institutional Selling (Premium Contraction)"
                else:
                    result["interpretation"] = "Stable / Noise"

            # 2. Calculate 20-day SMA Trend (Monthly Baseline)
            if not spot_daily_df.empty and not fut_daily_df.empty and len(spot_daily_df) >= 20 and len(fut_daily_df) >= 20:
                # Align dates if needed, but assuming roughly synced arrays for last 20 trading days
                spot_closes = spot_daily_df.tail(20)['close'].values
                fut_closes = fut_daily_df.tail(20)['close'].values

                basis_history = [f - s for f, s in zip(fut_closes, spot_closes)]
                basis_20d_sma = sum(basis_history) / len(basis_history)

                result["20d_sma_baseline"] = round(float(basis_20d_sma), 2)

                # Compare live basis to 20d SMA (Monthly context)
                # Only compare if live_basis was calculated (first block was executed)
                if live_basis is not None:
                    if live_basis > basis_20d_sma + 10:
                        result["premium_trend"] = "Expanding"
                    elif live_basis < basis_20d_sma - 10:
                        result["premium_trend"] = "Shrinking"
                    else:
                        result["premium_trend"] = "Mean Reverting"

            return result

        except Exception as e:
            logger.error(f"[compute_cost_of_carry_dict] Error calculating Cost of Carry: {e}")
            return result
            
    def compute_true_vwap_dict(self, fut_5m_df: pd.DataFrame):
        """
        Calculates the True Intraday VWAP on the Nifty Futures contract.
        Since Spot indices do not have real traded volume, true VWAP must be derived from the Future.
        Signals whether the current price is 'Mean Reverting' or 'Trending' vs the VWAP.
        """
        result = {
            "vwap_level": 0.0,
            "dist_from_vwap": 0.0,
            "vwap_trend_status": "Unknown"
        }
        
        try:
            if fut_5m_df.empty or len(fut_5m_df) == 0:
                return result
                
            # Filter DataFrame to strictly today's intraday bars
            latest_ts = pd.to_datetime(fut_5m_df['timestamp'].iloc[-1])
            today_date = latest_ts.date()
            # Use proper datetime comparison instead of string startswith
            today_df = fut_5m_df[pd.to_datetime(fut_5m_df['timestamp']).dt.date == today_date].copy()
            
            if len(today_df) == 0:
                return result
                
            # VWAP Formula: Cumulative(Typical Price * Volume) / Cumulative(Volume)
            # Typical Price = (High + Low + Close) / 3
            today_df['typical_price'] = (today_df['high'] + today_df['low'] + today_df['close']) / 3
            today_df['tp_v'] = today_df['typical_price'] * today_df['volume']
            
            today_df['cum_tp_v'] = today_df['tp_v'].cumsum()
            today_df['cum_v'] = today_df['volume'].cumsum()
            
            today_df['vwap'] = today_df['cum_tp_v'] / today_df['cum_v']
            
            latest_vwap = float(today_df['vwap'].iloc[-1])
            latest_close = float(today_df['close'].iloc[-1])
            dist = latest_close - latest_vwap
            
            result["vwap_level"] = round(latest_vwap, 2)
            result["dist_from_vwap"] = round(dist, 2)
            
            # Determine Trend Status based on distance
            if dist > 15.0:
                result["vwap_trend_status"] = "Uptrend (Holding Above VWAP)"
            elif dist < -15.0:
                result["vwap_trend_status"] = "Downtrend (Holding Below VWAP)"
            else:
                result["vwap_trend_status"] = "Mean Reverting (Hovering at VWAP)"
                
            return result
            
        except Exception as e:
            logger.error(f"[compute_true_vwap_dict] Error calculating True VWAP: {e}")
            return result
            
    def compute_max_pain(self, option_chain_data: list, latest_spot_price: float):
        """
        Calculates the Max Pain strike from the active option chain.
        Max Pain is the strike price where option sellers (writers) experience the least financial loss (intrinsic value).
        Calculates the distance from the current Spot price to evaluate manipulation pulls on Expiry Days.
        """
        result = {
            "max_pain_strike": 0.0,
            "dist_from_spot": 0.0,
            "pain_shift_signal": "Unknown"
        }
        
        try:
            if not option_chain_data or len(option_chain_data) == 0:
                return result
                
            strikes = []
            call_oi_map = {}
            put_oi_map = {}
            
            # Extract OI per strike
            for strike_node in option_chain_data:
                strike_price = float(strike_node.get('strike_price', 0))
                if strike_price == 0:
                    continue
                    
                strikes.append(strike_price)
                
                # Fetch Call OI
                call_info = strike_node.get('call_options', {})
                if call_info:
                    call_oi_map[strike_price] = float(call_info.get('market_data', {}).get('oi', 0))
                else:
                    call_oi_map[strike_price] = 0.0
                    
                # Fetch Put OI
                put_info = strike_node.get('put_options', {})
                if put_info:
                    put_oi_map[strike_price] = float(put_info.get('market_data', {}).get('oi', 0))
                else:
                    put_oi_map[strike_price] = 0.0
                    
            if not strikes:
                return result
                
            # Sort strikes to properly test expiry points
            strikes.sort()
            
            min_pain_value = float('inf')
            max_pain_strike = 0.0
            
            # Test every strike as a potential expiry point
            for test_strike in strikes:
                total_pain = 0.0
                
                # Calculate intrinsic value to be paid out if it expires at test_strike
                for actual_strike in strikes:
                    # If expires at test_strike, Calls below test_strike finish in the money
                    if actual_strike < test_strike:
                        intrinsic_call_val = test_strike - actual_strike
                        total_pain += intrinsic_call_val * call_oi_map[actual_strike]
                        
                    # If expires at test_strike, Puts above test_strike finish in the money
                    elif actual_strike > test_strike:
                        intrinsic_put_val = actual_strike - test_strike
                        total_pain += intrinsic_put_val * put_oi_map[actual_strike]
                        
                # Find the minimum payout mathematically
                if total_pain < min_pain_value:
                    min_pain_value = total_pain
                    max_pain_strike = test_strike
                    
            result["max_pain_strike"] = round(max_pain_strike, 2)
            dist_spot = max_pain_strike - latest_spot_price
            result["dist_from_spot"] = round(dist_spot, 2)
            
            # Signaling for mean reversion (Big Boys pulling price to them)
            if dist_spot >= 50.0:
                result["pain_shift_signal"] = "Spot significantly below Pain (Pull Up Expected)"
            elif dist_spot <= -50.0:
                result["pain_shift_signal"] = "Spot significantly above Pain (Pull Down Expected)"
            else:
                result["pain_shift_signal"] = "Spot hovering near Center of Gravity"
                
            return result
                
        except Exception as e:
            logger.error(f"[compute_max_pain] Error calculating Max Pain: {e}")
            return result
            
    def compute_options_pcr(self, option_chain_data: list):
        """
        Calculates the Put-Call Ratio (PCR) from the total Open Interest across the active Option Chain.
        Total Put OI / Total Call OI.
        > 1.0 implies more Puts (Bearish sentiment or hedging).
        < 1.0 implies more Calls (Bullish sentiment).
        """
        result = {
            "live_pcr": 0.0,
            "total_call_oi": 0.0,
            "total_put_oi": 0.0
        }
        
        try:
            if not option_chain_data or len(option_chain_data) == 0:
                return result
                
            total_call_oi = 0.0
            total_put_oi = 0.0
            
            for strike_node in option_chain_data:
                # Fetch Call OI
                call_info = strike_node.get('call_options', {})
                if call_info:
                    total_call_oi += float(call_info.get('market_data', {}).get('oi', 0))
                    
                # Fetch Put OI
                put_info = strike_node.get('put_options', {})
                if put_info:
                    total_put_oi += float(put_info.get('market_data', {}).get('oi', 0))
                    
            result["total_call_oi"] = total_call_oi
            result["total_put_oi"] = total_put_oi
            
            if total_call_oi > 0:
                result["live_pcr"] = round(total_put_oi / total_call_oi, 4)
                
            return result
            
        except Exception as e:
            logger.error(f"[compute_options_pcr] Error calculating PCR: {e}")
            return result
            
    def compute_gamma_walls(self, option_chain_data: list, latest_spot_price: float):
        """
        Identifies the Call Wall (Highest Call OI) and Put Wall (Highest Put OI)
        from the active option chain structure, acting as the strongest structural 
        ceiling/resistance and floor/support respectively.
        """
        result = {
            "call_wall_strike": 0.0,
            "call_wall_oi": 0.0,
            "call_wall_oi_change": 0.0,
            "dist_to_call_wall": 0.0,
            
            "put_wall_strike": 0.0,
            "put_wall_oi": 0.0,
            "put_wall_oi_change": 0.0,
            "dist_to_put_wall": 0.0,
            
            "wall_context": "No Options Data",
            "gamma_wall_proximity": False
        }
        
        try:
            if not option_chain_data or len(option_chain_data) == 0:
                return result
                
            max_call_oi = -1.0
            call_wall_strike = 0.0
            call_wall_oi_change = 0.0
            
            max_put_oi = -1.0
            put_wall_strike = 0.0
            put_wall_oi_change = 0.0
            
            for strike_node in option_chain_data:
                strike_price = float(strike_node.get('strike_price', 0))
                if strike_price == 0:
                    continue
                    
                # Scan Call OI
                call_info = strike_node.get('call_options', {})
                if call_info:
                    market_data = call_info.get('market_data', {})
                    call_oi = float(market_data.get('oi', 0))
                    if call_oi > max_call_oi:
                        max_call_oi = call_oi
                        call_wall_strike = strike_price
                        call_wall_oi_change = float(market_data.get('oi_change', market_data.get('chng_in_oi', 0.0)))
                        
                # Scan Put OI
                put_info = strike_node.get('put_options', {})
                if put_info:
                    market_data = put_info.get('market_data', {})
                    put_oi = float(market_data.get('oi', 0))
                    if put_oi > max_put_oi:
                        max_put_oi = put_oi
                        put_wall_strike = strike_price
                        put_wall_oi_change = float(market_data.get('oi_change', market_data.get('chng_in_oi', 0.0)))
                        
            # Map Call Wall Limits
            if max_call_oi > 0:
                result["call_wall_strike"] = round(call_wall_strike, 2)
                result["call_wall_oi"] = max_call_oi
                result["call_wall_oi_change"] = call_wall_oi_change
                result["dist_to_call_wall"] = round(call_wall_strike - latest_spot_price, 2)
                
            # Map Put Wall Limits
            if max_put_oi > 0:
                result["put_wall_strike"] = round(put_wall_strike, 2)
                result["put_wall_oi"] = max_put_oi
                result["put_wall_oi_change"] = put_wall_oi_change
                result["dist_to_put_wall"] = round(latest_spot_price - put_wall_strike, 2)
                
            # Synthesize Wall Context specifically for the prompt
            if result["dist_to_call_wall"] > 0 and result["dist_to_put_wall"] > 0:
                cw_dist = result["dist_to_call_wall"]
                pw_dist = result["dist_to_put_wall"]
                
                if cw_dist <= 50 and pw_dist <= 50:
                    result["wall_context"] = f"Pinned Tightly between Massive Call Wall (+{cw_dist}pts) and Put Wall (-{pw_dist}pts). High risk of violent breakout squeeze."
                    result["gamma_wall_proximity"] = True
                elif cw_dist <= 50:
                    result["wall_context"] = f"Approaching Hard Resistance. Only {cw_dist}pts away from massive Call Wall at {call_wall_strike}."
                    result["gamma_wall_proximity"] = True
                elif pw_dist <= 50:
                    result["wall_context"] = f"Approaching Hard Support. Only {pw_dist}pts away from massive Put Wall at {put_wall_strike}."
                    result["gamma_wall_proximity"] = True
                else:
                    result["wall_context"] = f"Floating between Call Ceiling ({call_wall_strike}) and Put Support ({put_wall_strike}). Rangebound setup expected."
                    result["gamma_wall_proximity"] = False
            
            return result
                
        except Exception as e:
            logger.error(f"[compute_gamma_walls] Error extracting Gamma Walls: {e}")
            return result

    def compute_gamma_flip_point(self, option_chain_data: list, latest_spot_price: float):
        """
        Calculates the exact Strike Price where the Total Market Gamma flips from Negative (Dealer Short Gamma)
        to Positive (Dealer Long Gamma). This level acts as the ultimate structural pivot for intraday flow.
        """
        try:
            if not option_chain_data or len(option_chain_data) == 0:
                return 0.0
                
            strike_gex_map = {}
            
            for strike_node in option_chain_data:
                strike_price = float(strike_node.get('strike_price', 0))
                if strike_price == 0:
                    continue
                    
                call_info = strike_node.get('call_options', {})
                put_info = strike_node.get('put_options', {})
                
                call_gex_value = 0.0
                put_gex_value = 0.0
                
                # Fetch Call Gamma/OI
                if call_info:
                    market_data = call_info.get('market_data', {})
                    gamma = float(call_info.get('option_greeks', {}).get('gamma', 0) or 0)
                    oi = float(market_data.get('oi', 0) or 0)
                    # Call GEX is positive
                    call_gex_value = gamma * oi * LOT_SIZE

                # Fetch Put Gamma/OI
                if put_info:
                    market_data = put_info.get('market_data', {})
                    gamma = float(put_info.get('option_greeks', {}).get('gamma', 0) or 0)
                    oi = float(market_data.get('oi', 0) or 0)
                    # Put GEX is negative
                    put_gex_value = gamma * oi * LOT_SIZE
                    put_gex_value = -put_gex_value
                    
                total_strike_gex = call_gex_value + put_gex_value
                strike_gex_map[strike_price] = total_strike_gex

            # To find the flip point, you typically sort the strikes and find where cumulative GEX crosses 0,
            # or locate the specific strike with the highest dense transition.
            # A common approach for the single pinpoint is the strike closest to Spot where Absolute GEX is minimal,
            # OR determining the structural floor where Dealer Gamma reverses.
            
            # Simple mathematically aggressive search: Find the strike with the lowest absolute Net GEX (the fulcrum point).
            if not strike_gex_map:
                return 0.0
                
            # Filter strikes near the spot price to avoid deep OTM noise
            valid_strikes = {k: v for k, v in strike_gex_map.items() if (latest_spot_price * 0.95) <= k <= (latest_spot_price * 1.05)}
            
            if not valid_strikes:
                valid_strikes = strike_gex_map
            
            # The exact Pivot is the closest to Zero GEX
            gamma_flip_strike = min(valid_strikes, key=lambda k: abs(valid_strikes[k]))
            
            return round(gamma_flip_strike, 2)
            
        except Exception as e:
            logger.error(f"[compute_gamma_flip_point] Error calculating Gamma Flip: {e}")
            return 0.0

    def compute_technical_indicators_dict(self, indicators_dict: dict):
        """
        Formats core technical indicators into a nested dictionary structure.
        E.g. RSI with value and signal.
        """
        tech_dict = {}
        
        # 1. RSI
        rsi_val = indicators_dict.get('rsi_14')
        if rsi_val is not None and not pd.isna(rsi_val):
            rsi_val = round(float(rsi_val), 2)
            if rsi_val > 70:
                signal = "overbought"
            elif rsi_val < 30:
                signal = "oversold"
            else:
                signal = "neutral"
                
            tech_dict["rsi"] = {
                "value": rsi_val,
                "signal": signal
            }
        else:
            tech_dict["rsi"] = {
                "value": 0.0,
                "signal": "unknown"
            }
            
        # 2. MACD
        macd_line = indicators_dict.get('macd_12_26_9')
        macd_signal = indicators_dict.get('macds_12_26_9')
        macd_hist = indicators_dict.get('macdh_12_26_9')
        
        if macd_line is not None and not pd.isna(macd_line):
            hist_val = round(float(macd_hist), 2)
            tech_dict["macd"] = {
                "line": round(float(macd_line), 2),
                "signal": round(float(macd_signal), 2) if macd_signal is not None else 0.0,
                "histogram": hist_val,
                "trend": "bullish" if hist_val > 0 else "bearish"
            }
        else:
            tech_dict["macd"] = {
                "line": 0.0,
                "signal": 0.0,
                "histogram": 0.0,
                "trend": "unknown"
            }
            
        # 3. Bollinger Bands
        # pandas_ta column naming for BBands(20, 2):
        # Before lowercase: BBL_20_2.0_2.0, BBM_20_2.0_2.0, BBU_20_2.0_2.0, BBB_20_2.0_2.0, BBP_20_2.0_2.0
        # After df.columns.str.lower() → bbl_20_2.0_2.0, etc.
        bbl = indicators_dict.get('bbl_20_2.0_2.0')
        bbm = indicators_dict.get('bbm_20_2.0_2.0')
        bbu = indicators_dict.get('bbu_20_2.0_2.0')
        bbb = indicators_dict.get('bbb_20_2.0_2.0')
        bbp = indicators_dict.get('bbp_20_2.0_2.0')
        
        if bbl is not None and not pd.isna(bbl):
            # Calculate signal based on percent B
            pct_b = round(float(bbp), 2)
            if pct_b > 0.8:
                signal = "near_upper"
            elif pct_b < 0.2:
                signal = "near_lower"
            else:
                signal = "neutral"
                
            tech_dict["bollinger_bands"] = {
                "upper": round(float(bbu), 2),
                "middle": round(float(bbm), 2),
                "lower": round(float(bbl), 2),
                "width_pct": round(float(bbb), 2),
                "percent_b": pct_b,
                "signal": signal
            }
        else:
            tech_dict["bollinger_bands"] = {
                "upper": 0.0,
                "middle": 0.0,
                "lower": 0.0,
                "width_pct": 0.0,
                "percent_b": 0.0,
                "signal": "unknown"
            }
            
        # 4. Supertrend
        # pandas_ta column naming for Supertrend(7, 3.0):
        # SUPERT_7_3.0 (value), SUPERTd_7_3.0 (direction: 1 for bull, -1 for bear), SUPERTl_7_3.0 (long line), SUPERTs_7_3.0 (short line)
        st_val = indicators_dict.get('SUPERT_7_3.0')
        st_dir = indicators_dict.get('SUPERTd_7_3.0')
        
        if st_val is not None and not pd.isna(st_val):
            if st_dir == 1:
                direction = "bullish"
            elif st_dir == -1:
                direction = "bearish"
            else:
                direction = "neutral"
                
            tech_dict["supertrend"] = {
                "value": round(float(st_val), 2),
                "direction": direction
            }
        else:
            tech_dict["supertrend"] = {
                "value": 0.0,
                "direction": "unknown"
            }
            
        # 5. Stochastic RSI
        # pandas_ta column naming for StochRSI(14, 14, 3, 3):
        # STOCHRSIk_14_14_3_3 (k line), STOCHRSId_14_14_3_3 (d line)
        stoch_k = indicators_dict.get('STOCHRSIk_14_14_3_3')
        stoch_d = indicators_dict.get('STOCHRSId_14_14_3_3')
        
        if stoch_k is not None and not pd.isna(stoch_k) and stoch_d is not None and not pd.isna(stoch_d):
            k_val = round(float(stoch_k), 2)
            d_val = round(float(stoch_d), 2)
            
            if k_val > 80:
                signal = "overbought"
            elif k_val < 20:
                signal = "oversold"
            else:
                signal = "neutral"
                
            tech_dict["stochastic_rsi"] = {
                "k": k_val,
                "d": d_val,
                "signal": signal
            }
        else:
            tech_dict["stochastic_rsi"] = {
                "k": 0.0,
                "d": 0.0,
                "signal": "unknown"
            }
            
        # 6. EMAs (21 and 50)
        ema_21 = indicators_dict.get('ema_21')
        ema_50 = indicators_dict.get('ema_50')
        
        if ema_21 is not None and not pd.isna(ema_21) and ema_50 is not None and not pd.isna(ema_50):
            ema21_val = round(float(ema_21), 2)
            ema50_val = round(float(ema_50), 2)
            
            if ema21_val > ema50_val:
                cross_signal = "bullish"
            elif ema21_val < ema50_val:
                cross_signal = "bearish"
            else:
                cross_signal = "neutral"
                
            tech_dict["ema"] = {
                "ema21": ema21_val,
                "ema50": ema50_val,
                "ema_cross": cross_signal
            }
        else:
            tech_dict["ema"] = {
                "ema21": 0.0,
                "ema50": 0.0,
                "ema_cross": "unknown"
            }
            
        # 7. ADX
        # pandas_ta column naming for ADX(14): ADX_14
        adx = indicators_dict.get('ADX_14')
        
        if adx is not None and not pd.isna(adx):
            adx_val = round(float(adx), 2)
            
            if adx_val > 50:
                strength = "very_strong"
            elif adx_val > 25:
                strength = "strong"
            elif adx_val < 20:
                strength = "weak"
            else:
                strength = "neutral"
                
            tech_dict["adx"] = {
                "value": adx_val,
                "trend_strength": strength
            }
        else:
            tech_dict["adx"] = {
                "value": 0.0,
                "trend_strength": "unknown"
            }
            
        # 8. ATR
        # pandas_ta column naming for ATR(14): ATRe_14 (Exponential by default) or ATRr_14 (RMA) or ATR_14
        # Since pandas-ta 0.3.1.4b0, default for ta.atr is ATR_14, often ATRr_14 (RMA based)
        atr = indicators_dict.get('ATRr_14')
        if atr is None:
            atr = indicators_dict.get('ATR_14')
            
        if atr is not None and not pd.isna(atr):
            atr_val = round(float(atr), 2)
            
            # 5-min Intraday thresholds roughly tailored for NIFTY ~25000:
            if atr_val > 30:
                volatility = "high"
            elif atr_val < 15:
                volatility = "low"
            else:
                volatility = "normal"
                
            tech_dict["atr"] = {
                "value": atr_val,
                "volatility": volatility
            }
        else:
            tech_dict["atr"] = {
                "value": 0.0,
                "volatility": "unknown"
            }
            
        return tech_dict

    def compute_term_structure_liquidity(self, market_quotes: dict, metadata_map: dict):
        """
        Calculates term structure liquidity across the next 5 expiries for ATM options.
        market_quotes: payload from fetcher.get_market_quote()
        metadata_map: dict mapping instrument_key -> respective contract metadata dict
        """
        results = []
        try:
            if not isinstance(market_quotes, dict):
                logger.error(f"[compute_term_structure_liquidity] Invalid market_quotes type: {type(market_quotes)}")
                return results
            if not isinstance(metadata_map, dict):
                logger.error(f"[compute_term_structure_liquidity] Invalid metadata_map type: {type(metadata_map)}")
                return results

            for key, quote in market_quotes.items():
                meta = metadata_map.get(key, {})
                symbol = meta.get('trading_symbol', meta.get('symbol', key))
                strike = meta.get('strike_price', 0.0)
                option_type = meta.get('instrument_type', 'Unknown')

                # Format expiry directly from timestamp or string safely
                expiry_str = meta.get('expiry')
                formatted_expiry = ""
                if expiry_str:
                    try:
                        if isinstance(expiry_str, str) and "-" in expiry_str:
                            dt = pd.to_datetime(expiry_str).date()
                            formatted_expiry = dt.strftime('%Y-%m-%d')
                        else:
                            dt = pd.to_datetime(int(expiry_str), unit='ms').date()
                            formatted_expiry = dt.strftime('%Y-%m-%d')
                    except Exception:
                        formatted_expiry = str(expiry_str)

                # Extract raw metrics from market quote schema
                total_buy = quote.get('total_buy_quantity')
                if total_buy is None: total_buy = 0.0
                total_sell = quote.get('total_sell_quantity')
                if total_sell is None: total_sell = 0.0

                last_price = quote.get('last_price', 0.0)
                timestamp = quote.get('timestamp', "")

                # Formulate buy pressure explicitly based on order book aggregates
                buy_pressure_pct = 0.0
                if total_buy + total_sell > 0:
                    buy_pressure_pct = round((total_buy / (total_buy + total_sell)) * 100, 2)

                # Compute deep liquidity proxy ('large trades') from active Level 2 depth
                depth = quote.get('depth', {})
                large_trades_count = 0
                if depth:
                    buy_depth = depth.get('buy', [])
                    sell_depth = depth.get('sell', [])
                    for item in buy_depth + sell_depth:
                        if item.get('quantity', 0) > 1000:
                            large_trades_count += 1

                results.append({
                    "instrument_metadata": {
                        "symbol": symbol,
                        "strike_price": float(strike),
                        "option_type": option_type,
                        "expiry": formatted_expiry
                    },
                    "liquidity_context": {
                        "large_trades_count": large_trades_count,
                        "buy_pressure_pct": buy_pressure_pct,
                        "total_buy_qty": total_buy,
                        "total_sell_qty": total_sell,
                        "last_traded_price": last_price,
                        "timestamp": timestamp
                    }
                })

        except Exception as e:
            logger.error(f"[compute_term_structure_liquidity] Error calculating term structure liquidity: {e}")

        return results

    def _safe_num(self, value, decimals=4):
        """Safely convert a numeric value, returning None if NaN/missing."""
        if value is None:
            return None
        try:
            f = float(value)
            return round(f, decimals) if not pd.isna(f) else None
        except (TypeError, ValueError):
            return None

    # Maps lowercase pandas-ta column names (from df.columns.str.lower())
    # to DB column names (underscores, no dots).
    _PANDAS_TA_TO_DB: dict[str, str] = {
        # Bollinger Bands (length=20, std=2.0 → BBL_20_2.0_2.0 after pandas-ta lowercased)
        "bbl_20_2.0_2.0": "bbl_20_2_0",
        "bbm_20_2.0_2.0": "bbm_20_2_0",
        "bbu_20_2.0_2.0": "bbu_20_2_0",
        "bbb_20_2.0_2.0": "bbb_20_2_0",
        "bbp_20_2.0_2.0": "bbp_20_2_0",
        # Supertrend (length=7, multiplier=3.0 → SUPERT_7_3.0 after pandas-ta lowercased)
        "supert_7_3.0": "supert_10_3",
        "supertd_7_3.0": "supertd_10_3",
        "supertl_7_3.0": "supertl_10_3",
        "superts_7_3.0": "superts_10_3",
    }

    def _lowercase_top_level_keys(self, d: dict) -> dict:
        """
        Lowercases top-level keys for Postgres identifier compatibility.
        Uses explicit pandas-ta name mapping for dotted columns.
        pandas-ta generates uppercase keys (e.g. 'BBL_20_2.0_2.0') so we first
        lowercase them to match the _PANDAS_TA_TO_DB lookup keys.
        """
        out = {}
        for k, v in d.items():
            lowered = k.lower()
            db_key = self._PANDAS_TA_TO_DB.get(lowered, lowered)
            out[db_key] = v
        return out

    def generate_5min_sync_payload(self, current_timestamp, synthetic_ohlc, net_gex, indicators_dict):
        """
        Packages the calculated data into a single row dictionary
        ready to be stored in the Supabase `market_data` table.

        Schema design:
        - Scalar columns (top-level): for fast WHERE/HAVING queries by the agent
        - JSONB columns: for rich context objects, accessed via ->> or full object fetch
        - timestamp (PK, timestamptz): precise candle-close time in IST
        """
        ind = indicators_dict  # shorthand

        # Helper to safely extract indicator values with pandas-na handling
        def safe_val(key, fallback=None):
            val = ind.get(key, fallback)
            if val is None:
                return None
            try:
                f = float(val)
                return f if not pd.isna(f) else None
            except (TypeError, ValueError):
                return None

        payload = {
            # ── Primary Key ──────────────────────────────────────────────
            # Supabase uses `timestamp` as the unique PK. IST timestamps are stored
            # as timezone-aware so queries like "data at 9:30 AM" work correctly.
            "timestamp": current_timestamp.isoformat(),

            # ── Symbol ───────────────────────────────────────────────────
            "symbol": "NIFTY50",

            # ── OHLCV ────────────────────────────────────────────────────
            "Open": self._safe_num(synthetic_ohlc.get('open')),
            "High": self._safe_num(synthetic_ohlc.get('high')),
            "Low": self._safe_num(synthetic_ohlc.get('low')),
            "Close": self._safe_num(synthetic_ohlc.get('close')),
            "Volume": int(synthetic_ohlc['volume']) if synthetic_ohlc.get('volume') else None,
            "OI": 0,  # Placeholder — integrate Upstox futures OI when available

            # ── Core Indicators (scalar columns) ──────────────────────────
            "VWAP_D": self._safe_num(ind.get('vwap'), decimals=2),
            "EMA_21": self._safe_num(ind.get('ema_21'), decimals=2),
            "EMA_50": self._safe_num(ind.get('ema_50'), decimals=2),
            "RSI_14": self._safe_num(ind.get('rsi_14')),
            "ADX_14": self._safe_num(ind.get('adx_14')),
            "ADXR_14_2": self._safe_num(ind.get('adxr_14_2')),
            "DMP_14": self._safe_num(ind.get('dmp_14')),
            "DMN_14": self._safe_num(ind.get('dmn_14')),
            "ATRr_14": self._safe_num(ind.get('atrr_14')),

            # MACD — pandas-ta generates MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
            # After df.columns.str.lower() → macd_12_26_9, macdh_12_26_9, macds_12_26_9
            "MACD_12_26_9": self._safe_num(ind.get('macd_12_26_9')),
            "MACDh_12_26_9": self._safe_num(ind.get('macdh_12_26_9')),
            "MACDs_12_26_9": self._safe_num(ind.get('macds_12_26_9')),

            # Bollinger Bands — pandas-ta (length=20, std=2.0)
            # pandas-ta format: BBL_{length}_{std}_{2.0} → lowercased: bbl_20_2.0_2.0
            "BBL_20_2.0_2.0": self._safe_num(ind.get('bbl_20_2.0_2.0')),
            "BBM_20_2.0_2.0": self._safe_num(ind.get('bbm_20_2.0_2.0')),
            "BBU_20_2.0_2.0": self._safe_num(ind.get('bbu_20_2.0_2.0')),
            "BBB_20_2.0_2.0": self._safe_num(ind.get('bbb_20_2.0_2.0')),
            "BBP_20_2.0_2.0": self._safe_num(ind.get('bbp_20_2.0_2.0')),

            # Supertrend — pandas-ta (length=7, multiplier=3.0)
            # pandas-ta format: SUPERT_{length}_{multiplier} → lowercased: supert_7_3.0
            # Mapping converts to DB column 'supert_10_3' (DB uses length=10 naming convention)
            "SUPERT_7_3.0": self._safe_num(ind.get('supert_7_3.0')),
            "SUPERTd_7_3.0": self._safe_num(ind.get('supertd_7_3.0')),
            # supertl is NaN in bullish trends — pandas-ta uses NaN to indicate "no lower band"
            "SUPERTl_7_3.0": self._safe_num(ind.get('supertl_7_3.0')) if not pd.isna(ind.get('supertl_7_3.0')) else None,
            "SUPERTs_7_3.0": self._safe_num(ind.get('superts_7_3.0')),

            # Stochastic RSI — pandas-ta (length=14, rsi_length=14, k=3, d=3)
            # Before lowercase: STOCHRSIk_14_14_3_3 → after: stochrsik_14_14_3_3
            "STOCHRSIk_14_14_3_3": self._safe_num(ind.get('stochrsik_14_14_3_3')),
            "STOCHRSId_14_14_3_3": self._safe_num(ind.get('stochrsid_14_14_3_3')),

            # ── Derived Metrics (scalar columns) ─────────────────────────
            "net_gex": self._safe_num(net_gex),
            "opening_range_status": ind.get('opening_range_status', 'Unknown'),
            # Note: main.py passes 'cpr_relationship' but DB column is 'cpr_status'
            "cpr_status": ind.get('cpr_relationship', 'Unknown'),
            "cpr_width": ind.get('cpr_width', 'Unknown'),
            # vwap_status is a dict from compute_vwap_status_dict — extract string for scalar col
            "vwap_status": ind.get('vwap_status', {}).get('price_vs_vwap', 'Unknown'),

            # ── JSONB: Session Meta ───────────────────────────────────────
            "meta": {
                "ticker": ind.get('meta', {}).get('ticker', 'NIFTY'),
                "live_price": self._safe_num(ind.get('meta', {}).get('live_price')),
                "is_index": ind.get('meta', {}).get('is_index', True),
                "session_phase": ind.get('meta', {}).get('session_phase', 'Unknown'),
                "market_time": ind.get('meta', {}).get('market_time', ''),
                "timestamp": ind.get('meta', {}).get('timestamp', ''),
            },

            # ── JSONB: Catalyst / Gap Analysis ───────────────────────────
            "catalyst_context": ind.get('catalyst_context', {}),

            # ── JSONB: Index Macro / VIX ────────────────────────────────
            "index_macro": ind.get('index_macro', {}),

            # ── JSONB: VIX Context (separate for fast access) ───────────
            "vix_context": {
                "vix_level": ind.get('index_macro', {}).get('vix', {}).get('level', 0),
                "vix_change": ind.get('index_macro', {}).get('vix', {}).get('change', 0),
                "vix_velocity": ind.get('index_macro', {}).get('vix_velocity', 'Unknown'),
                "vix_crush_detected": ind.get('index_macro', {}).get('vix_crush_detected', False),
            },

            # ── JSONB: Options Macro (PCR, Max Pain, Gamma) ─────────────
            "options_macro": {
                "net_gex": self._safe_num(net_gex),
                "pcr": ind.get('pcr', {}),
                "max_pain": ind.get('max_pain', {}),
                "gamma_walls": ind.get('gamma_walls', {}),
                "gamma_flip_point": self._safe_num(ind.get('gamma_flip_point')),
                "distance_to_gamma": ind.get('distance_to_gamma', 'N/A'),
                "gamma_wall_proximity": ind.get('gamma_walls', {}).get('gamma_wall_proximity', False),
            },

            # ── JSONB: Advanced Metrics (futures basis, VWAP) ───────────
            "advanced_metrics": {
                "cost_of_carry": ind.get('cost_of_carry', {}),
                "true_vwap": ind.get('true_vwap', {}),
                "vwap_context": ind.get('vwap_context', {}),
            },

            # ── JSONB: Options Chain Analysis ────────────────────────────
            "options_chain_analysis": {
                "pcr": self._safe_num(ind.get('pcr', {}).get('live_pcr')),
                "call_wall": self._safe_num(ind.get('gamma_walls', {}).get('call_wall_strike')),
                "put_wall": self._safe_num(ind.get('gamma_walls', {}).get('put_wall_strike')),
                "call_wall_oi_change": self._safe_num(ind.get('gamma_walls', {}).get('call_wall_oi_change')),
                "put_wall_oi_change": self._safe_num(ind.get('gamma_walls', {}).get('put_wall_oi_change')),
                "max_pain": self._safe_num(ind.get('max_pain', {}).get('max_pain_strike')),
                "net_gex": self._safe_num(net_gex),
                "atm_iv": self._safe_num(ind.get('atm_iv')),
                "atm_iv_change": self._safe_num(ind.get('atm_iv_change')),
                "base_price": self._safe_num(synthetic_ohlc.get('close')),
            },

            # ── JSONB: Intraday Structure ────────────────────────────────
            "key_intraday_levels": ind.get('key_intraday_levels', {}),
            "momentum_burst": ind.get('momentum_burst', {}),
            "institutional_context": ind.get('institutional_context', {}),
            "heavyweight_vs_vwap": ind.get('heavyweight_vs_vwap', {}),
            "volume_profile": ind.get('volume_profile', {}),
            "derived_features": ind.get('derived_features', {}),
            "market_internals": ind.get('market_internals', {}),

            # ── JSONB: Arrays ───────────────────────────────────────────
            "term_structure_liquidity": ind.get('term_structure_liquidity', []),
            "options_decision_matrix": ind.get('options_decision_matrix', []),

            # ── Processing Flag ───────────────────────────────────────────
            "is_processed": True,
        }
        # Postgres normalizes unquoted identifiers to lowercase — match that here
        return self._lowercase_top_level_keys(payload)
