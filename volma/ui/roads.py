import random
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from ..geo import fmt_num
from .theme import BG, FONT_S, MUTED, PANEL, Card, congestion_color, fill_tree, form_row, make_tree

EVENT_KINDS = ["ремонт", "ДТП", "пробка", "погода", "перекрытие"]
WEATHER = ["ясно", "дождь", "туман", "снег", "гололёд"]
RANDOM_DESC = {
    "ремонт": ["Ремонт покрытия, сужение до одной полосы", "Замена дорожного полотна, реверс", "Ремонт моста, ограничение скорости 40 км/ч"],
    "ДТП": ["ДТП с участием грузового ТС", "Столкновение на перекрёстке, затруднено движение"],
    "пробка": ["Затор на въезде в город", "Плотное движение, скопление фур"],
    "погода": ["Сильный боковой ветер, ограничение для высоких ТС", "Метель, видимость менее 100 м"],
    "перекрытие": ["Временное ограничение движения грузовых ТС", "Перекрытие из-за паводка"],
}


class RoadsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(12, 0))
        ttk.Button(bar, text="Получить обновление обстановки", style="Accent.TButton", command=self.simulate).pack(side="left")
        tk.Label(bar, text="Имитация потока данных от дорожных служб, навигационных и погодных сервисов", bg=BG, fg=MUTED, font=FONT_S).pack(side="left", padx=10)

        top = tk.Frame(self, bg=BG)
        top.pack(fill="both", expand=True, padx=12, pady=12)
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)
        top.rowconfigure(0, weight=1)
        top.rowconfigure(1, weight=1)

        ev = Card(top, "Активные дорожные события")
        ev.grid(row=0, column=0, sticky="nsew")
        cols = [("kind", "Тип", 90, "w"), ("road", "Дорога", 250, "w"), ("sev", "Тяжесть", 70, "center"), ("desc", "Описание", 300, "w"), ("t", "С", 120, "center")]
        fr, self.events = make_tree(ev.body, cols, height=7, stretch={"road", "desc"})
        fr.pack(fill="both", expand=True)
        b = tk.Frame(ev.body, bg=PANEL)
        b.pack(fill="x", pady=(8, 0))
        ttk.Button(b, text="Добавить событие", command=self.add_event).pack(side="left")
        ttk.Button(b, text="Снять событие", command=self.close_event).pack(side="left", padx=6)

        wx = Card(top, "Погода по регионам")
        wx.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        cols = [("reg", "Регион", 220, "w"), ("cond", "Условия", 100, "center")]
        fr, self.weather = make_tree(wx.body, cols, height=7, stretch={"reg"})
        fr.pack(fill="both", expand=True)
        b2 = tk.Frame(wx.body, bg=PANEL)
        b2.pack(fill="x", pady=(8, 0))
        self.wx_var = tk.StringVar(value="ясно")
        ttk.Combobox(b2, textvariable=self.wx_var, values=WEATHER, state="readonly", width=10).pack(side="left")
        ttk.Button(b2, text="Установить для региона", command=self.set_weather).pack(side="left", padx=6)

        rd = Card(top, "Дорожная сеть")
        rd.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        cols = [("name", "Дорога", 200, "w"), ("leg", "Участок", 330, "w"), ("cat", "Категория", 110, "center"), ("km", "Км", 70, "e"), ("q", "Покрытие", 80, "center"),
                ("toll", "Платная, ₽/км", 100, "e"), ("border", "МАПП", 60, "center"), ("now", "Загруж. сейчас", 110, "center")]
        fr, self.roads = make_tree(rd.body, cols, height=8, stretch={"leg"})
        fr.pack(fill="both", expand=True)
        b3 = tk.Frame(rd.body, bg=PANEL)
        b3.pack(fill="x", pady=(8, 0))
        tk.Label(b3, text="Состояние покрытия, %:", bg=PANEL, fg=MUTED).pack(side="left")
        self.q_var = tk.IntVar(value=80)
        ttk.Spinbox(b3, from_=20, to=100, increment=5, textvariable=self.q_var, width=6).pack(side="left", padx=6)
        ttk.Button(b3, text="Обновить для выбранной дороги", command=self.set_quality).pack(side="left")
        self.refresh()

    def refresh(self):
        db = self.app.db
        rows = []
        tags = []
        for e in db.active_events():
            rows.append((e["id"], e["kind"], f"{e['road_name']}: {e['a_name']} — {e['b_name']}", f"{e['severity']:.1f}", e["description"], e["created_at"]))
            tags.append(("bad",) if e["kind"] == "перекрытие" else ("warn",))
        fill_tree(self.events, rows, tags)
        rows = []
        tags = []
        for reg, c in sorted(db.weather_map().items()):
            rows.append((reg, reg, c))
            tags.append(("bad",) if c == "гололёд" else (("warn",) if c in ("снег", "туман") else ()))
        fill_tree(self.weather, rows, tags)
        net = self.app.net
        now = datetime.now()
        rows = []
        tags = []
        for rid, r in sorted(net.road_rows.items(), key=lambda kv: kv[1]["name"]):
            c = net.congestion(rid, now)
            rows.append((rid, r["name"], f"{net.nodes[r['a']]['name']} — {net.nodes[r['b']]['name']}", r["category"], fmt_num(r["distance_km"]), f"{int(r['quality'] * 100)}%",
                         fmt_num(r["toll_rub_km"], 1) if r["toll_rub_km"] else "", "да" if r["border"] else "", "перекрыта" if net.is_closed(rid) else f"×{c:.2f}"))
            tags.append(("bad",) if net.is_closed(rid) or c >= 1.4 else (("warn",) if c >= 1.15 else ()))
        fill_tree(self.roads, rows, tags)

    def add_event(self):
        EventDialog(self, self.app)

    def close_event(self):
        sel = self.events.selection()
        if not sel:
            return
        self.app.db.run("UPDATE road_events SET active=0 WHERE id=?", (int(sel[0]),))
        self.app.net.refresh()
        self.app.refresh_all()

    def set_weather(self):
        sel = self.weather.selection()
        if not sel:
            messagebox.showinfo("Погода", "Выберите регион.")
            return
        self.app.db.run("UPDATE weather SET condition=? WHERE region=?", (self.wx_var.get(), sel[0]))
        self.app.net.refresh()
        self.app.refresh_all()

    def set_quality(self):
        sel = self.roads.selection()
        if not sel:
            messagebox.showinfo("Дороги", "Выберите дорогу.")
            return
        q = max(0.2, min(1.0, int(self.q_var.get()) / 100))
        self.app.db.run("UPDATE roads SET quality=? WHERE id=?", (q, int(sel[0])))
        self.app.net.refresh()
        self.app.refresh_all()

    def simulate(self):
        db = self.app.db
        rng = random.Random()
        changes = []
        for e in db.active_events():
            if rng.random() < 0.4:
                db.conn.execute("UPDATE road_events SET active=0 WHERE id=?", (e["id"],))
                changes.append(f"снято: {e['kind']} на {e['road_name']}")
        roads = db.roads()
        for _ in range(rng.randint(1, 3)):
            r = rng.choice(roads)
            kind = rng.choice(EVENT_KINDS[:4] * 3 + ["перекрытие"])
            sev = 1.0 if kind == "перекрытие" else round(rng.uniform(0.3, 0.9), 1)
            db.conn.execute("INSERT INTO road_events(road_id,kind,severity,description,active,created_at) VALUES (?,?,?,?,1,?)",
                            (r["id"], kind, sev, rng.choice(RANDOM_DESC[kind]), datetime.now().strftime("%Y-%m-%d %H:%M")))
            changes.append(f"новое: {kind} на {r['name']}")
        regions = list(db.weather_map())
        for reg in rng.sample(regions, k=min(4, len(regions))):
            c = rng.choice(WEATHER + ["ясно", "ясно"])
            db.conn.execute("UPDATE weather SET condition=? WHERE region=?", (c, reg))
            changes.append(f"погода {reg}: {c}")
        db.conn.commit()
        self.app.net.refresh()
        self.app.refresh_all()
        messagebox.showinfo("Обстановка обновлена", "\n".join(changes) + "\n\nИИ учитывает новые данные при расчёте маршрутов.")


class EventDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Дорожное событие")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        f = tk.Frame(self, bg=PANEL)
        f.pack(fill="both", expand=True, padx=18, pady=16)
        net = app.net
        self.roads = {f"{r['name']}: {net.nodes[r['a']]['name']} — {net.nodes[r['b']]['name']}": rid for rid, r in sorted(net.road_rows.items(), key=lambda kv: kv[1]["name"])}
        self.road = tk.StringVar(value=next(iter(self.roads)))
        self.kind = tk.StringVar(value="ремонт")
        self.sev = tk.DoubleVar(value=0.5)
        self.desc = tk.StringVar()
        form_row(f, 0, "Участок", ttk.Combobox(f, textvariable=self.road, values=list(self.roads), state="readonly", width=60, height=20))
        form_row(f, 1, "Тип", ttk.Combobox(f, textvariable=self.kind, values=EVENT_KINDS, state="readonly"))
        form_row(f, 2, "Тяжесть (0.1–1.0)", ttk.Spinbox(f, from_=0.1, to=1.0, increment=0.1, textvariable=self.sev))
        form_row(f, 3, "Описание", ttk.Entry(f, textvariable=self.desc))
        tk.Label(f, text="«Перекрытие» исключает участок из расчёта маршрутов", bg=PANEL, fg=MUTED, font=FONT_S).grid(row=4, column=0, columnspan=2, sticky="w")
        b = tk.Frame(f, bg=PANEL)
        b.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(b, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Добавить", style="Accent.TButton", command=self.save).pack(side="right", padx=6)
        self.grab_set()

    def save(self):
        try:
            sev = max(0.1, min(1.0, float(self.sev.get())))
        except (ValueError, tk.TclError):
            sev = 0.5
        if self.kind.get() == "перекрытие":
            sev = 1.0
        self.app.db.run("INSERT INTO road_events(road_id,kind,severity,description,active,created_at) VALUES (?,?,?,?,1,?)",
                        (self.roads[self.road.get()], self.kind.get(), sev, self.desc.get().strip() or self.kind.get(), datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.destroy()
        self.app.net.refresh()
        self.app.refresh_all()
