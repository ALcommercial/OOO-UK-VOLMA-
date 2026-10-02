import math
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from ..ai.dispatcher import Dispatcher
from ..geo import fmt_hours, fmt_num, fmt_rub
from .map_view import MapCanvas
from .theme import ACCENT, BAD, BG, BORDER, FONT_B, FONT_H2, FONT_S, GOOD, MUTED, PANEL, TEXT, Card, Kpi, fill_tree, form_row, make_tree

STATUSES = ["все", "новый", "запланирован", "в пути", "доставлен", "отменён"]
PRIORITY = {1: "высокий", 2: "обычный", 3: "низкий"}


class OrdersTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(bar, text="Статус:", bg=BG, fg=MUTED).pack(side="left")
        self.status = tk.StringVar(value="все")
        cb = ttk.Combobox(bar, textvariable=self.status, values=STATUSES, state="readonly", width=16)
        cb.pack(side="left", padx=(6, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(bar, text="Новый заказ", command=self.new_order).pack(side="left")
        ttk.Button(bar, text="Отменить заказ", command=self.cancel_order).pack(side="left", padx=6)
        ttk.Button(bar, text="Оптимизировать план перевозок (ИИ)", style="Accent.TButton", command=self.optimize).pack(side="right")
        self.summary = tk.Label(bar, text="", bg=BG, fg=MUTED, font=FONT_S)
        self.summary.pack(side="right", padx=12)

        card = Card(self)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        cols = [
            ("id", "№", 50, "center"),
            ("created", "Создан", 120, "center"),
            ("origin", "Откуда", 200, "w"),
            ("dest", "Куда", 200, "w"),
            ("cargo", "Груз", 200, "w"),
            ("w", "Масса, т", 80, "e"),
            ("due", "Срок", 95, "center"),
            ("prio", "Приоритет", 90, "center"),
            ("status", "Статус", 110, "center"),
            ("trip", "Рейс", 60, "center"),
        ]
        fr, self.tree = make_tree(card.body, cols, height=20, stretch={"origin", "dest", "cargo"})
        fr.pack(fill="both", expand=True)
        self.refresh()

    def refresh(self):
        st = self.status.get()
        sql = ("SELECT o.*, na.name AS oname, nb.name AS dname, c.name AS cname FROM orders o JOIN nodes na ON na.id=o.origin "
               "JOIN nodes nb ON nb.id=o.destination JOIN cargo_types c ON c.code=o.cargo")
        params = ()
        if st != "все":
            sql += " WHERE o.status=?"
            params = (st,)
        sql += " ORDER BY CASE o.status WHEN 'новый' THEN 0 WHEN 'запланирован' THEN 1 WHEN 'в пути' THEN 2 ELSE 3 END, o.priority, o.due_date"
        rows = []
        tags = []
        for o in self.app.db.q(sql, params):
            rows.append((o["id"], o["id"], datetime.strptime(o["created_at"], "%Y-%m-%d %H:%M").strftime("%d.%m.%Y %H:%M"), o["oname"], o["dname"], o["cname"], fmt_num(o["weight_t"], 1), datetime.strptime(o["due_date"], "%Y-%m-%d").strftime("%d.%m.%Y"),
                         PRIORITY.get(o["priority"], ""), o["status"], o["trip_id"] or ""))
            tags.append(("bold",) if o["status"] == "новый" else (("muted",) if o["status"] in ("доставлен", "отменён") else ()))
        fill_tree(self.tree, rows, tags)
        n_new = self.app.db.scalar("SELECT COUNT(*) FROM orders WHERE status='новый'")
        w_new = self.app.db.scalar("SELECT COALESCE(SUM(weight_t),0) FROM orders WHERE status='новый'")
        self.summary.configure(text=f"К планированию: {n_new} заказов · {fmt_num(w_new)} т")

    def new_order(self):
        OrderDialog(self, self.app)

    def cancel_order(self):
        sel = self.tree.selection()
        if not sel:
            return
        oid = int(sel[0])
        o = self.app.db.one("SELECT * FROM orders WHERE id=?", (oid,))
        if o["status"] != "новый":
            messagebox.showinfo("Заказ", "Отменить можно только заказ в статусе «новый».")
            return
        if messagebox.askyesno("Заказ", f"Отменить заказ №{oid}?"):
            self.app.db.run("UPDATE orders SET status='отменён' WHERE id=?", (oid,))
            self.app.refresh_all()

    def optimize(self):
        if not self.app.db.scalar("SELECT COUNT(*) FROM orders WHERE status='новый'"):
            messagebox.showinfo("Планирование", "Нет новых заказов для планирования.")
            return
        self.app.set_status("ИИ формирует план перевозок…")
        self.update_idletasks()
        disp = Dispatcher(self.app.db, self.app.net)
        res = disp.plan()
        self.app.set_status("План сформирован")
        PlanDialog(self, self.app, disp, res)


class OrderDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Новый заказ")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        f = tk.Frame(self, bg=PANEL)
        f.pack(fill="both", expand=True, padx=18, pady=16)
        nodes = app.db.nodes()
        order = {"plant": 0, "deposit": 1, "hub": 2}
        nodes = sorted(nodes, key=lambda n: (order[n["kind"]], n["name"]))
        self.nodes = {n["name"]: n["id"] for n in nodes}
        self.cargos = {r["name"]: r for r in app.db.q("SELECT * FROM cargo_types")}
        self.src = tk.StringVar(value=nodes[0]["name"])
        self.dst = tk.StringVar()
        self.cargo = tk.StringVar(value="Сухие смеси в мешках")
        self.weight = tk.DoubleVar(value=10)
        self.due = tk.StringVar(value=(datetime.now() + timedelta(days=3)).strftime("%d.%m.%Y"))
        self.prio = tk.StringVar(value="обычный")
        form_row(f, 0, "Откуда", ttk.Combobox(f, textvariable=self.src, values=list(self.nodes), state="readonly", width=36, height=20))
        form_row(f, 1, "Куда", ttk.Combobox(f, textvariable=self.dst, values=list(self.nodes), state="readonly", width=36, height=20))
        form_row(f, 2, "Груз", ttk.Combobox(f, textvariable=self.cargo, values=list(self.cargos), state="readonly"))
        form_row(f, 3, "Масса, т", ttk.Spinbox(f, from_=0.5, to=500, increment=0.5, textvariable=self.weight))
        form_row(f, 4, "Срок доставки", ttk.Entry(f, textvariable=self.due))
        form_row(f, 5, "Приоритет", ttk.Combobox(f, textvariable=self.prio, values=list(PRIORITY.values()), state="readonly"))
        tk.Label(f, text="Крупные заказы автоматически делятся ИИ на несколько рейсов", bg=PANEL, fg=MUTED, font=FONT_S).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        b = tk.Frame(f, bg=PANEL)
        b.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(b, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Создать", style="Accent.TButton", command=self.save).pack(side="right", padx=6)
        self.grab_set()

    def save(self):
        try:
            src = self.nodes[self.src.get()]
            dst = self.nodes[self.dst.get()]
            cargo = self.cargos[self.cargo.get()]["code"]
            w = float(self.weight.get())
            due = datetime.strptime(self.due.get().strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
        except (KeyError, ValueError, tk.TclError):
            messagebox.showwarning("Заказ", "Проверьте поля формы (дата в формате ДД.ММ.ГГГГ).", parent=self)
            return
        if src == dst or w <= 0:
            messagebox.showwarning("Заказ", "Укажите разные точки и положительную массу.", parent=self)
            return
        prio = {v: k for k, v in PRIORITY.items()}[self.prio.get()]
        self.app.db.run(
            "INSERT INTO orders(created_at,origin,destination,cargo,weight_t,due_date,priority,status) VALUES (?,?,?,?,?,?,?, 'новый')",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), src, dst, cargo, w, due, prio),
        )
        self.destroy()
        self.app.refresh_all()


class PlanDialog(tk.Toplevel):
    def __init__(self, parent, app, disp, res):
        super().__init__(parent)
        self.app = app
        self.disp = disp
        self.res = res
        self.title("План перевозок — результат оптимизации ИИ")
        self.configure(bg=BG)
        self.geometry("1320x820")
        self.transient(parent.winfo_toplevel())
        opt = res["optimized"]
        base = res["baseline_served"]
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 0))

        def delta(a, b):
            return (b - a) / b * 100 if b else 0.0

        k = [
            ("Транспортные расходы", fmt_rub(opt["cost"]), f"было бы {fmt_rub(base['cost'])} · −{delta(opt['cost'], base['cost']):.1f}%", GOOD),
            ("Холостой пробег", f"{fmt_num(opt['empty_km'])} км", f"было бы {fmt_num(base['empty_km'])} км · −{delta(opt['empty_km'], base['empty_km']):.1f}%", GOOD),
            ("Топливо", f"{fmt_num(opt['fuel_l'])} л", f"было бы {fmt_num(base['fuel_l'])} л · −{delta(opt['fuel_l'], base['fuel_l']):.1f}%", GOOD),
            ("Ожидаемые потери груза", fmt_rub(opt["loss"]), f"традиционно {fmt_rub(base['loss'])}", ACCENT),
            ("Рейсы / ТС", f"{opt['loads']} / {opt['trips']}", f"заказов {len(res['served_orders'])} из {res['n_orders']} · объединений {res['merges']}", TEXT),
        ]
        for i, (t, v, s, c) in enumerate(k):
            w = Kpi(top, t, v, s, c)
            w.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            top.columnconfigure(i, weight=1)

        mid = ttk.PanedWindow(self, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=12, pady=12)
        card = Card(mid, "Цепочки рейсов по транспортным средствам")
        cols = [
            ("veh", "ТС", 150, "w"),
            ("chain", "Цепочка (погрузка → выгрузка)", 300, "w"),
            ("t", "Груз, т", 65, "e"),
            ("km", "Км", 70, "e"),
            ("ekm", "Порожн., км", 85, "e"),
            ("h", "Длит.", 110, "e"),
            ("cost", "Стоимость", 100, "e"),
            ("save", "Экономия", 95, "e"),
        ]
        fr, self.tree = make_tree(card.body, cols, height=16, stretch={"chain"})
        fr.pack(fill="both", expand=True)
        mid.add(card, weight=3)
        mp = tk.Frame(mid, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.map = MapCanvas(mp, app, legend=False)
        self.map.pack(fill="both", expand=True)
        mid.add(mp, weight=2)
        net = app.net
        rows = []
        tags = []
        for i, ch in enumerate(res["chains"]):
            v = ch["vehicle"]
            parts = []
            for ld in ch["loads"]:
                parts.append(f"{short(net, ld.origin)} → " + " → ".join(short(net, s) for s in ld.stops))
            save = ch["baseline_cost"] - ch["cost"]
            rows.append((i, f"{v['plate']} ({v['body']})", " | ".join(parts), fmt_num(ch["tonnage"], 1), fmt_num(ch["km"]), fmt_num(ch["empty_km"]), fmt_hours(ch["hours"]), fmt_rub(ch["cost"]), fmt_rub(save)))
            tags.append(("good",) if save > 0 else ())
        for j, ld in enumerate(res["unassigned"]):
            rows.append((f"u{j}", "не назначено", f"{short(net, ld.origin)} → " + " → ".join(short(net, s) for s in ld.stops), fmt_num(ld.weight, 1), "", "", "", "нет свободного ТС", ""))
            tags.append(("bad",))
        fill_tree(self.tree, rows, tags)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_chain())

        bot = tk.Frame(self, bg=BG)
        bot.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(bot, text="Экономия считается против традиционной схемы: каждый заказ — отдельный рейс машиной своего завода по кратчайшему пути с возвратом порожняком.",
                 bg=BG, fg=MUTED, font=FONT_S).pack(side="left")
        ttk.Button(bot, text="Закрыть", command=self.destroy).pack(side="right")
        ttk.Button(bot, text="Утвердить план", style="Accent.TButton", command=self.commit).pack(side="right", padx=6)
        if res["chains"]:
            self.tree.selection_set("0")
        self.grab_set()

    def show_chain(self):
        sel = self.tree.selection()
        if not sel or not sel[0].isdigit():
            return
        ch = self.res["chains"][int(sel[0])]
        items = []
        for kind, r, _ in ch["legs"]:
            if kind == "loaded":
                items.append({"nodes": r.nodes, "roads": r.roads, "color": ACCENT, "width": 6})
            else:
                items.append({"nodes": r.nodes, "roads": r.roads, "color": "#64748B", "width": 4, "dash": (6, 4)})
        self.map.highlight = items
        net = self.app.net
        lats = [net.nodes[n]["lat"] for it in items for n in it["nodes"]]
        lons = [net.nodes[n]["lon"] for it in items for n in it["nodes"]]
        if lats:
            pl = max(1.0, (max(lats) - min(lats)) * 0.2)
            po = max(1.5, (max(lons) - min(lons)) * 0.2)
            self.map._fitted = True
            self.map.fit(min(lons) - po, max(lons) + po, min(lats) - pl, max(lats) + pl)

    def commit(self):
        ids = self.disp.commit(self.res)
        self.destroy()
        self.app.refresh_all()
        messagebox.showinfo("План утверждён", f"Сформировано рейсов: {len(ids)}. Они доступны на вкладке «Рейсы».")


def short(net, nid):
    return net.nodes[nid]["name"].replace("Месторождение гипса ", "М-е ").replace(" (РЦ)", "")
