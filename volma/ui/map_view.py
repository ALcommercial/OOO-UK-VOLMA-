import math
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

from ..geo import fmt_hours, fmt_num
from .theme import (ACCENT, BAD, BG, BLUE, BORDER, FONT_B, FONT_S, GOOD, MAP_BG, MAP_GRID, MUTED, PANEL, TEXT, WARN, Card,
                    congestion_color)

KIND_STYLE = {
    "plant": {"color": ACCENT, "label": "Завод ВОЛМА"},
    "deposit": {"color": "#8B5A2B", "label": "Месторождение гипса"},
    "hub": {"color": BLUE, "label": "РЦ / клиент"},
}

VIEWS = {
    "Вся сеть": (28, 108, 42, 61),
    "Европейская часть": (29, 62, 43, 60.5),
    "Юг и Казахстан": (36, 60, 43, 53),
    "Урал и Сибирь": (54, 108, 50, 58),
}


class MapCanvas(tk.Canvas):
    def __init__(self, parent, app, legend=True, **kw):
        super().__init__(parent, bg=MAP_BG, highlightthickness=0, **kw)
        self.app = app
        self.legend = legend
        self._bounds = None
        self.scale = 10.0
        self.ox = 0.0
        self.oy = 0.0
        self.lat0 = 52.0
        self.when = datetime.now()
        self.highlight = []
        self.show_roads = True
        self.show_labels = True
        self.show_vehicles = True
        self.show_hubs = True
        self.on_node_click = None
        self._drag = None
        self._fitted = False
        self._tip = None
        self.bind("<Configure>", self._on_resize)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", lambda e: self._zoom(e.x, e.y, 1.15))
        self.bind("<Button-5>", lambda e: self._zoom(e.x, e.y, 1 / 1.15))
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda e: self._hide_tip())

    def proj(self, lat, lon):
        x = lon * math.cos(math.radians(self.lat0))
        y = -lat
        return x * self.scale + self.ox, y * self.scale + self.oy

    def fit(self, lon1, lon2, lat1, lat2):
        self._bounds = (lon1, lon2, lat1, lat2)
        w = max(self.winfo_width(), 300)
        h = max(self.winfo_height(), 200)
        k = math.cos(math.radians(self.lat0))
        sx = w / ((lon2 - lon1) * k)
        sy = h / (lat2 - lat1)
        self.scale = min(sx, sy) * 0.94
        cx = (lon1 + lon2) / 2 * k * self.scale
        cy = -(lat1 + lat2) / 2 * self.scale
        self.ox = w / 2 - cx
        self.oy = h / 2 - cy
        self.redraw()

    def set_view(self, name):
        self.fit(*VIEWS[name])

    def _on_resize(self, e):
        if self._bounds and e.width > 50:
            self.fit(*self._bounds)
        elif not self._fitted and e.width > 50:
            self._fitted = True
            self.fit(*VIEWS["Европейская часть"])
        else:
            self.redraw()

    def _press(self, e):
        self._drag = (e.x, e.y, e.x, e.y)

    def _motion(self, e):
        if self._drag:
            x0, y0, sx, sy = self._drag
            self._bounds = None
            self.ox += e.x - x0
            self.oy += e.y - y0
            self._drag = (e.x, e.y, sx, sy)
            self.redraw()

    def _release(self, e):
        if self._drag:
            _, _, sx, sy = self._drag
            self._drag = None
            if abs(e.x - sx) < 4 and abs(e.y - sy) < 4:
                self._click(e)

    def _wheel(self, e):
        self._zoom(e.x, e.y, 1.15 if e.delta > 0 else 1 / 1.15)

    def _zoom(self, x, y, f):
        self._bounds = None
        new = max(3.0, min(400.0, self.scale * f))
        f = new / self.scale
        self.ox = x - (x - self.ox) * f
        self.oy = y - (y - self.oy) * f
        self.scale = new
        self.redraw()

    def _click(self, e):
        items = self.find_overlapping(e.x - 6, e.y - 6, e.x + 6, e.y + 6)
        for it in reversed(items):
            for t in self.gettags(it):
                if t.startswith("node:") and self.on_node_click:
                    self.on_node_click(int(t.split(":")[1]))
                    return

    def _hover(self, e):
        items = self.find_overlapping(e.x - 3, e.y - 3, e.x + 3, e.y + 3)
        for it in reversed(items):
            for t in self.gettags(it):
                if t.startswith("node:"):
                    self._show_tip(e, self._node_tip(int(t.split(":")[1])))
                    return
                if t.startswith("road:"):
                    self._show_tip(e, self._road_tip(int(t.split(":")[1])))
                    return
        self._hide_tip()

    def _node_tip(self, nid):
        n = self.app.net.nodes[nid]
        lines = [n["name"], f"{n['region']}" + (" (Казахстан)" if n["country"] == "KZ" else "")]
        if n["kind"] in ("plant", "deposit"):
            lines.append(f"Мощность: {fmt_num(n['capacity_tpd'])} т/сут · запас {fmt_num(n['stock_t'])} т")
        if n["products"]:
            lines.append(n["products"])
        wx = self.app.net.weather.get(n["region"], "ясно")
        lines.append(f"Погода: {wx}")
        cnt = self.app.db.scalar("SELECT COUNT(*) FROM vehicles WHERE location_node=?", (nid,))
        if cnt:
            lines.append(f"ТС на площадке: {cnt}")
        return "\n".join(lines)

    def _road_tip(self, rid):
        net = self.app.net
        r = net.road_rows[rid]
        c = net.congestion(rid, self.when)
        lines = [
            f"{r['name']}",
            f"{net.nodes[r['a']]['name']} — {net.nodes[r['b']]['name']}",
            f"{fmt_num(r['distance_km'])} км · {r['category']} · покрытие {int(r['quality'] * 100)}%",
            f"Прогноз ИИ на {self.when:%H:%M}: загруженность ×{c:.2f}",
            f"Погода: {net.edge_weather(r)}",
        ]
        if r["toll_rub_km"]:
            lines.append(f"Платная: {r['toll_rub_km']} ₽/км")
        if r["border"]:
            lines.append("Пограничный переход")
        e = net.events.get(rid)
        if e:
            lines.append(f"⚠ {e['kind']}: {e['description']}")
        return "\n".join(lines)

    def _show_tip(self, e, text):
        self._hide_tip()
        x, y = e.x + 14, e.y + 10
        t = self.create_text(x + 8, y + 6, text=text, anchor="nw", font=FONT_S, fill=TEXT, tags="tip")
        bx = self.bbox(t)
        w = self.winfo_width()
        if bx[2] + 8 > w:
            self.move(t, -(bx[2] - bx[0]) - 40, 0)
            bx = self.bbox(t)
        r = self.create_rectangle(bx[0] - 8, bx[1] - 6, bx[2] + 8, bx[3] + 6, fill=PANEL, outline=BORDER, tags="tip")
        self.tag_lower(r, t)
        self._tip = True

    def _hide_tip(self):
        if self._tip:
            self.delete("tip")
            self._tip = None

    def redraw(self):
        self.delete("all")
        self._tip = None
        net = self.app.net
        w = self.winfo_width()
        h = self.winfo_height()
        step = 5 if self.scale < 25 else (2 if self.scale < 70 else 1)
        for lon in range(20, 115, step):
            x1, y1 = self.proj(40, lon)
            x2, y2 = self.proj(63, lon)
            self.create_line(x1, y1, x2, y2, fill=MAP_GRID)
            self.create_text(x1 + 2, h - 4, text=f"{lon}°", anchor="sw", fill="#A9B4C2", font=("Segoe UI", 7))
        for lat in range(40, 64, step):
            x1, y1 = self.proj(lat, 20)
            x2, y2 = self.proj(lat, 115)
            self.create_line(x1, y1, x2, y2, fill=MAP_GRID)
            self.create_text(4, y1 - 2, text=f"{lat}°", anchor="sw", fill="#A9B4C2", font=("Segoe UI", 7))
        hl_roads = set()
        for item in self.highlight:
            hl_roads.update(item.get("roads", []))
        if self.show_roads:
            for rid, r in net.road_rows.items():
                a = net.nodes[r["a"]]
                b = net.nodes[r["b"]]
                x1, y1 = self.proj(a["lat"], a["lon"])
                x2, y2 = self.proj(b["lat"], b["lon"])
                if net.is_closed(rid):
                    self.create_line(x1, y1, x2, y2, fill=BAD, width=3, dash=(6, 4), tags=(f"road:{rid}",))
                    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                    self.create_oval(mx - 8, my - 8, mx + 8, my + 8, fill=BAD, outline="white", width=2, tags=(f"road:{rid}",))
                    self.create_text(mx, my, text="×", fill="white", font=FONT_B, tags=(f"road:{rid}",))
                    continue
                c = net.congestion(rid, self.when)
                width = {"федеральная": 4, "региональная": 3, "местная": 2}[r["category"]]
                self.create_line(x1, y1, x2, y2, fill="#C9D2DD", width=width + 3, capstyle="round", tags=(f"road:{rid}",))
                self.create_line(x1, y1, x2, y2, fill=congestion_color(c), width=width, capstyle="round", tags=(f"road:{rid}",))
                e = net.events.get(rid)
                if e:
                    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                    self.create_polygon(mx, my - 10, mx - 9, my + 7, mx + 9, my + 7, fill=WARN, outline="white", width=1.5, tags=(f"road:{rid}",))
                    self.create_text(mx, my + 1, text="!", fill="white", font=FONT_B, tags=(f"road:{rid}",))
                if r["border"]:
                    mx, my = (x1 * 0.7 + x2 * 0.3), (y1 * 0.7 + y2 * 0.3)
                    self.create_rectangle(mx - 5, my - 5, mx + 5, my + 5, fill="white", outline=TEXT, tags=(f"road:{rid}",))
        for item in self.highlight:
            pts = []
            for nid in item["nodes"]:
                n = net.nodes[nid]
                pts.extend(self.proj(n["lat"], n["lon"]))
            if len(pts) >= 4:
                color = item.get("color", ACCENT)
                dash = item.get("dash")
                self.create_line(*pts, fill="white", width=item.get("width", 6) + 4, capstyle="round", joinstyle="round")
                self.create_line(*pts, fill=color, width=item.get("width", 6), capstyle="round", joinstyle="round", arrow="last", arrowshape=(16, 18, 6), dash=dash)
        hl_nodes = set()
        for item in self.highlight:
            hl_nodes.update(item["nodes"])
        veh = {}
        if self.show_vehicles:
            for r in self.app.db.q("SELECT location_node, status, COUNT(*) AS n FROM vehicles GROUP BY location_node, status"):
                veh.setdefault(r["location_node"], []).append((r["status"], r["n"]))
        for nid, n in net.nodes.items():
            if not self.show_hubs and n["kind"] == "hub" and nid not in hl_nodes:
                continue
            x, y = self.proj(n["lat"], n["lon"])
            col = KIND_STYLE[n["kind"]]["color"]
            tag = (f"node:{nid}",)
            big = 1.25 if nid in hl_nodes else 1.0
            if n["kind"] == "plant":
                s = 8 * big
                self.create_rectangle(x - s, y - s, x + s, y + s, fill=col, outline="white", width=2, tags=tag)
                self.create_text(x, y, text="В", fill="white", font=("Segoe UI Semibold", 8), tags=tag)
            elif n["kind"] == "deposit":
                s = 9 * big
                self.create_polygon(x, y - s, x - s, y + s * 0.8, x + s, y + s * 0.8, fill=col, outline="white", width=2, tags=tag)
            else:
                s = 6 * big
                self.create_oval(x - s, y - s, x + s, y + s, fill=col, outline="white", width=2, tags=tag)
            show = nid in hl_nodes or (n["kind"] == "plant" and self.scale > 9) or (n["kind"] == "hub" and self.scale > 24) or (n["kind"] == "deposit" and self.scale > 40)
            if self.show_labels and show:
                name = n["name"].replace("Месторождение гипса ", "").replace(" (РЦ)", "")
                if self.scale < 40:
                    name = name.replace("ВОЛМА-", "")
                font = FONT_B if n["kind"] == "plant" else FONT_S
                if n["kind"] == "deposit":
                    t = self.create_text(x + 12, y + 4, text=name, fill="#6B4423", font=FONT_S, anchor="w", tags=tag)
                elif n["kind"] == "plant":
                    dy = -18 if n["code"] == "VLG" else 18
                    t = self.create_text(x, y + dy, text=name, fill=TEXT, font=font, tags=tag)
                else:
                    t = self.create_text(x, y - 14, text=name, fill=TEXT, font=font, tags=tag)
                bx = self.bbox(t)
                bg = self.create_rectangle(bx[0] - 3, bx[1] - 1, bx[2] + 3, bx[3] + 1, fill=MAP_BG, outline="", tags=tag)
                self.tag_lower(bg, t)
            if nid in veh:
                total = sum(c for _, c in veh[nid])
                busy = any(s != "свободна" for s, _ in veh[nid])
                vx, vy = x + 12, y + 8
                self.create_oval(vx - 8, vy - 8, vx + 8, vy + 8, fill=(WARN if busy else "#334155"), outline="white", width=1.5, tags=tag)
                self.create_text(vx, vy, text=str(total), fill="white", font=("Segoe UI Semibold", 7), tags=tag)
        if self.legend:
            self._legend(w, h)

    def _legend(self, w, h):
        x0, y0 = 12, 12
        rows = [
            ("rect", ACCENT, "Завод ВОЛМА"),
            ("tri", "#8B5A2B", "Месторождение гипса"),
            ("oval", BLUE, "РЦ / клиент"),
            ("veh", "#334155", "ТС (кол-во)"),
            ("line", GOOD, "Свободно (ИИ-прогноз)"),
            ("line", WARN, "Затруднено"),
            ("line", BAD, "Пробки"),
            ("dash", BAD, "Перекрытие"),
            ("warn", WARN, "Событие на дороге"),
            ("box", "white", "Пограничный переход"),
        ]
        hgt = 26 + len(rows) * 18
        self.create_rectangle(x0, y0, x0 + 190, y0 + hgt, fill=PANEL, outline=BORDER)
        self.create_text(x0 + 10, y0 + 12, text=f"Прогноз на {self.when:%d.%m %H:%M}", anchor="w", font=FONT_B, fill=TEXT)
        for i, (kind, col, label) in enumerate(rows):
            y = y0 + 32 + i * 18
            x = x0 + 18
            if kind == "rect":
                self.create_rectangle(x - 6, y - 6, x + 6, y + 6, fill=col, outline="")
            elif kind == "tri":
                self.create_polygon(x, y - 7, x - 7, y + 6, x + 7, y + 6, fill=col, outline="")
            elif kind == "oval":
                self.create_oval(x - 5, y - 5, x + 5, y + 5, fill=col, outline="")
            elif kind == "veh":
                self.create_oval(x - 6, y - 6, x + 6, y + 6, fill=col, outline="")
            elif kind == "line":
                self.create_line(x - 9, y, x + 9, y, fill=col, width=4)
            elif kind == "dash":
                self.create_line(x - 9, y, x + 9, y, fill=col, width=3, dash=(4, 3))
            elif kind == "warn":
                self.create_polygon(x, y - 7, x - 7, y + 6, x + 7, y + 6, fill=col, outline="")
            elif kind == "box":
                self.create_rectangle(x - 5, y - 5, x + 5, y + 5, fill=col, outline=TEXT)
            self.create_text(x + 16, y, text=label, anchor="w", font=FONT_S, fill=TEXT)


class MapTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        side = tk.Frame(self, bg=BG, width=300)
        side.pack(side="left", fill="y", padx=(12, 6), pady=12)
        side.pack_propagate(False)
        wrap = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        wrap.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=12)
        self.canvas = MapCanvas(wrap, app)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.on_node_click = self.show_node

        c1 = Card(side, "Вид карты")
        c1.pack(fill="x")
        self.view = tk.StringVar(value="Европейская часть")
        cb = ttk.Combobox(c1.body, textvariable=self.view, values=list(VIEWS), state="readonly")
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: self.canvas.set_view(self.view.get()))
        self.v_labels = tk.BooleanVar(value=True)
        self.v_veh = tk.BooleanVar(value=True)
        self.v_hubs = tk.BooleanVar(value=True)
        for text, var in (("Подписи", self.v_labels), ("Транспорт", self.v_veh), ("РЦ и клиенты", self.v_hubs)):
            ttk.Checkbutton(c1.body, text=text, variable=var, command=self.apply).pack(anchor="w", pady=(6, 0))
        tk.Label(c1.body, text="Колесо мыши — масштаб, перетаскивание — сдвиг", bg=PANEL, fg=MUTED, font=FONT_S, wraplength=250, justify="left").pack(anchor="w", pady=(8, 0))

        c2 = Card(side, "Прогноз загруженности (ИИ)")
        c2.pack(fill="x", pady=(10, 0))
        self.hour = tk.IntVar(value=0)
        self.hour_lbl = tk.Label(c2.body, text="", bg=PANEL, fg=TEXT, font=FONT_B)
        self.hour_lbl.pack(anchor="w")
        ttk.Scale(c2.body, from_=0, to=72, orient="horizontal", command=self._hour_changed).pack(fill="x", pady=(6, 0))
        tk.Label(c2.body, text="Сдвиньте ползунок, чтобы увидеть прогноз на ближайшие 72 часа", bg=PANEL, fg=MUTED, font=FONT_S, wraplength=250, justify="left").pack(anchor="w", pady=(6, 0))

        c3 = Card(side, "Объект")
        c3.pack(fill="both", expand=True, pady=(10, 0))
        self.info = tk.Label(c3.body, text="Нажмите на объект на карте", bg=PANEL, fg=MUTED, justify="left", anchor="nw", wraplength=255, font=FONT_S)
        self.info.pack(fill="both", expand=True)
        ttk.Button(c3.body, text="Сбросить выделение маршрута", command=self.clear_highlight).pack(fill="x", pady=(8, 0))
        self._hour_changed(0)

    def _hour_changed(self, v):
        h = int(float(v))
        base = datetime.now().replace(minute=0, second=0, microsecond=0)
        self.canvas.when = base + timedelta(hours=h)
        wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][self.canvas.when.weekday()]
        self.hour_lbl.configure(text=f"{wd} {self.canvas.when:%d.%m, %H:00}  (+{h} ч)")
        self.canvas.redraw()

    def apply(self):
        self.canvas.show_labels = self.v_labels.get()
        self.canvas.show_vehicles = self.v_veh.get()
        self.canvas.show_hubs = self.v_hubs.get()
        self.canvas.redraw()

    def show_node(self, nid):
        self.info.configure(text=self.canvas._node_tip(nid), fg=TEXT)

    def clear_highlight(self):
        self.canvas.highlight = []
        self.canvas.redraw()

    def show_routes(self, items, fit=True):
        self.canvas.highlight = items
        if fit and items:
            lats, lons = [], []
            for it in items:
                for nid in it["nodes"]:
                    n = self.app.net.nodes[nid]
                    lats.append(n["lat"])
                    lons.append(n["lon"])
            pad_lat = max(1.0, (max(lats) - min(lats)) * 0.15)
            pad_lon = max(1.5, (max(lons) - min(lons)) * 0.15)
            self.canvas.fit(min(lons) - pad_lon, max(lons) + pad_lon, min(lats) - pad_lat, max(lats) + pad_lat)
        else:
            self.canvas.redraw()

    def refresh(self):
        self.canvas.redraw()
