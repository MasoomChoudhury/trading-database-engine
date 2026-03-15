import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

class LocalDBWatcher:
    def __init__(self):
        self.host = os.getenv("TIMESCALEDB_HOST", "localhost")
        self.port = os.getenv("TIMESCALEDB_PORT", "5432")
        self.dbname = os.getenv("TIMESCALEDB_NAME", "options_data")
        self.user = os.getenv("TIMESCALEDB_USER", "postgres")
        self.password = os.getenv("TIMESCALEDB_PASSWORD", "password")
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password
            )
            self.conn.autocommit = True
            print("Connected to Local TimescaleDB.")
        except Exception as e:
            print(f"Error connecting to TimescaleDB: {e}")

    def execute_query(self, query, params=None):
        if not self.conn:
            self.connect()
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                return True
        except Exception as e:
            print(f"Error executing query: {e}")
            return False

    def fetch_all(self, query, params=None):
        if not self.conn:
            self.connect()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return cur.fetchall()
        except Exception as e:
            print(f"Error fetching data: {e}")
            return []
    
    def close(self):
        if self.conn:
            self.conn.close()
            print("TimescaleDB connection closed.")

def init_db():
    db = LocalDBWatcher()
    db.connect()
    
    # Enable TimescaleDB extension if not already enabled
    db.execute_query("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    
    # Create the raw option chain / futures table
    # This stores the tick or 1m data fetched rapidly from Upstox
    create_table_query = """
    CREATE TABLE IF NOT EXISTS options_futures_data (
        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
        instrument_token VARCHAR(50) NOT NULL,
        trading_symbol VARCHAR(100) NOT NULL,
        instrument_type VARCHAR(20) NOT NULL, -- 'CE', 'PE', 'FUT'
        strike_price DOUBLE PRECISION,
        expiry_date DATE,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        volume BIGINT,
        open_interest BIGINT,
        -- Option Greeks (if calculated on the fly or fetched)
        implied_volatility DOUBLE PRECISION,
        delta DOUBLE PRECISION,
        gamma DOUBLE PRECISION,
        theta DOUBLE PRECISION,
        vega DOUBLE PRECISION
    );
    """
    db.execute_query(create_table_query)
    
    # Convert it into a TimescaleDB hypertable partitioned by time
    # This fails gracefully if already a hypertable
    try:
        db.execute_query(
            "SELECT create_hypertable('options_futures_data', 'timestamp', if_not_exists => TRUE);"
        )
        # Create an index for faster querying by instrument and time
        db.execute_query(
            "CREATE INDEX IF NOT EXISTS ix_symbol_time ON options_futures_data (trading_symbol, timestamp DESC);"
        )
        print("TimescaleDB hypertable 'options_futures_data' initialized successfully.")
    except Exception as e:
        print(f"Hypertable initialization note: {e}")
    
    db.close()

if __name__ == "__main__":
    init_db()
