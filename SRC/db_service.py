import os
import re
import sqlite3
import threading

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'DATA')
DB_FILE = os.path.join(DATA_DIR, os.getenv('SQLITE_DATABASE', 'nebot.db'))

def translate_sql(sql: str) -> str:
    sql_upper = sql.strip().upper()
    if sql_upper.startswith("PRAGMA"):
        return "SELECT 1;"

    sql = sql.replace('?', '%s')
    sql = re.sub(r'(?i)\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b', 'SERIAL PRIMARY KEY', sql)
    sql = re.sub(r'(?i)\bINTEGER\b', 'BIGINT', sql)

    ignore_match = re.search(r'(?i)\bINSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)', sql)
    if ignore_match:
        table = ignore_match.group(1).lower()
        conflict_target = ""
        if table == "users":
            conflict_target = "(user_id)"
        elif table == "guild_configs":
            conflict_target = "(guild_id)"
        elif table == "members":
            conflict_target = "(user_id, short_name)"
        elif table == "warnings":
            conflict_target = "(id)"
        elif table == "warning_linked_accounts":
            conflict_target = "(id)"
        elif table == "join_filtering_logs":
            conflict_target = "(id)"
        
        sql_clean = re.sub(r'(?i)\bINSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)', r'INSERT INTO \1', sql)
        sql_clean = sql_clean.strip().rstrip(';')
        if conflict_target:
            sql_clean += f" ON CONFLICT {conflict_target} DO NOTHING"
        return sql_clean + ";"

    replace_match = re.search(r'(?i)\bINSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\((.*?)\)', sql, re.DOTALL)
    if replace_match:
        table = replace_match.group(1).lower()
        cols_str = replace_match.group(2)
        cols = [c.strip().lower() for c in cols_str.split(',')]
        
        conflict_target = ""
        if table == "server_analytics":
            conflict_target = "(guild_id)"
        elif table == "battle_stats":
            conflict_target = "(user_id)"
        elif table == "global_configs":
            conflict_target = "(key)"
        elif table == "guild_configs":
            conflict_target = "(guild_id)"
        elif table == "members":
            conflict_target = "(user_id, short_name)"
        elif table == "proxy_tags":
            conflict_target = "(member_id)"
        elif table == "proxied_messages":
            conflict_target = "(message_id)"
        elif table == "sessions":
            conflict_target = "(session_id)"
        elif table == "vc_wr_records":
            conflict_target = "(guild_id, user_id)"
        elif table == "vc_wr_sessions":
            conflict_target = "(guild_id, user_id)"
        elif table == "warnings":
            conflict_target = "(id)"
        
        if conflict_target:
            target_cols = re.findall(r'\w+', conflict_target.lower())
            update_cols = [c for c in cols if c not in target_cols]
            update_clause = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_cols])
            
            sql_clean = re.sub(r'(?i)\bINSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)', r'INSERT INTO \1', sql)
            sql_clean = sql_clean.strip().rstrip(';')
            sql_clean += f" ON CONFLICT {conflict_target} DO UPDATE SET {update_clause}"
            return sql_clean + ";"

    return sql

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor
        self._lastrowid = None

    def execute(self, query, params=None):
        translated_query = translate_sql(query)
        
        should_return_id = False
        if query.strip().upper().startswith("INSERT"):
            for tbl in ["members", "proxy_tags", "warning_linked_accounts", "join_filtering_logs"]:
                if tbl in query.lower():
                    should_return_id = True
                    break
        
        if should_return_id:
            translated_query = translated_query.strip().rstrip(';') + " RETURNING id;"
            
        try:
            if params is not None:
                self._cursor.execute(translated_query, params)
            else:
                self._cursor.execute(translated_query)
            
            if should_return_id:
                row = self._cursor.fetchone()
                if row:
                    self._lastrowid = row[0]
            else:
                self._lastrowid = None
        except Exception as e:
            print(f"Postgres execution failed for query:\n{translated_query}\nWith params: {params}\nError: {e}")
            raise e
        return self

    def executemany(self, query, params_list):
        translated_query = translate_sql(query)
        try:
            self._cursor.executemany(translated_query, params_list)
            self._lastrowid = None
        except Exception as e:
            print(f"Postgres executemany failed for query:\n{translated_query}\nError: {e}")
            raise e
        return self

    def fetchone(self):
        try:
            return self._cursor.fetchone()
        except Exception:
            return None

    def fetchall(self):
        try:
            return self._cursor.fetchall()
        except Exception:
            return []

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)

class PostgresConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn
        self._row_factory = None

    def cursor(self, *args, **kwargs):
        import psycopg2.extras
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return PostgresCursorWrapper(cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def execute(self, query, params=None):
        cursor = self.cursor()
        return cursor.execute(query, params)

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, val):
        self._row_factory = val

