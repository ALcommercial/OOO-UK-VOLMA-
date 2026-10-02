import tkinter as tk
from datetime import datetime
from tkinter import ttk

from ..geo import fmt_num, fmt_rub
from .charts import Chart
from .map_view import MapCanvas
from .theme import ACCENT, BAD, BG, BLUE, BORDER, FONT_B, FONT_S, GOOD, MUTED, PANEL, TEXT, WARN, Card, Kpi, fill_tree, make_tree


class DashboardTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        kp = tk.Frame(self, bg=BG)
        kp.pack(fill="x", padx=12, pady=(12, 0))
        self.k_sites = Kpi(kp, "Площадки холдинга", color=ACCENT)
        self.k_fleet = Kpi(kp, "Автопарк", color=BLUE)
        self.k_orders = Kpi(kp, "Заказы к планированию", color=WARN)
        self.k_save = Kpi(kp, "Экономия ИИ по рейсам", color=GOOD)
        self.k_empty = Kpi(kp, "Сокращение холостого пробега", color=GOOD)
        self.k_model = Kpi(kp, "Точность прогноза трафика", color="#7C3AED")
        for i, k in enumerate((self.k_sites, self.k_fleet, self.k_orders, self.k_save, self.k_empty, self.k_model)):
            k.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            kp.columnconfigure(i, weight=1)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)

        mapcard = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        mapcard.grid(row=0, column=0, sticky="nsew")
        hdr = tk.Frame(mapcard, bg=PANEL)
        hdr.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(hdr, text="Логистическая сеть: заводы, месторождения, дороги", bg=PANEL, fg=TEXT, font=("Segoe UI Semibold", 12)).pack(side="left")
        ttk.Button(hdr, text="Открыть карту", command=lambda: app.select_tab("map")).pack(side="right")
        self.map = MapCanvas(mapcard, app)
        self.map.pack(fill="both", expand=True, padx=1, pady=(6, 1))

        alerts = Card(body, "Дорожная обстановка и риски")
        alerts.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        cols = [("type", "Тип", 90, "w"), ("where", "Где", 220, "w"), ("what", "Что", 260, "w")]
        fr, self.alerts = make_tree(alerts.body, cols, height=10, stretch={"where", "what"})
        fr.pack(fill="both", expand=True)

        ch = Card(body, "Стоимость рейсов: ИИ против традиционной схемы, тыс. ₽")
        ch.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.chart = Chart(ch.body, height=180)
        self.chart.pack(fill="both", expand=True)

        sites = Card(body, "Загрузка площадок")
        sites.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(10, 0))
        cols = [("name", "Площадка", 190, "w"), ("veh", "ТС", 50, "center"), ("out", "Отгрузка, т", 95, "e"), ("in", "Сырьё, т", 85, "e")]
        fr2, self.sites = make_tree(sites.body, cols, height=6, stretch={"name"})
        fr2.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        db = self.app.db
        np_ = db.scalar("SELECT COUNT(*) FROM nodes WHERE kind='plant'")
        nd = db.scalar("SELECT COUNT(*) FROM nodes WHERE kind='deposit'")
        nh = db.scalar("SELECT COUNT(*) FROM nodes WHERE kind='hub'")
        self.k_sites.set(f"{np_} + {nd}", f"заводов + месторождений · {nh} РЦ/клиентов")
        tot = db.scalar("SELECT COUNT(*) FROM vehicles")
        free = db.scalar("SELECT COUNT(*) FROM vehicles WHERE status='свободна'")
        self.k_fleet.set(f"{tot} ТС", f"свободно {free} · в работе {tot - free}")
        no = db.scalar("SELECT COUNT(*) FROM orders WHERE status='новый'")
        wt = db.scalar("SELECT COALESCE(SUM(weight_t),0) FROM orders WHERE status='новый'")
        self.k_orders.set(str(no), f"{fmt_num(wt)} т груза")
        r = db.one("SELECT COALESCE(SUM(cost_rub),0) c, COALESCE(SUM(baseline_cost_rub),0) b, COALESCE(SUM(empty_km),0) e, COALESCE(SUM(baseline_empty_km),0) be, COUNT(*) n FROM trips WHERE status!='отменён'")
        if r["n"]:
            s = r["b"] - r["c"]
            self.k_save.set(fmt_rub(s), f"−{s / r['b'] * 100:.1f}% по {r['n']} рейсам" if r["b"] else "")
            de = r["be"] - r["e"]
            self.k_empty.set(f"{fmt_num(de)} км", f"−{de / r['be'] * 100:.1f}% порожних км" if r["be"] else "")
        else:
            self.k_save.set("—", "запустите оптимизацию на вкладке «Заказы»")
            self.k_empty.set("—", "нет утверждённых рейсов")
        m = self.app.model.metrics
        self.k_model.set(f"R² {m.get('r2', 0):.2f}", f"MAPE {m.get('mape', 0) * 100:.1f}% · {fmt_num(m.get('n_train', 0) + m.get('n_test', 0))} наблюдений")

        rows = []
        tags = []
        for e in db.active_events():
            rows.append((f"e{e['id']}", e["kind"], f"{e['road_name']}: {e['a_name']} — {e['b_name']}", e["description"]))
            tags.append(("bad",) if e["kind"] == "перекрытие" else ("warn",))
        for reg, cond in sorted(db.weather_map().items()):
            if cond in ("снег", "гололёд", "туман"):
                rows.append((f"w{reg}", "погода", reg, f"{cond}: снижение скорости, риск для груза"))
                tags.append(("warn",) if cond != "гололёд" else ("bad",))
        net = self.app.net
        now = datetime.now()
        for rid, road in net.road_rows.items():
            c = net.congestion(rid, now)
            if c >= 1.4 and rid not in net.events:
                rows.append((f"c{rid}", "загруженность", f"{road['name']}: {net.nodes[road['a']]['name']} — {net.nodes[road['b']]['name']}", f"ИИ-прогноз ×{c:.2f} сейчас"))
                tags.append(("warn",))
        fill_tree(self.alerts, rows, tags)

        trips = db.q("SELECT id, cost_rub, baseline_cost_rub FROM trips WHERE status!='отменён' ORDER BY id DESC LIMIT 24")[::-1]
        self.chart.bars([f"№{t['id']}" for t in trips], [[t["baseline_cost_rub"] / 1000 for t in trips], [t["cost_rub"] / 1000 for t in trips]],
                        ["#CBD5E1", ACCENT], ["Традиционная схема", "План ИИ"])

        rows = []
        for n in db.q("SELECT * FROM nodes WHERE kind='plant' ORDER BY name"):
            veh = db.scalar("SELECT COUNT(*) FROM vehicles WHERE location_node=?", (n["id"],))
            out = db.scalar("SELECT COALESCE(SUM(weight_t),0) FROM orders WHERE origin=? AND status IN ('новый','запланирован','в пути')", (n["id"],))
            inn = db.scalar("SELECT COALESCE(SUM(weight_t),0) FROM orders WHERE destination=? AND cargo='GYPSUM_STONE' AND status IN ('новый','запланирован','в пути')", (n["id"],))
            rows.append((n["id"], n["name"], veh, fmt_num(out), fmt_num(inn)))
        fill_tree(self.sites, rows)
        self.map.redraw()
