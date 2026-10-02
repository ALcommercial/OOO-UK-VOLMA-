import tkinter as tk
from datetime import datetime
from tkinter import ttk

from ..ai.network import Network
from ..ai.traffic_model import TrafficModel
from ..db import Database
from .analytics import AnalyticsTab
from .dashboard import DashboardTab
from .fleet import FleetTab
from .map_view import MapTab
from .orders import OrdersTab
from .planner import PlannerTab
from .roads import RoadsTab
from .settings import SettingsTab
from .theme import ACCENT, BG, HEADER, MUTED, setup_style
from .trips import TripsTab

TABS = [
    ("dash", "Обзор", DashboardTab),
    ("map", "Карта сети", MapTab),
    ("plan", "Маршрут", PlannerTab),
    ("orders", "Заказы", OrdersTab),
    ("trips", "Рейсы", TripsTab),
    ("fleet", "Автопарк", FleetTab),
    ("roads", "Дорожная обстановка", RoadsTab),
    ("ai", "Аналитика ИИ", AnalyticsTab),
    ("settings", "Справочники", SettingsTab),
]


class App(tk.Tk):
    def __init__(self, db_path=None):
        super().__init__()
        self.title("ВОЛМА · Умная логистика")
        self.geometry("1500x900")
        self.minsize(1200, 760)
        setup_style(self)
        self.db = Database(db_path)
        self.model = TrafficModel(self.db)
        self.net = Network(self.db, self.model)
        self._header()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tabs = {}
        for key, title, cls in TABS:
            frame = cls(self.nb, self)
            self.nb.add(frame, text=title)
            self.tabs[key] = frame
        self.status = tk.Label(self, text="Готово", bg="#E4E8EF", fg=MUTED, anchor="w", padx=12, pady=4, font=("Segoe UI", 9))
        self.status.pack(fill="x", side="bottom")
        self.nb.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._tick()

    def _header(self):
        h = tk.Frame(self, bg=HEADER, height=58)
        h.pack(fill="x")
        h.pack_propagate(False)
        logo = tk.Frame(h, bg=ACCENT)
        logo.pack(side="left", padx=(16, 12), pady=12)
        tk.Label(logo, text="ВОЛМА", bg=ACCENT, fg="white", font=("Segoe UI Black", 13), padx=10).pack()
        tk.Label(h, text="Умная логистика", bg=HEADER, fg="white", font=("Segoe UI Semibold", 15)).pack(side="left")
        tk.Label(h, text="  ·  цифровая система управления цепочками поставок с ИИ", bg=HEADER, fg="#9FB0CC", font=("Segoe UI", 10)).pack(side="left")
        self.clock = tk.Label(h, text="", bg=HEADER, fg="#9FB0CC", font=("Segoe UI", 10))
        self.clock.pack(side="right", padx=16)
        self.ai_lbl = tk.Label(h, text="", bg=HEADER, fg="#7EE2A8", font=("Segoe UI Semibold", 10))
        self.ai_lbl.pack(side="right", padx=8)

    def _tick(self):
        self.clock.configure(text=datetime.now().strftime("%d.%m.%Y  %H:%M"))
        m = self.model.metrics
        self.ai_lbl.configure(text=f"● ИИ-модуль активен · R² {m.get('r2', 0):.2f}")
        self.after(30000, self._tick)

    def _tab_changed(self, e=None):
        key = self.current_tab()
        tab = self.tabs.get(key)
        if key in ("map", "dash") and tab is not None:
            tab.refresh()

    def current_tab(self):
        idx = self.nb.index(self.nb.select())
        return TABS[idx][0]

    def select_tab(self, key):
        keys = [k for k, _, _ in TABS]
        self.nb.select(keys.index(key))

    def set_status(self, text):
        self.status.configure(text=text)

    def refresh_all(self):
        self.net.refresh()
        for key, tab in self.tabs.items():
            if hasattr(tab, "refresh"):
                tab.refresh()
            elif hasattr(tab, "reload"):
                tab.reload()
        self._tick()
