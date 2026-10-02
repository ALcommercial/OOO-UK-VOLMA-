import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from ..geo import fmt_num, fmt_rub
from .charts import Chart
from .theme import ACCENT, BG, BLUE, FONT_S, GOOD, MUTED, PANEL, TEXT, Card, Kpi

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


class AnalyticsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        kp = tk.Frame(self, bg=BG)
        kp.pack(fill="x", padx=12, pady=(12, 0))
        self.k_r2 = Kpi(kp, "R² на отложенной выборке", color="#7C3AED")
        self.k_mae = Kpi(kp, "Средняя ошибка (MAE)", color="#7C3AED")
        self.k_n = Kpi(kp, "Обучающих наблюдений", color=BLUE)
        self.k_fuel = Kpi(kp, "Сэкономлено топлива", color=GOOD)
        self.k_loss = Kpi(kp, "Ожидаемые потери груза", color=ACCENT)
        for i, k in enumerate((self.k_r2, self.k_mae, self.k_n, self.k_fuel, self.k_loss)):
            k.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            kp.columnconfigure(i, weight=1)
        bar = tk.Frame(kp, bg=BG)
        bar.grid(row=0, column=5, sticky="nse", padx=(8, 0))
        ttk.Button(bar, text="Переобучить модель", style="Accent.TButton", command=self.retrain).pack(fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        c1 = Card(body, "Суточный профиль загруженности участка (прогноз ИИ)")
        c1.grid(row=0, column=0, sticky="nsew")
        row = tk.Frame(c1.body, bg=PANEL)
        row.pack(fill="x")
        self.road = tk.StringVar()
        self.cb_road = ttk.Combobox(row, textvariable=self.road, state="readonly", width=60, height=20)
        self.cb_road.pack(side="left", fill="x", expand=True)
        self.cb_road.bind("<<ComboboxSelected>>", lambda e: self.draw_profile())
        self.day = tk.StringVar(value=DAYS[datetime.now().weekday()])
        cbd = ttk.Combobox(row, textvariable=self.day, values=DAYS, state="readonly", width=5)
        cbd.pack(side="left", padx=(6, 0))
        cbd.bind("<<ComboboxSelected>>", lambda e: self.draw_profile())
        self.profile = Chart(c1.body, height=200)
        self.profile.pack(fill="both", expand=True, pady=(8, 0))

        c2 = Card(body, "Вклад факторов в загруженность (коэффициенты модели)")
        c2.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.imp = Chart(c2.body, height=200)
        self.imp.pack(fill="both", expand=True)

        c3 = Card(body, "Холостой пробег по рейсам, км")
        c3.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.empty = Chart(c3.body, height=200)
        self.empty.pack(fill="both", expand=True)

        c4 = Card(body, "Структура затрат по утверждённым рейсам")
        c4.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(10, 0))
        self.struct = Chart(c4.body, height=200)
        self.struct.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        m = self.app.model.metrics
        self.k_r2.set(f"{m.get('r2', 0):.3f}", "доля объяснённой дисперсии")
        self.k_mae.set(f"{m.get('mae', 0):.3f}", f"MAPE {m.get('mape', 0) * 100:.1f}% по коэффициенту загруженности")
        self.k_n.set(fmt_num(m.get("n_train", 0) + m.get("n_test", 0)), f"обучение {fmt_num(m.get('n_train', 0))} · тест {fmt_num(m.get('n_test', 0))}")
        db = self.app.db
        trips = db.q("SELECT * FROM trips WHERE status!='отменён' ORDER BY id")
        price = db.setting("fuel_price")
        if trips:
            saved = sum(t["baseline_fuel_l"] - t["fuel_l"] for t in trips)
            self.k_fuel.set(f"{fmt_num(max(0, saved))} л", f"≈ {fmt_rub(max(0, saved) * price)}")
            self.k_loss.set(fmt_rub(sum(t["loss_rub"] for t in trips)), "с учётом типа груза и дорог")
        else:
            self.k_fuel.set("—", "нет рейсов")
            self.k_loss.set("—", "нет рейсов")
        net = self.app.net
        self.roads = {}
        for rid, r in sorted(net.road_rows.items(), key=lambda kv: -kv[1]["urban"]):
            self.roads[f"{r['name']}: {net.nodes[r['a']]['name']} — {net.nodes[r['b']]['name']}"] = rid
        self.cb_road["values"] = list(self.roads)
        if self.road.get() not in self.roads:
            self.road.set(next(iter(self.roads)))
        self.draw_profile()
        imp = sorted(self.app.model.importance(), key=lambda t: -abs(t[1]))
        self.imp.bars([n for n, _ in imp], [[v for _, v in imp]], [ACCENT, GOOD], fmt=lambda v: f"{v:+.2f}", horizontal=True)
        self.empty.bars([f"№{t['id']}" for t in trips[-24:]], [[t["baseline_empty_km"] for t in trips[-24:]], [t["empty_km"] for t in trips[-24:]]], ["#CBD5E1", BLUE], ["Традиционная схема", "План ИИ"])
        if trips:
            cost = sum(t["cost_rub"] for t in trips)
            fuel = sum(t["fuel_l"] for t in trips) * price
            loss = sum(t["loss_rub"] for t in trips)
            other = max(0.0, cost - fuel - loss)
            self.struct.bars(["Топливо", "Время, дороги", "Потери груза"], [[fuel / 1000, other / 1000, loss / 1000]], [BLUE], fmt=lambda v: f"{v:,.0f} тыс. ₽".replace(",", " "), horizontal=True)
        else:
            self.struct.bars([], [[]], [BLUE])

    def draw_profile(self):
        rid = self.roads.get(self.road.get())
        if rid is None:
            return
        net = self.app.net
        wd = DAYS.index(self.day.get())
        base = datetime.now()
        base = base - timedelta(days=base.weekday() - wd)
        road = net.road_rows[rid]
        ys_now = []
        ys_clear = []
        for h in range(24):
            when = base.replace(hour=h, minute=0, second=0, microsecond=0)
            ys_now.append(net.congestion(rid, when))
            ys_clear.append(self.app.model.predict(road, wd, h, "ясно", 0))
        hist = self.app.db.q("SELECT hour, AVG(congestion) c FROM traffic_history WHERE road_id=? GROUP BY hour ORDER BY hour", (rid,))
        ys_hist = [0.0] * 24
        for r in hist:
            ys_hist[r["hour"]] = r["c"]
        self.profile.line(list(range(24)), [ys_hist, ys_clear, ys_now], ["#CBD5E1", BLUE, ACCENT], ["История (среднее)", "Прогноз, ясно", "Прогноз, текущая погода"], xfmt=lambda x: f"{x}:00")

    def retrain(self):
        m = self.app.model.train()
        self.app.net.refresh()
        self.app.refresh_all()
        messagebox.showinfo("Модель", f"Модель переобучена на {fmt_num(m['n_train'])} наблюдениях.\nR² = {m['r2']:.3f}, MAE = {m['mae']:.3f}")
