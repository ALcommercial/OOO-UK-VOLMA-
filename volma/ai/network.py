import heapq
import itertools
from datetime import datetime, timedelta

WEATHER_RANK = {"ясно": 0, "дождь": 1, "туман": 2, "снег": 3, "гололёд": 4}
WEATHER_SPEED = {"ясно": 1.0, "дождь": 0.92, "туман": 0.86, "снег": 0.78, "гололёд": 0.68}
WEATHER_FUEL = {"ясно": 1.0, "дождь": 1.03, "туман": 1.02, "снег": 1.1, "гололёд": 1.08}
WEATHER_RISK = {"ясно": 0.0, "дождь": 0.35, "туман": 0.15, "снег": 0.45, "гололёд": 0.7}
BASE_SPEED = {"федеральная": 78.0, "региональная": 64.0, "местная": 42.0}
DEFAULT_PROFILE = {
    "тент": {"capacity_t": 20.0, "fuel_l_100": 31.0},
    "самосвал": {"capacity_t": 25.0, "fuel_l_100": 38.0},
    "цементовоз": {"capacity_t": 30.0, "fuel_l_100": 35.0},
}
EVENT_DELAY = {"ремонт": 2.0, "ДТП": 3.0, "пробка": 2.5, "погода": 2.0}
PRESETS = {
    "Баланс": (1.0, 1.0, 1.0),
    "Минимум затрат": (1.6, 0.6, 1.0),
    "Скорость доставки": (0.7, 2.2, 1.0),
    "Сохранность груза": (0.9, 0.8, 4.0),
}


class RouteResult:
    def __init__(self):
        self.nodes = []
        self.roads = []
        self.segments = []
        self.km = 0.0
        self.drive_h = 0.0
        self.rest_h = 0.0
        self.border_h = 0.0
        self.fuel_l = 0.0
        self.fuel_rub = 0.0
        self.toll_rub = 0.0
        self.time_rub = 0.0
        self.loss_rub = 0.0
        self.gen_cost = 0.0
        self.closed = False
        self.departure = None
        self.arrival = None
        self.label = ""

    @property
    def total_h(self):
        return self.drive_h + self.rest_h + self.border_h

    @property
    def total_rub(self):
        return self.fuel_rub + self.toll_rub + self.time_rub + self.loss_rub


