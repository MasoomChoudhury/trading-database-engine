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

    # ─── Data Integrity Audit ────────────────────────────────────────────

    def audit_candle_gaps(self, hours_back: int = 24) -> dict:
        """
        Detects gaps in 5-minute candle time-series data using LAG() window function.
        A gap exists when the time delta between consecutive rows exceeds 6 minutes.
        Returns dict with gap count and list of gap details.
        """
        conn = self._get_raw_conn()
        if conn is None:
            # Fall back to PostgREST — less precise but works
            return self._audit_via_postgrest(hours_back)

        try:
            sql = f"""
                SELECT
                    ts,
                    ts - LAG(ts) OVER (ORDER BY ts) AS gap
                FROM market_data
                WHERE ts >= NOW() - INTERVAL '{hours_back} hours'
                ORDER BY ts
            """
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                gaps = [
                    {"previous_candle": r[0].isoformat() if r[0] else None,
                     "next_candle": r[1].isoformat() if r[1] else None,
                     "gap_seconds": (r[1] - r[0]).total_seconds() if r[0] and r[1] else None}
                    for r in rows[1:] if r[1] and (r[1] - r[0]).total_seconds() > 360
                ]
                return {"method": "psycopg2", "total_rows": len(rows), "gaps": gaps}

        except Exception as e:
            print(f"[RemoteDBWatcher] audit_candle_gaps error: {e}")
            conn.rollback()
            return self._audit_via_postgrest(hours_back)

    def _audit_via_postgrest(self, hours_back: int = 24) -> dict:
        """Fallback gap audit via PostgREST RPC (calls a stored procedure)."""
        try:
            import datetime
            from_str = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(hours=hours_back)
            ).isoformat()

            response = (
                self.supabase.table("market_data")
                .select("timestamp")
                .gte("timestamp", from_str)
                .order("timestamp", desc=False)
                .execute()
            )

            rows = response.data or []
            gaps = []
            prev_ts = None
            for row in rows:
                ts_str = row.get("timestamp", "")
                if prev_ts:
                    from datetime import datetime as dt
                    prev = dt.fromisoformat(prev_ts.replace("Z", "+00:00"))
                    curr = dt.fromisoformat(ts_str.replace("Z", "+00:00"))
                    delta = (curr - prev).total_seconds()
                    if delta > 360:  # > 6 minutes
                        gaps.append({
                            "previous_candle": prev_ts,
                            "next_candle": ts_str,
                            "gap_seconds": delta,
                        })
                prev_ts = ts_str

            return {"method": "postgrest", "total_rows": len(rows), "gaps": gaps}
        except Exception as e:
            return {"method": "error", "total_rows": 0, "gaps": [], "error": str(e)}

    # ─── TimescaleDB Pruning ────────────────────────────────────────────

    def get_chunk_info(self, end_date: str) -> dict:
        """
        Returns information about chunks that would be dropped for a given end_date.
        Works via direct psycopg2 connection to Supabase.
        """
        conn = self._get_raw_conn()
        if conn is None:
            return {"error": "Cannot connect to database. Check SUPABASE_DB_URL."}

        try:
            sql = """
                SELECT
                    chunk_table->>'chunk_name'       AS chunk_name,
                    chunk_table->>'range_start_time' AS range_start,
                    chunk_table->>'range_end_time'   AS range_end,
                    pg_size_pretty(
                        (chunk_table->>'total_bytes')::bigint
                    )                                AS size
                FROM timescaledb_information.chunks
                WHERE hypertable_name = 'market_data'
                  AND (chunk_table->>'range_end_time')::timestamptz < %s::timestamptz
                ORDER BY range_start ASC
            """
            with conn.cursor() as cur:
                cur.execute(sql, (end_date,))
                rows = cur.fetchall()
                return {
                    "chunks": [
                        {"name": r[0], "start": r[1], "end": r[2], "size": r[3]}
                        for r in rows
                    ],
                    "total_chunks": len(rows),
                }
        except Exception as e:
            # timescaledb_information might not be accessible — try raw pg tables
            try:
                sql = """
                    SELECT
                        inhrelid::regclass::text AS chunk_name,
                        pg_size_pretty(pg_relation_size(inhrelid)) AS size
                    FROM pg_inherits
                    JOIN pg_class ON inhrelid = pg_class.oid
                    WHERE inhparent = 'market_data'::regclass
                      AND pg_relation_size(inhrelid) > 0
                    ORDER BY inhrelid
                """
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
                    return {
                        "chunks": [{"name": r[0], "size": r[1]} for r in rows],
                        "total_chunks": len(rows),
                        "note": "Limited chunk info (TimescaleDB catalog not accessible)",
                    }
            except Exception as inner_e:
                return {"error": f"Chunk query failed: {inner_e}"}
        finally:
            try:
                conn.rollback()
            except Exception:
                pass

    def drop_chunks(self, end_date: str) -> dict:
        """
        Drops TimescaleDB chunks older than end_date.
        Requires direct psycopg2 connection to Supabase.
        """
        conn = self._get_raw_conn()
        if conn is None:
            return {"success": False, "error": "Cannot connect to database. Check SUPABASE_DB_URL."}

        try:
            # First verify the table is a hypertable
            verify_sql = """
                SELECT EXISTS(
                    SELECT 1 FROM timescaledb_information.hypertables
                    WHERE hypertable_name = 'market_data'
                )
            """
            with conn.cursor() as cur:
                cur.execute(verify_sql)
                is_hypertable = cur.fetchone()[0]

            if not is_hypertable:
                # Not a hypertable — just delete old rows
                delete_sql = "DELETE FROM market_data WHERE timestamp < %s::timestamptz"
                with conn.cursor() as cur:
                    cur.execute(delete_sql, (end_date,))
                    deleted = cur.rowcount
                    conn.commit()
                return {"success": True, "method": "delete", "rows_deleted": deleted}

            # It's a hypertable — use drop_chunks
            sql = "SELECT drop_chunks('market_data', older_than => %s::timestamptz)"
            with conn.cursor() as cur:
                cur.execute(sql, (end_date,))
                result = cur.fetchone()
                conn.commit()
            return {"success": True, "method": "drop_chunks", "result": result[0] if result else "done"}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            return {"success": False, "error": str(e)}

    def __del__(self):
        """Clean up psycopg2 connection on shutdown."""
        if self._raw_conn is not None:
            try:
                self._raw_conn.close()
            except Exception:
                pass
