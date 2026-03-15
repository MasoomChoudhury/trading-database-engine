import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class RemoteDBWatcher:
    def __init__(self):
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        if not url or not key:
            print("WARNING: Supabase URL/Key missing. Running in Dry-Run Mode. Database writes will be mocked.")
            self.supabase = None
        else:
            self.supabase: Client = create_client(url, key)
            print("Initialized Supabase Client.")

    def upsert_5min_summary(self, data: dict):
        """
        Upserts a 5-minute summary row into the 'market_data' table.
        The table should have a UNIQUE constraint on (timestamp) or (timestamp, instrument_token).
        """
        try:
            if not self.supabase:
                print("DRY-RUN: Upsert triggered. Supabase mock received Payload.")
                return data
            
            # The 'upsert' method in Supabase-py relies on primary keys or unique constraints
            response = self.supabase.table('market_data').upsert(data).execute()
            return response.data
        except Exception as e:
            print(f"Error upserting to Supabase: {e}")
            return None

    def get_latest_summary(self):
        """
        Fetches the most recent 5-minute summary for debugging or baseline checks.
        """
        try:
            response = self.supabase.table('market_data').select('*').order('timestamp', desc=True).limit(1).execute()
            return response.data
        except Exception as e:
            print(f"Error fetching from Supabase: {e}")
            return None

    def get_historical_max_pain(self, target_timestamp_str: str):
        """
        Queries the database for a specific historical timestamp (e.g., 24 hours ago).
        Extracts the nested `max_pain_strike` from the `options_macro` JSON obj.
        """
        try:
            if not self.supabase: return 0.0
            
            # We look for a row exactly at or shortly after the target timestamp
            response = self.supabase.table('market_data')\
                .select('options_macro')\
                .gte('ts', target_timestamp_str)\
                .order('ts', desc=False)\
                .limit(1)\
                .execute()
                
            if response.data and len(response.data) > 0:
                row = response.data[0]
                macro = row.get('options_macro', {})
                if macro and isinstance(macro, dict):
                    pain = macro.get('max_pain', {})
                    if pain and isinstance(pain, dict):
                        return float(pain.get('max_pain_strike', 0.0))
            return 0.0
            
        except Exception as e:
            print(f"Error fetching historical max pain from DB: {e}")
            return 0.0

    def get_historical_pcr_array(self, days_back: int = 20):
        """
        Queries the database to extract an array of historical PCR values over the last X trading days.
        Used to calculate mathematical percentiles (e.g. 90th percentile PCR).
        """
        import datetime
        try:
            if not self.supabase: return []
            
            from_date_str = (datetime.datetime.now() - datetime.timedelta(days=days_back + 10)).isoformat()
            
            # Fetch the `options_macro` json dict for the recent timeline
            response = self.supabase.table('market_data')\
                .select('options_macro')\
                .gte('ts', from_date_str)\
                .order('ts', desc=True)\
                .execute()
                
            pcr_history = []
            
            if response.data:
                for row in response.data:
                    macro = row.get('options_macro', {})
                    if macro and isinstance(macro, dict):
                        # Safely navigate to options_macro -> pcr -> live_pcr
                        pcr_node = macro.get('pcr', {})
                        if pcr_node and isinstance(pcr_node, dict):
                            pcr_val = pcr_node.get('live_pcr', None)
                            if pcr_val is not None and pcr_val > 0.0:
                                pcr_history.append(float(pcr_val))
                                
            return pcr_history
            
        except Exception as e:
            print(f"Error fetching historical PCR array from DB: {e}")
            return []
            
    def get_historical_vix_array(self, days_back: int = 20):
        """
        Queries the database to extract an array of historical India VIX values over the last X trading days.
        Used to calculate mathematical IV Rank (Implied Volatility Percentile).
        """
        import datetime
        try:
            from_date_str = (datetime.datetime.now() - datetime.timedelta(days=days_back + 10)).isoformat()
            
            # Fetch the `index_macro` json dict for the recent timeline
            response = self.supabase.table('market_data')\
                .select('index_macro')\
                .gte('ts', from_date_str)\
                .order('ts', desc=True)\
                .execute()
                
            vix_history = []
            
            if response.data:
                for row in response.data:
                    macro = row.get('index_macro', {})
                    if macro and isinstance(macro, dict):
                        # Safely navigate to index_macro -> vix -> level
                        vix_node = macro.get('vix', {})
                        if vix_node and isinstance(vix_node, dict):
                            vix_val = vix_node.get('level', None)
                            if vix_val is not None and vix_val > 0.0:
                                vix_history.append(float(vix_val))
                                
            return vix_history
            
        except Exception as e:
            print(f"Error fetching historical VIX array from DB: {e}")
            return []
    def get_config(self, key_name: str):
        """
        Retrieves a configuration value from the 'app_config' table.
        Used for persistent storage of tokens, etc.
        """
        try:
            if not self.supabase: return None
            response = self.supabase.table('app_config').select('value').eq('key', key_name).execute()
            if response.data:
                return response.data[0].get('value')
            return None
        except Exception as e:
            print(f"Error fetching config {key_name}: {e}")
            return None

    def set_config(self, key_name: str, value: str):
        """
        Stores a configuration value in the 'app_config' table.
        """
        try:
            if not self.supabase: return None
            data = {"key": key_name, "value": value}
            response = self.supabase.table('app_config').upsert(data).execute()
            return response.data
        except Exception as e:
            print(f"Error setting config {key_name}: {e}")
            return None
