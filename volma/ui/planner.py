import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from ..ai.network import PRESETS, next_departure
from ..geo import fmt_hours, fmt_num, fmt_rub
from .map_view import MapCanvas
from .theme import ACCENT, BG, BLUE, BORDER, FONT_B, FONT_S, GOOD, MUTED, PANEL, TEXT, Card, fill_tree, form_row, make_tree

ROUTE_COLORS = [ACCENT, BLUE, "#7C3AED", "#64748B"]


class PlannerTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.results = []
        self.baseline = None

        left = tk.Frame(self, bg=BG, width=330)
        left.pack(side="left", fill="y", padx=(12, 6), pady=12)
        left.pack_propagate(False)
        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=12)

        card = Card(left, "Параметры перевозки")
        card.pack(fill="x")
        f = card.body
        self.node_names = {}
        self.src = tk.StringVar()
        self.dst = tk.StringVar()
        self.cargo = tk.StringVar()
        self.weight = tk.DoubleVar(value=20.0)
        self.vehicle = tk.StringVar(value="Типовое ТС")
        self.date = tk.StringVar()
        self.hour = tk.IntVar(value=8)
        self.preset = tk.StringVar(value="Баланс")
        self.cb_src = form_row(f, 0, "Откуда", ttk.Combobox(f, textvariable=self.src, state="readonly", height=20))
        self.cb_dst = form_row(f, 1, "Куда", ttk.Combobox(f, textvariable=self.dst, state="readonly", height=20))
        self.cb_cargo = form_row(f, 2, "Груз", ttk.Combobox(f, textvariable=self.cargo, state="readonly"))
        form_row(f, 3, "Масса, т", ttk.Spinbox(f, from_=1, to=40, increment=1, textvariable=self.weight))
        self.cb_veh = form_row(f, 4, "Транспорт", ttk.Combobox(f, textvariable=self.vehicle, state="readonly", height=20))
        form_row(f, 5, "Дата", ttk.Entry(f, textvariable=self.date))
        form_row(f, 6, "Час выезда", ttk.Spinbox(f, from_=0, to=23, textvariable=self.hour, wrap=True))
        form_row(f, 7, "Приоритет", ttk.Combobox(f, textvariable=self.preset, values=list(PRESETS), state="readonly"))
        self.cb_cargo.bind("<<ComboboxSelected>>", lambda e: self._fill_vehicles())
        ttk.Button(f, text="Рассчитать маршрут (ИИ)", style="Accent.TButton", command=self.calculate).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(f, text="Создать заказ по маршруту", command=self.make_order).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        info = Card(left, "Как считает ИИ")
        info.pack(fill="both", expand=True, pady=(10, 0))
        tk.Label(
            info.body,
            text=(
                "• Прогноз загруженности каждого участка по часу прохождения (модель обучена на истории трафика)\n"
                "• Погода, состояние покрытия, ремонты, ДТП и перекрытия\n"
                "• Топливо с учётом загрузки и пробок, платные дороги и «Платон», МАПП\n"
                "• Риск потерь по типу груза: гипс навалом, мешки, ГКЛ\n"
                "• Режим труда и отдыха водителя\n"
                "• Поиск k лучших маршрутов (алгоритм Йена)"
            ),
            bg=PANEL, fg=TEXT, font=FONT_S, justify="left", anchor="nw", wraplength=290,
        ).pack(fill="both", expand=True)

        self.banner = tk.Frame(right, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.banner.pack(fill="x")
        self.banner_lbl = tk.Label(self.banner, text="Выберите точки и нажмите «Рассчитать маршрут»", bg=PANEL, fg=MUTED, font=FONT_B, anchor="w", justify="left", padx=14, pady=10)
        self.banner_lbl.pack(fill="x")

        alt = Card(right, "Варианты маршрута")
        alt.pack(fill="x", pady=(10, 0))
        cols = [
            ("label", "Вариант", 210, "w"),
            ("path", "Маршрут", 300, "w"),
            ("km", "Км", 70, "e"),
            ("time", "В пути", 110, "e"),
            ("arr", "Прибытие", 110, "center"),
            ("fuel", "Топливо, л", 95, "e"),
            ("toll", "Платные", 85, "e"),
            ("loss", "Потери груза", 95, "e"),
            ("total", "Итого", 110, "e"),
        ]
        fr, self.tree = make_tree(alt.body, cols, height=5, stretch={"path"})
        fr.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_selected())

        bottom = ttk.PanedWindow(right, orient="horizontal")
        bottom.pack(fill="both", expand=True, pady=(10, 0))
        seg = Card(bottom, "Участки выбранного маршрута")
        cols2 = [
            ("road", "Дорога", 150, "w"),
            ("leg", "Участок", 230, "w"),
            ("km", "Км", 60, "e"),
            ("cong", "Загруж.", 65, "center"),
            ("wx", "Погода", 75, "center"),
            ("spd", "Ср. ск.", 60, "e"),
            ("h", "Время", 80, "e"),
            ("ev", "События", 200, "w"),
        ]
        fr2, self.seg_tree = make_tree(seg.body, cols2, height=8, stretch={"leg", "ev"})
        fr2.pack(fill="both", expand=True)
        bottom.add(seg, weight=3)
        mp = tk.Frame(bottom, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.map = MapCanvas(mp, app, legend=False)
        self.map.pack(fill="both", expand=True)
        bottom.add(mp, weight=2)
        self.reload()

    def reload(self):
        nodes = self.app.db.nodes()
        order = {"plant": 0, "deposit": 1, "hub": 2}
        nodes = sorted(nodes, key=lambda n: (order[n["kind"]], n["name"]))
        self.node_names = {n["name"]: n["id"] for n in nodes}
        names = list(self.node_names)
        self.cb_src["values"] = names
        self.cb_dst["values"] = names
        self.cargos = {r["name"]: r["code"] for r in self.app.db.q("SELECT * FROM cargo_types")}
        self.cb_cargo["values"] = list(self.cargos)
        if not self.src.get():
            self.src.set("ИндерГипс")
            self.dst.set("Саратов")
            self.cargo.set("Сухие смеси в мешках")
        if not self.date.get():
            self.date.set(next_departure(8).strftime("%d.%m.%Y"))
        self._fill_vehicles()

    def _fill_vehicles(self):
        code = self.cargos.get(self.cargo.get())
        if not code:
            return
        body = self.app.db.scalar("SELECT body FROM cargo_types WHERE code=?", (code,))
        rows = self.app.db.q("SELECT v.*, n.name AS loc FROM vehicles v JOIN nodes n ON n.id=v.location_node WHERE v.body=? ORDER BY v.status, n.name", (body,))
        self.veh_map = {"Типовое ТС": None}
        for r in rows:
            self.veh_map[f"{r['plate']} · {r['model']} · {r['capacity_t']:.0f} т · {r['loc']} ({r['status']})"] = r
        self.cb_veh["values"] = list(self.veh_map)
        if self.vehicle.get() not in self.veh_map:
            self.vehicle.set("Типовое ТС")

    def _departure(self):
        d = datetime.strptime(self.date.get().strip(), "%d.%m.%Y")
        return d.replace(hour=int(self.hour.get()))

    def calculate(self):
        try:
            src = self.node_names[self.src.get()]
            dst = self.node_names[self.dst.get()]
            code = self.cargos[self.cargo.get()]
            weight = float(self.weight.get())
            dep = self._departure()
        except (KeyError, ValueError, tk.TclError):
            messagebox.showwarning("Маршрут", "Проверьте параметры: точки, груз, массу и дату (ДД.ММ.ГГГГ).")
            return
        if src == dst:
            messagebox.showwarning("Маршрут", "Точки отправления и назначения совпадают.")
            return
        net = self.app.net
        net.refresh()
        veh = self.veh_map.get(self.vehicle.get())
        body = self.app.db.scalar("SELECT body FROM cargo_types WHERE code=?", (code,))
        prof = net.profile_for(veh, body)
        if weight > prof["capacity_t"]:
            messagebox.showinfo("Маршрут", f"Масса {weight:.0f} т превышает грузоподъёмность ТС ({prof['capacity_t']:.0f} т). Расчёт выполнен для одного рейса с полной загрузкой.")
            weight = prof["capacity_t"]
        weights = PRESETS[self.preset.get()]
        self.results = net.k_routes(src, dst, dep, prof, code, weight, k=3, weights=weights)
        self.baseline = net.baseline_route(src, dst, dep, prof, code, weight)
        self.extra = None
        if veh is not None and veh["location_node"] != src:
            self.extra = net.best_route(veh["location_node"], src, dep - timedelta(hours=1), prof, None, 0)
        if not self.results:
            self.banner_lbl.configure(text="Маршрут не найден: все варианты перекрыты", fg="#B91C1C")
            fill_tree(self.tree, [])
            return
        rows = []
        tags = []
        for i, r in enumerate(self.results + ([self.baseline] if self.baseline else [])):
            is_base = r is self.baseline
            rows.append((
                "base" if is_base else i,
                r.label + (" ⚠ перекрыт" if r.closed else ""),
                net.route_name(r.nodes),
                fmt_num(r.km),
                fmt_hours(r.total_h),
                r.arrival.strftime("%d.%m %H:%M"),
                fmt_num(r.fuel_l),
                fmt_rub(r.toll_rub),
                fmt_rub(r.loss_rub),
                fmt_rub(r.total_rub),
            ))
            tags.append(("muted",) if is_base else (("bold", "good") if i == 0 else ()))
        fill_tree(self.tree, rows, tags)
        best = self.results[0]
        if self.baseline:
            b = self.baseline
            d_cost = b.total_rub - best.total_rub
            d_time = b.total_h - best.total_h
            d_loss = b.loss_rub - best.loss_rub
            pct = d_cost / b.total_rub * 100 if b.total_rub else 0
            txt = f"ИИ-маршрут: {fmt_rub(best.total_rub)} · {fmt_hours(best.total_h)} · {fmt_num(best.km)} км"
            if b.closed:
                txt += f"\nТрадиционный кратчайший маршрут перекрыт — ИИ построил объезд. Экономия {fmt_rub(d_cost)} и {fmt_hours(max(0, d_time))} простоя."
            elif abs(d_cost) < 1:
                txt += "\nКратчайший маршрут совпадает с оптимальным при текущей обстановке."
            else:
                txt += f"\nЭкономия против кратчайшего маршрута: {fmt_rub(d_cost)} ({pct:.1f}%), время {'−' if d_time >= 0 else '+'}{fmt_hours(abs(d_time))}, потери груза {'−' if d_loss >= 0 else '+'}{fmt_rub(abs(d_loss))}"
            if self.extra is not None:
                txt += f"\nПодача ТС к месту погрузки: {fmt_num(self.extra.km)} км порожнём, {fmt_hours(self.extra.total_h)}, {fmt_rub(self.extra.total_rub)}"
            self.banner_lbl.configure(text=txt, fg=GOOD if d_cost >= 0 else TEXT)
        self.tree.selection_set("0")
        self.show_selected()

    def show_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.baseline if sel[0] == "base" else self.results[int(sel[0])]
        net = self.app.net
        rows = []
        tags = []
        for i, s in enumerate(r.segments):
            ev = s["event"]
            if s["border_h"] and not s["closed"]:
                ev = (ev + "; " if ev else "") + f"МАПП +{s['border_h']:.0f} ч"
            rows.append((i, s["road"], f"{net.nodes[s['from']]['name']} → {net.nodes[s['to']]['name']}", fmt_num(s["km"]), f"×{s['congestion']:.2f}", s["weather"], f"{s['speed']:.0f}", fmt_hours(s["drive_h"] + s["border_h"]), ev))
            tags.append(("bad",) if s["closed"] else (("warn",) if s["event"] or s["congestion"] > 1.4 else ()))
        if r.rest_h:
            rows.append(("rest", "Отдых водителя", "по режиму труда и отдыха", "", "", "", "", fmt_hours(r.rest_h), ""))
            tags.append(("muted",))
        fill_tree(self.seg_tree, rows, tags)
        items = []
        if self.baseline and sel[0] != "base":
            items.append({"nodes": self.baseline.nodes, "roads": self.baseline.roads, "color": "#94A3B8", "width": 4, "dash": (6, 4)})
        idx = -1 if sel[0] == "base" else int(sel[0])
        items.append({"nodes": r.nodes, "roads": r.roads, "color": "#64748B" if idx < 0 else ROUTE_COLORS[idx % len(ROUTE_COLORS)], "width": 6})
        self.map.highlight = items
        lats = [net.nodes[n]["lat"] for n in r.nodes]
        lons = [net.nodes[n]["lon"] for n in r.nodes]
        pl = max(1.0, (max(lats) - min(lats)) * 0.2)
        po = max(1.5, (max(lons) - min(lons)) * 0.2)
        self.map._fitted = True
        self.map.fit(min(lons) - po, max(lons) + po, min(lats) - pl, max(lats) + pl)

    def make_order(self):
        try:
            src = self.node_names[self.src.get()]
            dst = self.node_names[self.dst.get()]
            code = self.cargos[self.cargo.get()]
            weight = float(self.weight.get())
            dep = self._departure()
        except (KeyError, ValueError, tk.TclError):
            messagebox.showwarning("Заказ", "Заполните параметры перевозки.")
            return
        if src == dst:
            return
        due = (dep + timedelta(days=3)).strftime("%Y-%m-%d")
        oid = self.app.db.run(
            "INSERT INTO orders(created_at,origin,destination,cargo,weight_t,due_date,priority,status) VALUES (?,?,?,?,?,?,?, 'новый')",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), src, dst, code, weight, due, 2),
        )
        self.app.refresh_all()
        messagebox.showinfo("Заказ", f"Заказ №{oid} создан. Его можно включить в план на вкладке «Заказы».")