# Thread-local database connection pool/cache
_local = threading.local()



def setup_schema(conn):
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        system_name TEXT,
        fronting_member TEXT
    );
    """)

    # Members Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        short_name TEXT NOT NULL,
        display_name TEXT NOT NULL,
        avatar_url TEXT,
        avatar_msg_id INTEGER,
        avatar_chan_id INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        UNIQUE(user_id, short_name)
    );
    """)

    # Proxy Tags Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proxy_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        proxy_tag TEXT NOT NULL,
        FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE,
        UNIQUE(member_id)
    );
    """)

    # Guild Configs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guild_configs (
        guild_id INTEGER PRIMARY KEY,
        prefix TEXT,
        cmd TEXT,
        channel_id INTEGER,
        admin_role_id INTEGER,
        shared_channel_id INTEGER,
        private_sessions_enabled BOOLEAN,
        shared_enabled BOOLEAN,
        ne_os_enabled BOOLEAN,
        nebuff_module_enabled BOOLEAN,
        battle_enabled BOOLEAN,
        battle_default_hp INTEGER,
        battle_damage_range TEXT,
        battle_timeout INTEGER,
        minesweeper_enabled BOOLEAN,
        minesweeper_default_mines INTEGER,
        warning_tracker_enabled BOOLEAN,
        warning_platforms TEXT, -- JSON array
        warning_severity_points TEXT, -- JSON object
        warning_escalation_mode TEXT,
        warning_rolling_window_days INTEGER,
        warning_ladder TEXT, -- JSON object
        warning_log_channel_id INTEGER,
        warning_dm_enabled BOOLEAN,
        verification_enabled BOOLEAN,
        verification_unverified_role_id INTEGER,
        verification_verified_role_id INTEGER,
        verification_verified_role_ids TEXT, -- JSON array
        verification_channel_id INTEGER,
        verification_landing_channel_id INTEGER,
        global_log_channel_id INTEGER,
        verification_log_channel_id INTEGER,
        verification_timeout INTEGER,
        mod_role_id INTEGER,
        auto_roller_enabled BOOLEAN,
        auto_roller_role_id INTEGER,
        auto_roller_role_ids TEXT, -- JSON array
        automod_enabled BOOLEAN,
        automod_filters TEXT, -- JSON array
        automod_ignored_channels TEXT, -- JSON array
        automod_ignored_roles TEXT, -- JSON array
        music_enabled BOOLEAN,
        music_role_restriction_enabled BOOLEAN,
        music_allowed_roles TEXT, -- JSON array
        music_allowed_users TEXT, -- JSON array
        music_component_restriction_enabled BOOLEAN,
        analytics_enabled BOOLEAN,
        analytics_excluded_channels TEXT, -- JSON array
        vc_wr_enabled BOOLEAN,
        join_filter_enabled BOOLEAN,
        join_filter_min_age_value INTEGER,
        join_filter_min_age_unit TEXT,
        join_filter_username_patterns TEXT, -- JSON array
        join_filter_username_emojis BOOLEAN,
        join_filter_username_homoglyphs BOOLEAN,
        join_filter_enforcement TEXT,
        join_filters TEXT, -- JSON array
        auto_channel_namer_enabled BOOLEAN,
        auto_channel_namer_left TEXT,
        auto_channel_namer_right TEXT,
        auto_channel_namer_font TEXT,
        auto_channel_namer_exclude_ids TEXT, -- JSON array
        plurality_enabled BOOLEAN,
        self_roles_enabled BOOLEAN,
        self_roles_groups TEXT -- JSON array
    );
    """)

    # Global Configs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS global_configs (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)

    # Battle Stats Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS battle_stats (
        user_id TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        total_rounds_won INTEGER DEFAULT 0,
        minesweeper_wins INTEGER DEFAULT 0,
        minesweeper_losses INTEGER DEFAULT 0,
        minesweeper_quits INTEGER DEFAULT 0,
        minesweeper_total_safe_clicks INTEGER DEFAULT 0,
        minesweeper_total_correct_flags INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    );
    """)

    # Warnings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warnings (
        id TEXT PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        details TEXT,
        severity TEXT,
        points INTEGER,
        timestamp TEXT,
        action_taken TEXT,
        FOREIGN KEY(guild_id) REFERENCES guild_configs(guild_id) ON DELETE CASCADE
    );
    """)

    # Warning Linked Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warning_linked_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        warning_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        identifier TEXT NOT NULL,
        display_name TEXT NOT NULL,
        FOREIGN KEY(warning_id) REFERENCES warnings(id) ON DELETE CASCADE
    );
    """)

    # Join Filtering Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS join_filtering_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        username TEXT,
        account_created_at TEXT,
        age_evaluated TEXT,
        reason TEXT,
        action TEXT,
        status TEXT,
        timestamp TEXT,
        FOREIGN KEY(guild_id) REFERENCES guild_configs(guild_id) ON DELETE CASCADE
    );
    """)

    # Proxied Messages Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS proxied_messages (
        message_id TEXT PRIMARY KEY,
        author_id INTEGER NOT NULL,
        content TEXT,
        reply_prefix TEXT,
        channel_id INTEGER NOT NULL,
        timestamp REAL NOT NULL
    );
    """)

    # Sessions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        cwd TEXT NOT NULL, -- JSON array
        installed_packages TEXT NOT NULL, -- JSON array
        history TEXT NOT NULL, -- JSON array
        env TEXT NOT NULL, -- JSON object
        start_time TEXT NOT NULL,
        root TEXT NOT NULL, -- JSON object
        is_persistent BOOLEAN NOT NULL
    );
    """)

    # VC WR Records Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vc_wr_records (
        guild_id INTEGER,
        user_id TEXT,
        duration REAL DEFAULT 0.0,
        PRIMARY KEY(guild_id, user_id)
    );
    """)

    # VC WR Sessions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vc_wr_sessions (
        guild_id INTEGER,
        user_id TEXT,
        join_time REAL,
        PRIMARY KEY(guild_id, user_id)
    );
    """)

    # Server Analytics Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS server_analytics (
        guild_id INTEGER PRIMARY KEY,
        messages TEXT, -- JSON Object
        churn TEXT, -- JSON Array
        voice TEXT -- JSON Array
    );
    """)

    # Indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_user ON members(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_warnings_guild ON warnings(guild_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_warning_accounts_warning ON warning_linked_accounts(warning_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_join_logs_guild ON join_filtering_logs(guild_id);")
    conn.commit()

def set_db_file(file_path):

    close_db_connection()
    global DB_FILE
    DB_FILE = file_path

def get_db_file():
    return DB_FILE

def get_db_connection():
    if not hasattr(_local, "connection") or _local.connection is None:
        db_host = os.getenv("DATABASE_HOST")
        if db_host:
            import psycopg2
            import psycopg2.extras
            import time
            db_port = os.getenv("DATABASE_PORT", "3080")
            db_user = os.getenv("DATABASE_USER", "postgres")
            db_password = os.getenv("DATABASE_PASSWORD", "Frog0101!")
            db_name = os.getenv("DATABASE_NAME", "nebot")
            
            max_attempts = 12
            conn = None
            for attempt in range(1, max_attempts + 1):
                try:
                    conn_pg = psycopg2.connect(
                        host=db_host,
                        port=db_port,
                        user=db_user,
                        password=db_password,
                        dbname="postgres",
                        connect_timeout=3
                    )
                    conn_pg.autocommit = True
                    cur_pg = conn_pg.cursor()
                    cur_pg.execute(f"SELECT 1 FROM pg_database WHERE datname='{db_name}';")
                    if not cur_pg.fetchone():
                        cur_pg.execute(f"CREATE DATABASE {db_name};")
                    cur_pg.close()
                    conn_pg.close()
                    
                    # Connect to target DB
                    raw_conn = psycopg2.connect(
                        host=db_host,
                        port=db_port,
                        user=db_user,
                        password=db_password,
                        dbname=db_name,
                        connect_timeout=3
                    )
                    conn = PostgresConnectionWrapper(raw_conn)
                    setup_schema(conn)
                    _local.connection = conn
                    print(f"Successfully connected to PostgreSQL database '{db_name}' at {db_host}:{db_port}")
                    break
                except Exception as e:
                    print(f"[Attempt {attempt}/{max_attempts}] Failed to connect to PostgreSQL at {db_host}:{db_port}: {e}")
                    if attempt == max_attempts:
                        print(f"CRITICAL: Failed to connect to PostgreSQL at {db_host}:{db_port}: {e}")
                        print("Falling back to local SQLite database...")
                        conn = sqlite3.connect(DB_FILE, timeout=30.0)
                        # Enable WAL mode for concurrency
                        conn.execute("PRAGMA journal_mode=WAL;")
                        conn.execute("PRAGMA synchronous=NORMAL;")
                        conn.execute("PRAGMA synchronous=NORMAL;")
                        conn.execute("PRAGMA foreign_keys = ON;")
                        setup_schema(conn)
                        conn.row_factory = sqlite3.Row
                        _local.connection = conn
                        break
                    print("Retrying connection in 5 seconds...")
                    time.sleep(5)
        else:
            conn = sqlite3.connect(DB_FILE, timeout=30.0)
            # Enable WAL mode for concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            setup_schema(conn)
            conn.row_factory = sqlite3.Row
            _local.connection = conn
    return _local.connection




def close_db_connection():
    if hasattr(_local, "connection") and _local.connection is not None:
        try:
            _local.connection.close()
        except Exception:
            pass
        _local.connection = None
