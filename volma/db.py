import os
import sqlite3
import sys

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    region TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT 'RU',
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    address TEXT DEFAULT '',
    capacity_tpd REAL DEFAULT 0,
    stock_t REAL DEFAULT 0,
    products TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS roads (
    id INTEGER PRIMARY KEY,
    a INTEGER NOT NULL REFERENCES nodes(id),
    b INTEGER NOT NULL REFERENCES nodes(id),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    distance_km REAL NOT NULL,
    quality REAL NOT NULL,
    urban REAL NOT NULL DEFAULT 0,
    toll_rub_km REAL NOT NULL DEFAULT 0,
    border INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS road_events (
    id INTEGER PRIMARY KEY,
    road_id INTEGER NOT NULL REFERENCES roads(id),
    kind TEXT NOT NULL,
    severity REAL NOT NULL,
    description TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS weather (
    region TEXT PRIMARY KEY,
    condition TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS traffic_history (
    id INTEGER PRIMARY KEY,
    road_id INTEGER NOT NULL REFERENCES roads(id),
    weekday INTEGER NOT NULL,
    hour INTEGER NOT NULL,
    weather TEXT NOT NULL,
    event INTEGER NOT NULL,
    congestion REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cargo_types (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    price_rub_t REAL NOT NULL,
    loss_base REAL NOT NULL,
    road_sensitivity REAL NOT NULL,
    weather_sensitivity REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY,
    plate TEXT UNIQUE NOT NULL,
    model TEXT NOT NULL,
    body TEXT NOT NULL,
    capacity_t REAL NOT NULL,
    fuel_l_100 REAL NOT NULL,
    base_node INTEGER NOT NULL REFERENCES nodes(id),
    location_node INTEGER NOT NULL REFERENCES nodes(id),
    status TEXT NOT NULL DEFAULT 'свободна',
    odometer_km REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    origin INTEGER NOT NULL REFERENCES nodes(id),
    destination INTEGER NOT NULL REFERENCES nodes(id),
    cargo TEXT NOT NULL REFERENCES cargo_types(code),
    weight_t REAL NOT NULL,
    due_date TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'новый',
    trip_id INTEGER
);
CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    route_nodes TEXT NOT NULL,
    route_roads TEXT NOT NULL,
    distance_km REAL NOT NULL,
    empty_km REAL NOT NULL,
    duration_h REAL NOT NULL,
    fuel_l REAL NOT NULL,
    cost_rub REAL NOT NULL,
    loss_rub REAL NOT NULL,
    baseline_cost_rub REAL NOT NULL,
    baseline_empty_km REAL NOT NULL,
    baseline_fuel_l REAL NOT NULL DEFAULT 0,
    load_t REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'запланирован',
    legs TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "fuel_price": "68.5",
    "driver_rate": "650",
    "vehicle_rate": "900",
    "platon_rub_km": "3.0",
    "late_penalty_rub_h": "4000",
    "w_cost": "1.0",
    "w_time": "1.0",
    "w_risk": "1.0",
    "border_delay_h": "3.0",
}


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def db_path():
    return os.path.join(app_dir(), "data", "volma.db")


class Database:
    def __init__(self, path=None):
        self.path = path or db_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fresh = not os.path.exists(self.path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            self.conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v))
        self.conn.commit()
        if fresh or self.scalar("SELECT COUNT(*) FROM nodes") == 0:
            from .seed import seed
            seed(self)

    def q(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql, params=()):
        return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return row[0] if row else None

    def run(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur.lastrowid

    def many(self, sql, rows):
        self.conn.executemany(sql, rows)
        self.conn.commit()

    def setting(self, key, cast=float):
        v = self.scalar("SELECT value FROM settings WHERE key=?", (key,))
        if v is None:
            v = DEFAULT_SETTINGS.get(key, "0")
        return cast(v)

    def set_setting(self, key, value):
        self.run("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, str(value)))

    def nodes(self, kind=None):
        if kind:
            return self.q("SELECT * FROM nodes WHERE kind=? ORDER BY name", (kind,))
        return self.q("SELECT * FROM nodes ORDER BY kind, name")

    def node_map(self):
        return {r["id"]: r for r in self.q("SELECT * FROM nodes")}

    def roads(self):
        return self.q("SELECT * FROM roads")

    def cargo_map(self):
        return {r["code"]: r for r in self.q("SELECT * FROM cargo_types")}

    def active_events(self):
        return self.q(
            "SELECT e.*, r.name AS road_name, na.name AS a_name, nb.name AS b_name FROM road_events e "
            "JOIN roads r ON r.id=e.road_id JOIN nodes na ON na.id=r.a JOIN nodes nb ON nb.id=r.b "
            "WHERE e.active=1 ORDER BY e.created_at DESC"
        )

    def weather_map(self):
        return {r["region"]: r["condition"] for r in self.q("SELECT * FROM weather")}

    def reset(self):
        self.conn.close()
        os.remove(self.path)
        self.__init__(self.path)