class Network:
    def __init__(self, db, model):
        self.db = db
        self.model = model
        self.refresh()

    def refresh(self):
        self.nodes = self.db.node_map()
        self.road_rows = {r["id"]: r for r in self.db.roads()}
        self.adj = {nid: [] for nid in self.nodes}
        for r in self.road_rows.values():
            self.adj[r["a"]].append((r["b"], r["id"]))
            self.adj[r["b"]].append((r["a"], r["id"]))
        self.weather = self.db.weather_map()
        self.events = {}
        for e in self.db.active_events():
            cur = self.events.get(e["road_id"])
            if cur is None or e["severity"] > cur["severity"] or e["kind"] == "перекрытие":
                self.events[e["road_id"]] = e
        self.cargo = self.db.cargo_map()
        s = self.db.setting
        self.fuel_price = s("fuel_price")
        self.driver_rate = s("driver_rate")
        self.vehicle_rate = s("vehicle_rate")
        self.platon = s("platon_rub_km")
        self.border_delay = s("border_delay_h")
        self.weights = (s("w_cost"), s("w_time"), s("w_risk"))
        self._cache = {}

    def edge_weather(self, road):
        wa = self.weather.get(self.nodes[road["a"]]["region"], "ясно")
        wb = self.weather.get(self.nodes[road["b"]]["region"], "ясно")
        return wa if WEATHER_RANK.get(wa, 0) >= WEATHER_RANK.get(wb, 0) else wb

    def is_closed(self, road_id):
        e = self.events.get(road_id)
        return bool(e and e["kind"] == "перекрытие" and e["severity"] >= 1.0)

    def congestion(self, road_id, when):
        key = (road_id, when.weekday(), when.hour)
        if key in self._cache:
            return self._cache[key]
        road = self.road_rows[road_id]
        wx = self.edge_weather(road)
        c = self.model.predict(road, when.weekday(), when.hour, wx, 0)
        self._cache[key] = c
        return c

    def edge(self, road_id, when, profile, cargo_code, load_t):
        road = self.road_rows[road_id]
        wx = self.edge_weather(road)
        c = self.congestion(road_id, when)
        q = road["quality"]
        d = road["distance_km"]
        speed = BASE_SPEED[road["category"]] * (0.62 + 0.38 * q) * WEATHER_SPEED.get(wx, 1.0) / (1 + (c - 1) * 0.55)
        drive_h = d / max(speed, 5.0)
        e = self.events.get(road_id)
        event_h = 0.0
        if e and e["kind"] != "перекрытие":
            event_h = EVENT_DELAY.get(e["kind"], 1.0) * e["severity"]
            drive_h += event_h
        cap = profile["capacity_t"]
        load_ratio = min(1.0, load_t / cap) if cap else 0.0
        fuel_l = d / 100.0 * profile["fuel_l_100"] * (0.72 + 0.28 * load_ratio) * (1 + 0.32 * (c - 1)) * (1 + 0.18 * (1 - q)) * WEATHER_FUEL.get(wx, 1.0)
        toll = d * road["toll_rub_km"]
        if self.nodes[road["a"]]["country"] == "RU" and self.nodes[road["b"]]["country"] == "RU" and road["category"] == "федеральная" and cap >= 12:
            toll += d * self.platon
        loss = 0.0
        if cargo_code and load_t > 0:
            cg = self.cargo[cargo_code]
            rate = cg["loss_base"] * d / 100.0 * (1 + cg["road_sensitivity"] * (1 - q) * 2.0) * (1 + cg["weather_sensitivity"] * WEATHER_RISK.get(wx, 0.0)) * (1 + 0.25 * (c - 1))
            if event_h:
                rate += cg["loss_base"] * cg["road_sensitivity"] * 0.5
            loss = min(rate, 0.25) * load_t * cg["price_rub_t"]
        border_h = self.border_delay if road["border"] else 0.0
        return {
            "road_id": road_id,
            "road": road["name"],
            "category": road["category"],
            "km": d,
            "drive_h": drive_h,
            "border_h": border_h,
            "speed": speed,
            "congestion": c,
            "weather": wx,
            "quality": q,
            "fuel_l": fuel_l,
            "fuel_rub": fuel_l * self.fuel_price,
            "toll_rub": toll,
            "time_rub": (drive_h + border_h) * (self.driver_rate + self.vehicle_rate),
            "loss_rub": loss,
            "event": f"{e['kind']}: {e['description']}" if e else "",
            "event_h": event_h,
            "closed": self.is_closed(road_id),
        }

    def gen(self, seg, weights=None):
        wc, wt, wr = weights or self.weights
        return wc * (seg["fuel_rub"] + seg["toll_rub"]) + wt * seg["time_rub"] + wr * seg["loss_rub"]

    def profile_for(self, vehicle=None, body="тент"):
        if vehicle is not None:
            return {"capacity_t": vehicle["capacity_t"], "fuel_l_100": vehicle["fuel_l_100"], "body": vehicle["body"]}
        p = dict(DEFAULT_PROFILE.get(body, DEFAULT_PROFILE["тент"]))
        p["body"] = body
        return p

    def shortest(self, src, dst, departure, profile, cargo_code, load_t, weights=None, banned_edges=(), banned_nodes=(), mode="smart"):
        if src == dst:
            return [src], []
        counter = itertools.count()
        best = {src: 0.0}
        heap = [(0.0, next(counter), src, 0.0, [src], [])]
        done = set()
        while heap:
            cost, _, node, clock, path, roads = heapq.heappop(heap)
            if node in done:
                continue
            done.add(node)
            if node == dst:
                return path, roads
            for nxt, rid in self.adj[node]:
                if nxt in done or rid in banned_edges or nxt in banned_nodes:
                    continue
                if mode == "distance":
                    step = self.road_rows[rid]["distance_km"]
                    dt = 0.0
                else:
                    if self.is_closed(rid):
                        continue
                    seg = self.edge(rid, departure + timedelta(hours=clock), profile, cargo_code, load_t)
                    step = self.gen(seg, weights)
                    dt = seg["drive_h"] + seg["border_h"]
                nc = cost + step
                if nc < best.get(nxt, float("inf")) - 1e-9:
                    best[nxt] = nc
                    heapq.heappush(heap, (nc, next(counter), nxt, clock + dt, path + [nxt], roads + [rid]))
        return None, None

    def evaluate(self, nodes, roads, departure, profile, cargo_code, load_t, weights=None):
        res = RouteResult()
        res.nodes = list(nodes)
        res.roads = list(roads)
        res.departure = departure
        clock = 0.0
        since_break = 0.0
        day_drive = 0.0
        for i, rid in enumerate(roads):
            seg = self.edge(rid, departure + timedelta(hours=clock), profile, cargo_code, load_t)
            seg["from"] = nodes[i]
            seg["to"] = nodes[i + 1]
            seg["start_h"] = clock
            if seg["closed"]:
                res.closed = True
                seg["border_h"] += 10.0
                seg["time_rub"] += 10.0 * (self.driver_rate + self.vehicle_rate)
            res.segments.append(seg)
            res.km += seg["km"]
            res.drive_h += seg["drive_h"]
            res.border_h += seg["border_h"]
            res.fuel_l += seg["fuel_l"]
            res.fuel_rub += seg["fuel_rub"]
            res.toll_rub += seg["toll_rub"]
            res.time_rub += seg["time_rub"]
            res.loss_rub += seg["loss_rub"]
            res.gen_cost += self.gen(seg, weights)
            clock += seg["drive_h"] + seg["border_h"]
            since_break += seg["drive_h"]
            day_drive += seg["drive_h"]
            while since_break >= 4.5:
                since_break -= 4.5
                res.rest_h += 0.75
                clock += 0.75
            while day_drive >= 9.0:
                day_drive -= 9.0
                res.rest_h += 10.25
                clock += 10.25
                since_break = 0.0
        rest_rub = res.rest_h * self.vehicle_rate * 0.5
        res.time_rub += rest_rub
        res.gen_cost += (weights or self.weights)[1] * rest_rub
        res.arrival = departure + timedelta(hours=res.total_h)
        return res

    def k_routes(self, src, dst, departure, profile, cargo_code, load_t, k=3, weights=None):
        first_nodes, first_roads = self.shortest(src, dst, departure, profile, cargo_code, load_t, weights)
        if first_nodes is None:
            return []
        found = [(first_nodes, first_roads)]
        candidates = []
        seen = {tuple(first_roads)}
        while len(found) < k:
            last_nodes, last_roads = found[-1]
            for i in range(len(last_nodes) - 1):
                spur = last_nodes[i]
                root_nodes = last_nodes[: i + 1]
                root_roads = last_roads[:i]
                banned_e = set()
                for pn, pr in found:
                    if pr[:i] == root_roads and len(pr) > i:
                        banned_e.add(pr[i])
                banned_n = set(root_nodes[:-1])
                root_eval = self.evaluate(root_nodes, root_roads, departure, profile, cargo_code, load_t, weights) if root_roads else None
                t0 = departure + timedelta(hours=root_eval.total_h) if root_eval else departure
                sn, sr = self.shortest(spur, dst, t0, profile, cargo_code, load_t, weights, banned_e, banned_n)
                if sn is None:
                    continue
                total_nodes = root_nodes[:-1] + sn
                total_roads = root_roads + sr
                key = tuple(total_roads)
                if key in seen:
                    continue
                seen.add(key)
                ev = self.evaluate(total_nodes, total_roads, departure, profile, cargo_code, load_t, weights)
                heapq.heappush(candidates, (ev.gen_cost, len(seen), total_nodes, total_roads))
            if not candidates:
                break
            _, _, n, r = heapq.heappop(candidates)
            found.append((n, r))
        bn, br = self.shortest(src, dst, departure, profile, cargo_code, load_t, mode="distance")
        if bn is not None and tuple(br) not in seen:
            alt = self.evaluate(bn, br, departure, profile, cargo_code, load_t, weights)
            worst = max(self.evaluate(n, r, departure, profile, cargo_code, load_t, weights).gen_cost for n, r in found)
            if not alt.closed and (alt.gen_cost < worst or len(found) < k):
                if len(found) >= k:
                    found.sort(key=lambda nr: self.evaluate(nr[0], nr[1], departure, profile, cargo_code, load_t, weights).gen_cost)
                    found[-1] = (bn, br)
                else:
                    found.append((bn, br))
        results = [self.evaluate(n, r, departure, profile, cargo_code, load_t, weights) for n, r in found]
        results.sort(key=lambda x: x.gen_cost)
        for i, r in enumerate(results):
            r.label = "Рекомендуемый ИИ" if i == 0 else f"Альтернатива {i}"
        return results

    def best_route(self, src, dst, departure, profile, cargo_code, load_t, weights=None):
        n, r = self.shortest(src, dst, departure, profile, cargo_code, load_t, weights)
        if n is None:
            return None
        res = self.evaluate(n, r, departure, profile, cargo_code, load_t, weights)
        bn, br = self.shortest(src, dst, departure, profile, cargo_code, load_t, mode="distance")
        if bn is not None and br != r:
            alt = self.evaluate(bn, br, departure, profile, cargo_code, load_t, weights)
            if not alt.closed and alt.gen_cost < res.gen_cost:
                return alt
        return res

    def baseline_route(self, src, dst, departure, profile, cargo_code, load_t):
        n, r = self.shortest(src, dst, departure, profile, cargo_code, load_t, mode="distance")
        if n is None:
            return None
        res = self.evaluate(n, r, departure, profile, cargo_code, load_t)
        res.label = "Традиционный (кратчайший)"
        return res

    def route_name(self, nodes):
        return " → ".join(self.nodes[n]["name"].split(" (")[0] for n in nodes)


def next_departure(hour=8):
    now = datetime.now()
    d = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if d < now:
        d += timedelta(days=1)
    return d
