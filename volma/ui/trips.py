import json
import random
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from ..geo import fmt_hours, fmt_num, fmt_rub
from ..seed import true_congestion
from .map_view import MapCanvas
from .theme import ACCENT, BG, BORDER, FONT_S, MUTED, PANEL, Card, fill_tree, make_tree

KIND = {"empty": "подача порожняком", "loaded": "с грузом", "return": "возврат на базу"}


class TripsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(12, 0))
        ttk.Button(bar, text="Отправить в рейс", command=self.start).pack(side="left")
        ttk.Button(bar, text="Завершить рейс", command=self.finish).pack(side="left", padx=6)
        ttk.Button(bar, text="Отменить рейс", command=self.cancel).pack(side="left")
        self.summary = tk.Label(bar, text="", bg=BG, fg=MUTED, font=FONT_S)
        self.summary.pack(side="right")

        pw = ttk.PanedWindow(self, orient="vertical")
        pw.pack(fill="both", expand=True, padx=12, pady=12)
        top = Card(pw, "Рейсы")
        cols = [
            ("id", "№", 50, "center"),
            ("created", "Создан", 120, "center"),
            ("veh", "ТС", 170, "w"),
            ("status", "Статус", 110, "center"),
            ("t", "Груз, т", 70, "e"),
            ("km", "Пробег, км", 90, "e"),
            ("ekm", "Порожн., км", 90, "e"),
            ("h", "Длительность", 110, "e"),
            ("cost", "Стоимость", 110, "e"),
            ("base", "Традиц. схема", 110, "e"),
            ("save", "Экономия", 100, "e"),
            ("loss", "Риск потерь", 100, "e"),
        ]
        fr, self.tree = make_tree(top.body, cols, height=9, stretch={"veh"})
        fr.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show())
        pw.add(top, weight=1)

        bottom = ttk.PanedWindow(pw, orient="horizontal")
        legs = Card(bottom, "Плечи рейса")
        cols2 = [
            ("n", "#", 30, "center"),
            ("kind", "Тип", 140, "w"),
            ("path", "Маршрут", 380, "w"),
            ("t", "Груз, т", 65, "e"),
            ("km", "Км", 65, "e"),
            ("h", "Время", 100, "e"),
            ("cost", "Стоимость", 100, "e"),
            ("orders", "Заказы", 80, "center"),
        ]
        fr2, self.legs = make_tree(legs.body, cols2, height=8, stretch={"path"})
        fr2.pack(fill="both", expand=True)
        bottom.add(legs, weight=3)
        mp = tk.Frame(bottom, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.map = MapCanvas(mp, app, legend=False)
        self.map.pack(fill="both", expand=True)
        bottom.add(mp, weight=2)
        pw.add(bottom, weight=1)
        self.refresh()

    def refresh(self):
        rows = []
        tags = []
        for t in self.app.db.q("SELECT t.*, v.plate, v.body FROM trips t JOIN vehicles v ON v.id=t.vehicle_id ORDER BY CASE t.status WHEN 'в пути' THEN 0 WHEN 'запланирован' THEN 1 ELSE 2 END, t.id DESC"):
            save = t["baseline_cost_rub"] - t["cost_rub"]
            rows.append((t["id"], t["id"], datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M"), f"{t['plate']} ({t['body']})", t["status"], fmt_num(t["load_t"], 1), fmt_num(t["distance_km"]), fmt_num(t["empty_km"]),
                         fmt_hours(t["duration_h"]), fmt_rub(t["cost_rub"]), fmt_rub(t["baseline_cost_rub"]), fmt_rub(save), fmt_rub(t["loss_rub"])))
            tags.append(("muted",) if t["status"] in ("выполнен", "отменён") else (("bold",) if t["status"] == "в пути" else ()))
        fill_tree(self.tree, rows, tags)
        r = self.app.db.one("SELECT COUNT(*) n, COALESCE(SUM(baseline_cost_rub - cost_rub),0) s FROM trips WHERE status!='отменён'")
        self.summary.configure(text=f"Всего рейсов: {r['n']} · суммарная экономия ИИ: {fmt_rub(r['s'])}")
        fill_tree(self.legs, [])
        self.map.highlight = []
        self.map.redraw()

    def selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Рейсы", "Выберите рейс в таблице.")
            return None
        return self.app.db.one("SELECT * FROM trips WHERE id=?", (int(sel[0]),))

    def show(self):
        sel = self.tree.selection()
        if not sel:
            return
        t = self.app.db.one("SELECT * FROM trips WHERE id=?", (int(sel[0]),))
        net = self.app.net
        legs = json.loads(t["legs"] or "[]")
        rows = []
        items = []
        tags = []
        for i, lg in enumerate(legs):
            rows.append((i, i + 1, KIND.get(lg["kind"], lg["kind"]), " → ".join(net.nodes[n]["name"].replace(" (РЦ)", "") for n in lg["nodes"]),
                         fmt_num(lg["load_t"], 1) if lg["load_t"] else "—", fmt_num(lg["km"]), fmt_hours(lg["hours"]), fmt_rub(lg["cost"]), ", ".join(map(str, lg["orders"]))))
            tags.append(() if lg["kind"] == "loaded" else ("muted",))
            if lg["kind"] == "loaded":
                items.append({"nodes": lg["nodes"], "roads": lg["roads"], "color": ACCENT, "width": 6})
            else:
                items.append({"nodes": lg["nodes"], "roads": lg["roads"], "color": "#64748B", "width": 4, "dash": (6, 4)})
        fill_tree(self.legs, rows, tags)
        self.map.highlight = items
        lats = [net.nodes[n]["lat"] for it in items for n in it["nodes"]]
        lons = [net.nodes[n]["lon"] for it in items for n in it["nodes"]]
        if lats:
            pl = max(1.0, (max(lats) - min(lats)) * 0.2)
            po = max(1.5, (max(lons) - min(lons)) * 0.2)
            self.map._fitted = True
            self.map.fit(min(lons) - po, max(lons) + po, min(lats) - pl, max(lats) + pl)

    def start(self):
        t = self.selected()
        if not t:
            return
        if t["status"] != "запланирован":
            messagebox.showinfo("Рейсы", "Отправить можно только запланированный рейс.")
            return
        db = self.app.db
        db.conn.execute("UPDATE trips SET status='в пути' WHERE id=?", (t["id"],))
        db.conn.execute("UPDATE orders SET status='в пути' WHERE trip_id=?", (t["id"],))
        db.conn.execute("UPDATE vehicles SET status='в рейсе' WHERE id=?", (t["vehicle_id"],))
        db.conn.commit()
        self.app.refresh_all()

    def finish(self):
        t = self.selected()
        if not t:
            return
        if t["status"] not in ("в пути", "запланирован"):
            messagebox.showinfo("Рейсы", "Рейс уже закрыт.")
            return
        db = self.app.db
        nodes = json.loads(t["route_nodes"])
        roads = json.loads(t["route_roads"])
        rng = random.Random()
        when = datetime.now()
        hist = []
        for rid in roads:
            road = self.app.net.road_rows.get(rid)
            if not road:
                continue
            wx = self.app.net.edge_weather(road)
            ev = 1 if rid in self.app.net.events else 0
            for _ in range(3):
                hr = (when.hour + rng.randint(0, 23)) % 24
                hist.append((rid, when.weekday(), hr, wx, ev, round(true_congestion(rng, road, when.weekday(), hr, wx, ev), 3)))
        db.conn.executemany("INSERT INTO traffic_history(road_id,weekday,hour,weather,event,congestion) VALUES (?,?,?,?,?,?)", hist)
        db.conn.execute("UPDATE trips SET status='выполнен' WHERE id=?", (t["id"],))
        db.conn.execute("UPDATE orders SET status='доставлен' WHERE trip_id=?", (t["id"],))
        db.conn.execute("UPDATE vehicles SET status='свободна', location_node=?, odometer_km=odometer_km+? WHERE id=?", (nodes[-1], t["distance_km"], t["vehicle_id"]))
        db.conn.commit()
        self.app.model.train()
        self.app.net.refresh()
        self.app.refresh_all()
        self.app.set_status(f"Рейс №{t['id']} завершён. Телеметрия ({len(hist)} наблюдений) добавлена, модель трафика дообучена.")

    def cancel(self):
        t = self.selected()
        if not t:
            return
        if t["status"] in ("выполнен", "отменён"):
            return
        if not messagebox.askyesno("Рейсы", f"Отменить рейс №{t['id']}? Заказы вернутся в планирование."):
            return
        db = self.app.db
        db.conn.execute("UPDATE trips SET status='отменён' WHERE id=?", (t["id"],))
        db.conn.execute("UPDATE orders SET status='новый', trip_id=NULL WHERE trip_id=?", (t["id"],))
        db.conn.execute("UPDATE vehicles SET status='свободна' WHERE id=?", (t["vehicle_id"],))
        db.conn.commit()
        self.app.refresh_all()
