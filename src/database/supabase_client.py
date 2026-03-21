import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


class RemoteDBWatcher:
    """
    Handles all Supabase read/write operations for market data.

    Architecture:
    - Uses supabase-py (PostgREST API) for normal upserts and reads
    - Falls back to direct psycopg2 SQL when PostgREST schema cache is stale
      (can happen after schema migrations until Supabase auto-refreshes)
    """

    def __init__(self):
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        if not url or not key:
            print("WARNING: SUPABASE_URL or SUPABASE_KEY missing. Running in Dry-Run Mode.")
            self.supabase = None
            self._raw_conn = None
        else:
            self.supabase: Client = create_client(url, key)
            print("Initialized Supabase Client (PostgREST + psycopg2).")

        # Lazy psycopg2 connection for direct SQL fallback
        self._raw_conn = None

    # ─── Direct SQL helpers ──────────────────────────────────────────────

    def _get_raw_conn(self):
        """Returns a psycopg2 connection using the SUPABASE_DB_URL env var."""
        if self._raw_conn is not None:
            try:
                self._raw_conn.ping()
                return self._raw_conn
            except Exception:
                self._raw_conn = None

        db_url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
        if not db_url:
            return None
        try:
            import psycopg2
            self._raw_conn = psycopg2.connect(db_url)
            return self._raw_conn
        except Exception as e:
            print(f"[RemoteDBWatcher] Failed to open psycopg2 connection: {e}")
            return None

    def _upsert_raw_sql(self, data: dict) -> list | None:
        """
        Direct SQL upsert via psycopg2 — bypasses PostgREST schema cache.
        Used as fallback when PostgREST doesn't know about new columns yet.
        """
        conn = self._get_raw_conn()
        if conn is None:
            return None

        try:
            cols = list(data.keys())
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(f'"{c}"' for c in cols)
            update_clause = ", ".join(
                f'"{c}" = EXCLUDED."{c}"' for c in cols if c != "timestamp"
            )

            sql = f"""
                INSERT INTO market_data ({col_names})
                VALUES ({placeholders})
                ON CONFLICT (timestamp) DO UPDATE SET {update_clause}
            """
            vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in data.values()]

            with conn.cursor() as cur:
                cur.execute(sql, list(vals))
                conn.commit()
                cur.execute('SELECT * FROM market_data WHERE timestamp = %s', (data["timestamp"],))
                rows = cur.fetchall()
                cols_out = [desc[0] for desc in cur.description]
                return [dict(zip(cols_out, row)) for row in rows]
        except Exception as e:
            print(f"[RemoteDBWatcher] Raw SQL upsert failed: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            return None

    # ─── Public API ───────────────────────────────────────────────────

    def upsert_5min_summary(self, data: dict) -> list | None:
        """
        Upserts a 5-minute summary row into the 'market_data' table.

        Strategy:
        1. Try PostgREST upsert first (fast, correct for cached schemas)
        2. Fall back to direct psycopg2 SQL if PostgREST returns PGRST204
           (schema cache is stale after migrations)
        """
        if not self.supabase:
            print("DRY-RUN: upsert_5min_summary received payload.")
            return [data]

        try:
            response = self.supabase.table("market_data").upsert(data).execute()
            return response.data
        except Exception as e:
            error_str = str(e)
            # Check for PostgREST schema cache staleness
            if "PGRST204" in error_str or "Could not find the" in error_str:
                print("[RemoteDBWatcher] PostgREST schema cache stale — trying direct SQL fallback.")
                result = self._upsert_raw_sql(data)
                if result is not None:
                    print("[RemoteDBWatcher] Direct SQL fallback succeeded.")
                    return result
            print(f"[RemoteDBWatcher] Upsert failed (all strategies): {e}")
            return None

    def get_latest_summary(self) -> list | None:
        """
        Fetches the most recent market_data row.
        """
        try:
            response = (
                self.supabase.table("market_data")
                .select("*")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"[RemoteDBWatcher] get_latest_summary error: {e}")
            return None

    def get_latest(self) -> dict | None:
        """
        Fetches the most recent market_data row as a flat dict (alias for convenience).
        """
        rows = self.get_latest_summary()
        return rows[0] if rows else None

    def get_historical_max_pain(self, target_timestamp_str: str) -> float:
        """
        Fetches max_pain_strike at or after a target timestamp from options_macro JSONB.
        """
        try:
            if not self.supabase:
                return 0.0
            response = (
                self.supabase.table("market_data")
                .select("options_macro")
                .gte("timestamp", target_timestamp_str)
                .order("timestamp", desc=False)
                .limit(1)
                .execute()
            )
            if not response.data:
                return 0.0
            macro = response.data[0].get("options_macro", {})
            if not isinstance(macro, dict):
                return 0.0
            pain = macro.get("max_pain", {})
            if isinstance(pain, dict):
                return float(pain.get("max_pain_strike", 0.0))
            return 0.0
        except Exception as e:
            print(f"[RemoteDBWatcher] get_historical_max_pain error: {e}")
            return 0.0

    def get_historical_pcr_array(self, days_back: int = 20) -> list[float]:
        """
        Fetches PCR history over the last N trading days from options_macro JSONB.
        Returns a list of float PCR values.
        """
        import datetime
        try:
            if not self.supabase:
                return []
            from_str = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=days_back + 10)
            ).isoformat()
            response = (
                self.supabase.table("market_data")
                .select("options_macro")
                .gte("timestamp", from_str)
                .order("timestamp", desc=True)
                .execute()
            )
            pcr_history = []
            for row in response.data:
                macro = row.get("options_macro", {})
                if not isinstance(macro, dict):
                    continue
                pcr_node = macro.get("pcr", {})
                if isinstance(pcr_node, dict):
                    val = pcr_node.get("live_pcr")
                    if val is not None and float(val) > 0.0:
                        pcr_history.append(float(val))
            return pcr_history
        except Exception as e:
            print(f"[RemoteDBWatcher] get_historical_pcr_array error: {e}")
            return []

    def get_historical_vix_array(self, days_back: int = 20) -> list[float]:
        """
        Fetches India VIX history over the last N trading days from index_macro JSONB.
        Returns a list of float VIX level values.
        """
        import datetime
        try:
            if not self.supabase:
                return []
            from_str = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=days_back + 10)
            ).isoformat()
            response = (
                self.supabase.table("market_data")
                .select("index_macro")
                .gte("timestamp", from_str)
                .order("timestamp", desc=True)
                .execute()
            )
            vix_history = []
            for row in response.data:
                macro = row.get("index_macro", {})
                if not isinstance(macro, dict):
                    continue
                vix_node = macro.get("vix", {})
                if isinstance(vix_node, dict):
                    val = vix_node.get("level")
                    if val is not None and float(val) > 0.0:
                        vix_history.append(float(val))
            return vix_history
        except Exception as e:
            print(f"[RemoteDBWatcher] get_historical_vix_array error: {e}")
            return []

    def get_config(self, key_name: str) -> str | None:
        """Retrieves a value from the app_config table."""
        try:
            if not self.supabase:
                return None
            response = (
                self.supabase.table("app_config")
                .select("value")
                .eq("key", key_name)
                .execute()
            )
            return response.data[0].get("value") if response.data else None
        except Exception as e:
            print(f"[RemoteDBWatcher] get_config error: {e}")
            return None

    def set_config(self, key_name: str, value: str) -> list | None:
        """Stores a key-value pair in the app_config table."""
        try:
            if not self.supabase:
                return None
            response = (
                self.supabase.table("app_config")
                .upsert({"key": key_name, "value": value})
                .execute()
            )
            return response.data
        except Exception as e:
            print(f"[RemoteDBWatcher] set_config error: {e}")
            return None

    def __del__(self):
        """Clean up psycopg2 connection on shutdown."""
        if self._raw_conn is not None:
            try:
                self._raw_conn.close()
            except Exception:
                pass
