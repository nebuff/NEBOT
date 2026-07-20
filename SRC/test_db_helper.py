import os
import sqlite3
import db_service

DB_TEST_FILE = os.path.join(os.path.dirname(__file__), "..", "DATA", "test_nebot.db")

def init_test_db():
    # Close any open connections
    db_service.close_db_connection()
    # Set to test database
    db_service.set_db_file(DB_TEST_FILE)
    
    # Remove file if exists
    if os.path.exists(DB_TEST_FILE):
        try:
            os.remove(DB_TEST_FILE)
        except Exception:
            pass
            
    # Connect and setup schema
    conn = sqlite3.connect(DB_TEST_FILE)
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
    conn.close()
