import tkinter as tk
from tkinter import messagebox, ttk

from ..ai.network import DEFAULT_PROFILE
from ..geo import fmt_num
from .theme import BG, FONT_S, MUTED, PANEL, Card, fill_tree, form_row, make_tree

STATUSES = ["свободна", "назначена", "в рейсе", "ремонт"]


class FleetTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=(12, 0))
        ttk.Button(bar, text="Добавить ТС", command=lambda: VehicleDialog(self, app)).pack(side="left")
        ttk.Button(bar, text="Изменить", command=self.edit).pack(side="left", padx=6)
        ttk.Button(bar, text="Удалить", command=self.delete).pack(side="left")
        ttk.Button(bar, text="В ремонт / из ремонта", command=self.toggle_repair).pack(side="left", padx=6)
        self.summary = tk.Label(bar, text="", bg=BG, fg=MUTED, font=FONT_S)
        self.summary.pack(side="right")
        card = Card(self)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        cols = [
            ("plate", "Госномер", 110, "center"),
            ("model", "Модель", 200, "w"),
            ("body", "Кузов", 100, "center"),
            ("cap", "Г/п, т", 70, "e"),
            ("fuel", "Расход, л/100", 100, "e"),
            ("base", "База", 190, "w"),
            ("loc", "Местоположение", 190, "w"),
            ("status", "Статус", 100, "center"),
            ("odo", "Пробег, км", 100, "e"),
        ]
        fr, self.tree = make_tree(card.body, cols, height=22, stretch={"model", "base", "loc"})
        fr.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.refresh()

    def refresh(self):
        rows = []
        tags = []
        for v in self.app.db.q("SELECT v.*, nb.name AS bname, nl.name AS lname FROM vehicles v JOIN nodes nb ON nb.id=v.base_node JOIN nodes nl ON nl.id=v.location_node ORDER BY nb.name, v.body, v.plate"):
            rows.append((v["id"], v["plate"], v["model"], v["body"], fmt_num(v["capacity_t"]), fmt_num(v["fuel_l_100"], 1), v["bname"], v["lname"], v["status"], fmt_num(v["odometer_km"])))
            tags.append(("bad",) if v["status"] == "ремонт" else (("warn",) if v["status"] != "свободна" else ()))
        fill_tree(self.tree, rows, tags)
        parts = [f"{r['body']}: {r['n']}" for r in self.app.db.q("SELECT body, COUNT(*) n FROM vehicles GROUP BY body")]
        self.summary.configure(text="Всего ТС по типам — " + ", ".join(parts))

    def _sel(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Автопарк", "Выберите ТС в таблице.")
            return None
        return self.app.db.one("SELECT * FROM vehicles WHERE id=?", (int(sel[0]),))

    def edit(self):
        v = self._sel()
        if v:
            VehicleDialog(self, self.app, v)

    def delete(self):
        v = self._sel()
        if not v:
            return
        if self.app.db.scalar("SELECT COUNT(*) FROM trips WHERE vehicle_id=?", (v["id"],)):
            messagebox.showinfo("Автопарк", "У ТС есть рейсы в истории — переведите его в ремонт вместо удаления.")
            return
        if messagebox.askyesno("Автопарк", f"Удалить ТС {v['plate']}?"):
            self.app.db.run("DELETE FROM vehicles WHERE id=?", (v["id"],))
            self.app.refresh_all()

    def toggle_repair(self):
        v = self._sel()
        if not v:
            return
        if v["status"] in ("назначена", "в рейсе"):
            messagebox.showinfo("Автопарк", "ТС занято в рейсе.")
            return
        new = "свободна" if v["status"] == "ремонт" else "ремонт"
        self.app.db.run("UPDATE vehicles SET status=? WHERE id=?", (new, v["id"]))
        self.app.refresh_all()


class VehicleDialog(tk.Toplevel):
    def __init__(self, parent, app, v=None):
        super().__init__(parent)
        self.app = app
        self.v = v
        self.title("Транспортное средство")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        f = tk.Frame(self, bg=PANEL)
        f.pack(fill="both", expand=True, padx=18, pady=16)
        nodes = app.db.q("SELECT * FROM nodes ORDER BY kind DESC, name")
        self.nodes = {n["name"]: n["id"] for n in nodes}
        plants = [n["name"] for n in nodes if n["kind"] == "plant"]
        names = {n["id"]: n["name"] for n in nodes}
        self.plate = tk.StringVar(value=v["plate"] if v else "")
        self.model = tk.StringVar(value=v["model"] if v else "")
        self.body = tk.StringVar(value=v["body"] if v else "тент")
        self.cap = tk.DoubleVar(value=v["capacity_t"] if v else 20)
        self.fuel = tk.DoubleVar(value=v["fuel_l_100"] if v else 31)
        self.base = tk.StringVar(value=names[v["base_node"]] if v else plants[0])
        self.loc = tk.StringVar(value=names[v["location_node"]] if v else plants[0])
        form_row(f, 0, "Госномер", ttk.Entry(f, textvariable=self.plate, width=34))
        form_row(f, 1, "Модель", ttk.Entry(f, textvariable=self.model))
        cb = form_row(f, 2, "Кузов", ttk.Combobox(f, textvariable=self.body, values=list(DEFAULT_PROFILE), state="readonly"))
        cb.bind("<<ComboboxSelected>>", self._defaults)
        form_row(f, 3, "Грузоподъёмность, т", ttk.Spinbox(f, from_=1, to=60, increment=1, textvariable=self.cap))
        form_row(f, 4, "Расход, л/100 км", ttk.Spinbox(f, from_=10, to=60, increment=0.5, textvariable=self.fuel))
        form_row(f, 5, "База", ttk.Combobox(f, textvariable=self.base, values=plants, state="readonly"))
        form_row(f, 6, "Местоположение", ttk.Combobox(f, textvariable=self.loc, values=list(self.nodes), state="readonly", height=20))
        b = tk.Frame(f, bg=PANEL)
        b.grid(row=7, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(b, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Сохранить", style="Accent.TButton", command=self.save).pack(side="right", padx=6)
        self.grab_set()

    def _defaults(self, e=None):
        p = DEFAULT_PROFILE[self.body.get()]
        self.cap.set(p["capacity_t"])
        self.fuel.set(p["fuel_l_100"])

    def save(self):
        try:
            data = (self.plate.get().strip().upper(), self.model.get().strip(), self.body.get(), float(self.cap.get()), float(self.fuel.get()), self.nodes[self.base.get()], self.nodes[self.loc.get()])
        except (ValueError, KeyError, tk.TclError):
            messagebox.showwarning("ТС", "Проверьте значения.", parent=self)
            return
        if not data[0] or not data[1]:
            messagebox.showwarning("ТС", "Укажите госномер и модель.", parent=self)
            return
        try:
            if self.v:
                self.app.db.run("UPDATE vehicles SET plate=?, model=?, body=?, capacity_t=?, fuel_l_100=?, base_node=?, location_node=? WHERE id=?", data + (self.v["id"],))
            else:
                self.app.db.run("INSERT INTO vehicles(plate,model,body,capacity_t,fuel_l_100,base_node,location_node) VALUES (?,?,?,?,?,?,?)", data)
        except Exception as ex:
            messagebox.showerror("ТС", f"Не удалось сохранить: {ex}", parent=self)
            return
        self.destroy()
        self.app.refresh_all()
