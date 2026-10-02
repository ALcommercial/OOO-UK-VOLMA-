import heapq
import itertools
import json
import math
from datetime import datetime, timedelta

LOAD_H = 1.5
UNLOAD_H = 1.0
HORIZON_H = 96.0
MAX_LOADS = 4


class Load:
    _ids = itertools.count(1)

    def __init__(self, origin, body):
        self.id = next(Load._ids)
        self.origin = origin
        self.body = body
        self.items = []
        self.stops = []

    @property
    def weight(self):
        return sum(w for _, w, _ in self.items)

    @property
    def priority(self):
        return min(p["priority"] for p, _, _ in self.items)

    @property
    def due(self):
        return min(p["due"] for p, _, _ in self.items)

    def cargo_code(self, cargo_map):
        codes = {p["cargo"] for p, _, _ in self.items}
        return max(codes, key=lambda c: cargo_map[c]["loss_base"] * cargo_map[c]["price_rub_t"])


class Dispatcher:
    def __init__(self, db, net):
        self.db = db
        self.net = net
        self._dist = {}
        self._matrix = {}

    def dist(self, a, b):
        key = (a, b) if a < b else (b, a)
        if key not in self._dist:
            if a == b:
                self._dist[key] = 0.0
            else:
                n, r = self.net.shortest(a, b, datetime.now(), self.net.profile_for(None), None, 0, mode="distance")
                self._dist[key] = sum(self.net.road_rows[x]["distance_km"] for x in r) if r is not None else 1e9
        return self._dist[key]

    def matrix(self, body, departure):
        if body in self._matrix:
            return self._matrix[body]
        prof = self.net.profile_for(None, body)
        out = {}
        for src in self.net.nodes:
            out[src] = self._tree(src, departure, prof)
        self._matrix[body] = out
        return out

    def _tree(self, src, departure, profile):
        counter = itertools.count()
        best = {src: (0.0, 0.0)}
        heap = [(0.0, next(counter), src, 0.0)]
        done = set()
        while heap:
            cost, _, node, clock = heapq.heappop(heap)
            if node in done:
                continue
            done.add(node)
            best[node] = (cost, clock)
            for nxt, rid in self.net.adj[node]:
                if nxt in done or self.net.is_closed(rid):
                    continue
                seg = self.net.edge(rid, departure + timedelta(hours=clock), profile, None, 0)
                heapq.heappush(heap, (cost + self.net.gen(seg), next(counter), nxt, clock + seg["drive_h"] + seg["border_h"]))
        return best

    def pieces(self, orders, max_cap):
        out = []
        for o in orders:
            cg = self.net.cargo[o["cargo"]]
            body = cg["body"]
            cap = max_cap.get(body, 20.0)
            w = o["weight_t"]
            n = max(1, math.ceil(w / cap - 1e-9))
            part = w / n
            for _ in range(n):
                out.append({
                    "order_id": o["id"],
                    "origin": o["origin"],
                    "dest": o["destination"],
                    "cargo": o["cargo"],
                    "body": body,
                    "weight": part,
                    "priority": o["priority"],
                    "due": datetime.strptime(o["due_date"], "%Y-%m-%d") + timedelta(hours=20),
                })
        return out

    def consolidate(self, pieces, max_cap):
        groups = {}
        for p in pieces:
            groups.setdefault((p["origin"], p["body"]), []).append(p)
        loads = []
        merges = 0
        for (origin, body), items in groups.items():
            cap = max_cap.get(body, 20.0)
            items.sort(key=lambda p: -p["weight"])
            group_loads = []
            for p in items:
                placed = False
                for ld in group_loads:
                    if ld.weight + p["weight"] > cap + 1e-6:
                        continue
                    if p["dest"] in ld.stops:
                        ld.items.append((p, p["weight"], p["dest"]))
                        placed = True
                        merges += 1
                        break
                    if len(ld.stops) >= 2 or body != "тент":
                        continue
                    a = ld.stops[0]
                    b = p["dest"]
                    da, db_, dab = self.dist(origin, a), self.dist(origin, b), self.dist(a, b)
                    first, second = (a, b) if da <= db_ else (b, a)
                    combined = min(da, db_) + dab
                    direct = max(da, db_)
                    if dab <= 450 and combined <= direct * 1.25 + 60:
                        ld.items.append((p, p["weight"], b))
                        ld.stops = [first, second]
                        placed = True
                        merges += 1
                        break
                if not placed:
                    ld = Load(origin, body)
                    ld.items.append((p, p["weight"], p["dest"]))
                    ld.stops = [p["dest"]]
                    group_loads.append(ld)
            loads.extend(group_loads)
        return loads, merges

    def plan(self, departure=None):
        self.net.refresh()
        self._matrix = {}
        departure = departure or datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        orders = self.db.q("SELECT * FROM orders WHERE status='новый' ORDER BY priority, due_date")
        vehicles = [dict(v) for v in self.db.q("SELECT * FROM vehicles WHERE status='свободна'")]
        all_vehicles = self.db.q("SELECT body, MAX(capacity_t) AS cap FROM vehicles GROUP BY body")
        max_cap = {r["body"]: r["cap"] for r in all_vehicles}
        late_pen = self.db.setting("late_penalty_rub_h")
        result = {"departure": departure, "chains": [], "unassigned": [], "merges": 0, "n_orders": len(orders)}
        if not orders:
            return result
        pieces = self.pieces(orders, max_cap)
        loads, merges = self.consolidate(pieces, max_cap)
        result["merges"] = merges
        result["n_loads_initial"] = len(pieces)
        load_route = {}
        for ld in loads:
            load_route[ld.id] = self.loaded_eval(ld, departure, None)
        state = {}
        for v in vehicles:
            state[v["id"]] = {"veh": v, "loc": v["location_node"], "clock": 0.0, "loads": []}
        mats = {b: self.matrix(b, departure) for b in {ld.body for ld in loads}}
        pending = list(loads)
        while pending:
            best_pick = None
            for ld in pending:
                lr = load_route[ld.id]
                if lr is None:
                    continue
                opts = []
                for vid, st in state.items():
                    v = st["veh"]
                    if v["body"] != ld.body or len(st["loads"]) >= MAX_LOADS or st["clock"] > HORIZON_H:
                        continue
                    m = mats[ld.body]
                    e_cost, e_h = m[st["loc"]].get(ld.origin, (1e9, 1e9))
                    last = ld.stops[-1]
                    base = v["base_node"]
                    ret_new = m[last].get(base, (1e9, 0))[0]
                    ret_old = m[st["loc"]].get(base, (1e9, 0))[0]
                    arrive = st["clock"] + e_h + LOAD_H + lr.total_h + UNLOAD_H * len(ld.stops)
                    late_h = max(0.0, (departure + timedelta(hours=arrive) - ld.due).total_seconds() / 3600)
                    cap_ratio = min(1.0, ld.weight / v["capacity_t"])
                    marginal = e_cost + lr.gen_cost + ret_new - ret_old + late_h * late_pen + (1 - cap_ratio) * 1500
                    if v["capacity_t"] + 1e-6 < ld.weight:
                        marginal = marginal * ld.weight / v["capacity_t"] + 800
                    opts.append((marginal, vid))
                if not opts:
                    continue
                opts.sort()
                regret = (opts[1][0] - opts[0][0]) if len(opts) > 1 else 1e7
                regret *= {1: 1.6, 2: 1.0, 3: 0.7}.get(ld.priority, 1.0)
                if best_pick is None or regret > best_pick[0]:
                    best_pick = (regret, ld, opts[0][1])
            if best_pick is None:
                break
            _, ld, vid = best_pick
            st = state[vid]
            v = st["veh"]
            if ld.weight > v["capacity_t"] + 1e-6:
                rest = self.split(ld, v["capacity_t"])
                pending.append(rest)
                load_route[rest.id] = self.loaded_eval(rest, departure, None)
                load_route[ld.id] = self.loaded_eval(ld, departure, None)
            m = mats[ld.body]
            e_h = m[st["loc"]].get(ld.origin, (0, 0))[1]
            st["clock"] += e_h + LOAD_H + load_route[ld.id].total_h + UNLOAD_H * len(ld.stops)
            st["loc"] = ld.stops[-1]
            st["loads"].append(ld)
            pending.remove(ld)
        for ld in pending:
            result["unassigned"].append(ld)
        result["improvements"] = self.improve(state, mats, load_route)
        for vid, st in state.items():
            if st["loads"]:
                result["chains"].append(self.build_chain(st["veh"], st["loads"], departure))
        base = self.baseline(orders, max_cap, departure)
        result["baseline"] = base
        self.attach_baseline(result)
        return result

    def chain_cost(self, st, loads, mats, load_route):
        v = st["veh"]
        if not loads:
            return 0.0, 0.0
        loc = v["location_node"]
        cost = 0.0
        clock = 0.0
        for ld in loads:
            if v["capacity_t"] + 1e-6 < ld.weight or v["body"] != ld.body:
                return 1e12, 1e12
            c, h = mats[ld.body][loc].get(ld.origin, (1e9, 1e9))
            cost += c + load_route[ld.id].gen_cost
            clock += h + LOAD_H + load_route[ld.id].total_h + UNLOAD_H * len(ld.stops)
            loc = ld.stops[-1]
        cost += mats[v["body"]][loc].get(v["base_node"], (1e9, 0))[0]
        if clock > HORIZON_H + 48:
            cost += (clock - HORIZON_H - 48) * 2000
        return cost, clock

    def improve(self, state, mats, load_route, rounds=6):
        moves = 0
        vids = list(state)
        costs = {vid: self.chain_cost(state[vid], state[vid]["loads"], mats, load_route)[0] for vid in vids}
        for _ in range(rounds):
            changed = False
            for a in vids:
                for ld in list(state[a]["loads"]):
                    rest_a = [x for x in state[a]["loads"] if x is not ld]
                    ca = self.chain_cost(state[a], rest_a, mats, load_route)[0]
                    best = None
                    for b in vids:
                        if b == a or state[b]["veh"]["body"] != ld.body or state[b]["veh"]["capacity_t"] + 1e-6 < ld.weight or len(state[b]["loads"]) >= MAX_LOADS:
                            continue
                        lb = state[b]["loads"]
                        for pos in range(len(lb) + 1):
                            cand = lb[:pos] + [ld] + lb[pos:]
                            cb = self.chain_cost(state[b], cand, mats, load_route)[0]
                            gain = costs[a] + costs[b] - ca - cb
                            if gain > 50 and (best is None or gain > best[0]):
                                best = (gain, b, cand, ca, cb)
                    for pos in range(len(rest_a) + 1):
                        cand = rest_a[:pos] + [ld] + rest_a[pos:]
                        if cand == state[a]["loads"]:
                            continue
                        cc = self.chain_cost(state[a], cand, mats, load_route)[0]
                        gain = costs[a] - cc
                        if gain > 50 and (best is None or gain > best[0]):
                            best = (gain, a, cand, None, cc)
                    if best:
                        gain, b, cand, ca2, cb = best
                        if b == a:
                            state[a]["loads"] = cand
                            costs[a] = cb
                        else:
                            state[a]["loads"] = rest_a
                            state[b]["loads"] = cand
                            costs[a] = ca2
                            costs[b] = cb
                        moves += 1
                        changed = True
            if not changed:
                break
        return moves

    def split(self, ld, cap):
        rest = Load(ld.origin, ld.body)
        keep = []
        acc = 0.0
        for p, w, d in sorted(ld.items, key=lambda t: -t[1]):
            if acc + w <= cap + 1e-6:
                keep.append((p, w, d))
                acc += w
            elif acc < cap - 1e-6:
                part = cap - acc
                keep.append((p, part, d))
                rest.items.append((p, w - part, d))
                acc = cap
            else:
                rest.items.append((p, w, d))
        ld.items = keep
        ld.stops = [s for s in ld.stops if any(d == s for _, _, d in keep)]
        rest.stops = [s for s in ld.stops + [d for _, _, d in rest.items] if any(d == s for _, _, d in rest.items)]
        rest.stops = list(dict.fromkeys(rest.stops))
        return rest

    def loaded_eval(self, ld, departure, vehicle):
        prof = self.net.profile_for(vehicle, ld.body)
        cargo = ld.cargo_code(self.net.cargo)
        cur = ld.origin
        total = None
        t = departure
        remaining = ld.weight
        for stop in ld.stops:
            r = self.net.best_route(cur, stop, t, prof, cargo, remaining)
            if r is None:
                return None
            total = r if total is None else merge_routes(total, r)
            t = t + timedelta(hours=r.total_h + UNLOAD_H)
            remaining -= sum(w for _, w, d in ld.items if d == stop)
            cur = stop
        return total

    def build_chain(self, v, loads, departure):
        prof = self.net.profile_for(v)
        legs = []
        t = departure
        loc = v["location_node"]
        for ld in loads:
            if loc != ld.origin:
                r = self.net.best_route(loc, ld.origin, t, prof, None, 0)
                legs.append(("empty", r, None))
                t += timedelta(hours=r.total_h)
            t += timedelta(hours=LOAD_H)
            cur = ld.origin
            remaining = ld.weight
            cargo = ld.cargo_code(self.net.cargo)
            for stop in ld.stops:
                r = self.net.best_route(cur, stop, t, prof, cargo, remaining)
                legs.append(("loaded", r, ld))
                t += timedelta(hours=r.total_h + UNLOAD_H)
                remaining -= sum(w for _, w, d in ld.items if d == stop)
                cur = stop
            loc = ld.stops[-1]
        if loc != v["base_node"]:
            r = self.net.best_route(loc, v["base_node"], t, prof, None, 0)
            if r is not None:
                legs.append(("return", r, None))
                t += timedelta(hours=r.total_h)
        km = sum(r.km for _, r, _ in legs)
        empty_km = sum(r.km for k, r, _ in legs if k != "loaded")
        return {
            "vehicle": v,
            "loads": loads,
            "legs": legs,
            "km": km,
            "empty_km": empty_km,
            "hours": (t - departure).total_seconds() / 3600,
            "fuel_l": sum(r.fuel_l for _, r, _ in legs),
            "cost": sum(r.total_rub for _, r, _ in legs),
            "loss": sum(r.loss_rub for _, r, _ in legs),
            "tonnage": sum(ld.weight for ld in loads),
            "closed": any(r.closed for _, r, _ in legs),
        }

    def baseline(self, orders, max_cap, departure):
        bases = {}
        for v in self.db.q("SELECT * FROM vehicles"):
            bases.setdefault(v["body"], {}).setdefault(v["base_node"], v)
        per_order = {}
        tot = {"cost": 0.0, "km": 0.0, "empty_km": 0.0, "loss": 0.0, "fuel_l": 0.0, "trips": 0, "closed": 0}
        for o in orders:
            cg = self.net.cargo[o["cargo"]]
            body = cg["body"]
            cands = bases.get(body, {})
            if not cands:
                continue
            if o["origin"] in cands:
                v = cands[o["origin"]]
            else:
                bnode = min(cands, key=lambda b: self.dist(b, o["origin"]))
                v = cands[bnode]
            prof = self.net.profile_for(v)
            n = max(1, math.ceil(o["weight_t"] / v["capacity_t"] - 1e-9))
            w = o["weight_t"] / n
            legs = []
            t = departure
            plan_legs = []
            if v["base_node"] != o["origin"]:
                plan_legs.append((v["base_node"], o["origin"], None, 0, False))
            plan_legs.append((o["origin"], o["destination"], o["cargo"], w, True))
            plan_legs.append((o["destination"], v["base_node"], None, 0, False))
            for a, b, cg_code, lw, loaded in plan_legs:
                if a == b:
                    continue
                r = self.net.baseline_route(a, b, t, prof, cg_code, lw)
                legs.append((r, loaded))
                if r:
                    t += timedelta(hours=r.total_h + (LOAD_H if loaded else 0) + (UNLOAD_H if loaded else 0))
            c = sum(r.total_rub for r, _ in legs if r) * n
            km = sum(r.km for r, _ in legs if r) * n
            ekm = sum(r.km for r, l in legs if r and not l) * n
            loss = sum(r.loss_rub for r, _ in legs if r) * n
            fuel = sum(r.fuel_l for r, _ in legs if r) * n
            closed = any(r.closed for r, _ in legs if r)
            per_order[o["id"]] = {"cost": c, "km": km, "empty_km": ekm, "loss": loss, "fuel_l": fuel, "weight": o["weight_t"]}
            tot["cost"] += c
            tot["km"] += km
            tot["empty_km"] += ekm
            tot["loss"] += loss
            tot["fuel_l"] += fuel
            tot["trips"] += n
            tot["closed"] += 1 if closed else 0
        tot["per_order"] = per_order
        return tot

    def attach_baseline(self, result):
        per = result["baseline"]["per_order"]
        for ch in result["chains"]:
            bc = be = bf = 0.0
            for ld in ch["loads"]:
                for p, w, _ in ld.items:
                    b = per.get(p["order_id"])
                    if b:
                        share = w / b["weight"] if b["weight"] else 0
                        bc += b["cost"] * share
                        be += b["empty_km"] * share
                        bf += b["fuel_l"] * share
            ch["baseline_cost"] = bc
            ch["baseline_fuel"] = bf
            ch["baseline_empty_km"] = be
        served = set()
        for ch in result["chains"]:
            for ld in ch["loads"]:
                for p, _, _ in ld.items:
                    served.add(p["order_id"])
        opt = {
            "cost": sum(c["cost"] for c in result["chains"]),
            "km": sum(c["km"] for c in result["chains"]),
            "empty_km": sum(c["empty_km"] for c in result["chains"]),
            "loss": sum(c["loss"] for c in result["chains"]),
            "fuel_l": sum(c["fuel_l"] for c in result["chains"]),
            "trips": len(result["chains"]),
            "loads": sum(len(c["loads"]) for c in result["chains"]),
        }
        base_served = {k: 0.0 for k in ("cost", "km", "empty_km", "loss", "fuel_l")}
        for oid in served:
            b = per.get(oid)
            if b:
                for k in base_served:
                    base_served[k] += b[k]
        result["optimized"] = opt
        result["baseline_served"] = base_served
        result["served_orders"] = served

    def commit(self, result):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ids = []
        for ch in result["chains"]:
            nodes = []
            roads = []
            legs_json = []
            for kind, r, ld in ch["legs"]:
                if nodes and nodes[-1] == r.nodes[0]:
                    nodes.extend(r.nodes[1:])
                else:
                    nodes.extend(r.nodes)
                roads.extend(r.roads)
                legs_json.append({
                    "kind": kind,
                    "from": r.nodes[0],
                    "to": r.nodes[-1],
                    "nodes": r.nodes,
                    "roads": r.roads,
                    "km": round(r.km, 1),
                    "hours": round(r.total_h, 2),
                    "cost": round(r.total_rub, 0),
                    "loss": round(r.loss_rub, 0),
                    "load_t": round(ld.weight, 2) if ld else 0,
                    "orders": sorted({p["order_id"] for p, _, _ in ld.items}) if ld else [],
                })
            tid = self.db.run(
                "INSERT INTO trips(created_at,vehicle_id,route_nodes,route_roads,distance_km,empty_km,duration_h,fuel_l,cost_rub,loss_rub,baseline_cost_rub,baseline_empty_km,baseline_fuel_l,load_t,status,legs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (now, ch["vehicle"]["id"], json.dumps(nodes), json.dumps(roads), round(ch["km"], 1), round(ch["empty_km"], 1), round(ch["hours"], 2), round(ch["fuel_l"], 1),
                 round(ch["cost"], 0), round(ch["loss"], 0), round(ch["baseline_cost"], 0), round(ch["baseline_empty_km"], 1), round(ch["baseline_fuel"], 1), round(ch["tonnage"], 2), "запланирован", json.dumps(legs_json)),
            )
            ids.append(tid)
            ch["trip_id"] = tid
            self.db.conn.execute("UPDATE vehicles SET status='назначена' WHERE id=?", (ch["vehicle"]["id"],))
        served = {}
        for ch in result["chains"]:
            for ld in ch["loads"]:
                for p, w, _ in ld.items:
                    rec = served.setdefault(p["order_id"], {"w": 0.0, "trips": []})
                    rec["w"] += w
                    rec["trips"].append(ch["trip_id"])
        for oid, rec in served.items():
            o = self.db.one("SELECT * FROM orders WHERE id=?", (oid,))
            trips = list(dict.fromkeys(rec["trips"]))
            served_w = round(rec["w"], 2)
            remainder = round(o["weight_t"] - served_w, 2)
            if remainder > 0.05:
                self.db.conn.execute(
                    "INSERT INTO orders(created_at,origin,destination,cargo,weight_t,due_date,priority,status) VALUES (?,?,?,?,?,?,?, 'новый')",
                    (o["created_at"], o["origin"], o["destination"], o["cargo"], remainder, o["due_date"], o["priority"]),
                )
                self.db.conn.execute("UPDATE orders SET weight_t=? WHERE id=?", (served_w, oid))
            self.db.conn.execute("UPDATE orders SET status='запланирован', trip_id=? WHERE id=?", (trips[0], oid))
        self.db.conn.commit()
        return ids


def merge_routes(a, b):
    a.nodes = a.nodes + b.nodes[1:]
    a.roads = a.roads + b.roads
    a.segments = a.segments + b.segments
    for k in ("km", "drive_h", "rest_h", "border_h", "fuel_l", "fuel_rub", "toll_rub", "time_rub", "loss_rub", "gen_cost"):
        setattr(a, k, getattr(a, k) + getattr(b, k))
    a.closed = a.closed or b.closed
    a.arrival = b.arrival
    return a
