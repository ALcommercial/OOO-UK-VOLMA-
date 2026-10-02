import csv
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..geo import fmt_num
from .theme import BG, FONT_S, MUTED, PANEL, Card, fill_tree, form_row, make_tree

PARAMS = [
    ("fuel_price", "Цена дизтоплива, ₽/л"),
    ("driver_rate", "Ставка водителя, ₽/ч"),
    ("vehicle_rate", "Стоимость часа ТС, ₽/ч"),
    ("platon_rub_km", "«Платон», ₽/км (ТС > 12 т)"),
    ("border_delay_h", "Прохождение МАПП, ч"),
    ("late_penalty_rub_h", "Штраф за опоздание, ₽/ч"),
    ("w_cost", "Вес критерия «затраты»"),
    ("w_time", "Вес критерия «время»"),
    ("w_risk", "Вес критерия «сохранность»"),
]
KINDS = {"plant": "завод", "deposit": "месторождение", "hub": "РЦ / клиент"}


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        left = tk.Frame(self, bg=BG, width=360)
        left.pack(side="left", fill="y", padx=(12, 6), pady=12)
        left.pack_propagate(False)
        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=12)

        c = Card(left, "Экономические параметры")
        c.pack(fill="x")
        self.vars = {}
        for i, (k, label) in enumerate(PARAMS):
            v = tk.StringVar()
            self.vars[k] = v
            form_row(c.body, i, label, ttk.Entry(c.body, textvariable=v, width=10))
        ttk.Button(c.body, text="Сохранить", style="Accent.TButton", command=self.save).grid(row=len(PARAMS), column=0, columnspan=2, sticky="ew", pady=(10, 0))

        d = Card(left, "Данные")
        d.pack(fill="x", pady=(10, 0))
        ttk.Button(d.body, text="Экспорт рейсов в CSV", command=self.export).pack(fill="x")
        ttk.Button(d.body, text="Сбросить демо-данные", command=self.reset).pack(fill="x", pady=(6, 0))
        tk.Label(d.body, text=f"База данных: {app.db.path}", bg=PANEL, fg=MUTED, font=FONT_S, wraplength=320, justify="left").pack(anchor="w", pady=(8, 0))

        o = Card(right, "Объекты логистической сети")
        o.pack(fill="both", expand=True)
        cols = [("kind", "Тип", 125, "w"), ("name", "Название", 250, "w"), ("region", "Регион", 190, "w"), ("addr", "Адрес", 230, "w"),
                ("cap", "Мощность, т/сут", 110, "e"), ("stock", "Запас, т", 90, "e"), ("prod", "Продукция", 200, "w")]
        fr, self.nodes = make_tree(o.body, cols, height=14, stretch={"name", "addr", "prod"})
        fr.pack(fill="both", expand=True)
        b = tk.Frame(o.body, bg=PANEL)
        b.pack(fill="x", pady=(8, 0))
        tk.Label(b, text="Запас, т:", bg=PANEL, fg=MUTED).pack(side="left")
        self.stock = tk.StringVar()
        ttk.Entry(b, textvariable=self.stock, width=10).pack(side="left", padx=6)
        ttk.Button(b, text="Обновить запас", command=self.set_stock).pack(side="left")

        g = Card(right, "Типы грузов и параметры риска потерь")
        g.pack(fill="x", pady=(10, 0))
        cols = [("name", "Груз", 230, "w"), ("body", "Кузов", 100, "center"), ("price", "Цена, ₽/т", 100, "e"), ("loss", "Базовые потери на 100 км", 170, "e"),
                ("road", "Чувств. к дорогам", 130, "e"), ("wx", "Чувств. к погоде", 130, "e")]
        fr, self.cargo = make_tree(g.body, cols, height=6, stretch={"name"})
        fr.pack(fill="x")
        self.refresh()

    def refresh(self):
        for k, _ in PARAMS:
            self.vars[k].set(str(self.app.db.setting(k)))
        rows = []
        for n in self.app.db.q("SELECT * FROM nodes ORDER BY CASE kind WHEN 'plant' THEN 0 WHEN 'deposit' THEN 1 ELSE 2 END, name"):
            rows.append((n["id"], KINDS[n["kind"]], n["name"], n["region"] + (" (KZ)" if n["country"] == "KZ" else ""), n["address"], fmt_num(n["capacity_tpd"]) if n["capacity_tpd"] else "",
                         fmt_num(n["stock_t"]) if n["stock_t"] else "", n["products"]))
        fill_tree(self.nodes, rows)
        rows = []
        for c in self.app.db.q("SELECT * FROM cargo_types"):
            rows.append((c["code"], c["name"], c["body"], fmt_num(c["price_rub_t"]), f"{c['loss_base'] * 100:.2f}%", f"{c['road_sensitivity']:.1f}", f"{c['weather_sensitivity']:.1f}"))
        fill_tree(self.cargo, rows)

    def save(self):
        try:
            vals = {k: float(self.vars[k].get().replace(",", ".")) for k, _ in PARAMS}
        except ValueError:
            messagebox.showwarning("Параметры", "Введите числовые значения.")
            return
        for k, v in vals.items():
            self.app.db.set_setting(k, v)
        self.app.net.refresh()
        self.app.refresh_all()
        self.app.set_status("Параметры сохранены")

    def set_stock(self):
        sel = self.nodes.selection()
        if not sel:
            return
        try:
            v = float(self.stock.get().replace(",", "."))
        except ValueError:
            return
        self.app.db.run("UPDATE nodes SET stock_t=? WHERE id=?", (v, int(sel[0])))
        self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")], initialfile="рейсы_волма.csv")
        if not path:
            return
        net = self.app.net
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["№", "Создан", "ТС", "Статус", "Маршрут", "Груз, т", "Пробег, км", "Порожний, км", "Часы", "Топливо, л", "Стоимость, ₽", "Традиционная схема, ₽", "Экономия, ₽", "Риск потерь, ₽"])
            for t in self.app.db.q("SELECT t.*, v.plate FROM trips t JOIN vehicles v ON v.id=t.vehicle_id ORDER BY t.id"):
                route = " → ".join(net.nodes[n]["name"] for n in json.loads(t["route_nodes"]))
                w.writerow([t["id"], t["created_at"], t["plate"], t["status"], route, t["load_t"], t["distance_km"], t["empty_km"], t["duration_h"], t["fuel_l"], t["cost_rub"],
                            t["baseline_cost_rub"], round(t["baseline_cost_rub"] - t["cost_rub"]), t["loss_rub"]])
        self.app.set_status(f"Экспортировано: {path}")

    def reset(self):
        if not messagebox.askyesno("Сброс", "Удалить все изменения и восстановить демонстрационные данные?"):
            return
        self.app.db.reset()
        self.app.model.load()
        self.app.net.refresh()
        self.app.refresh_all()
