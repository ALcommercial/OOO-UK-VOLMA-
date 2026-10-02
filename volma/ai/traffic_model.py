import json
import math
import random

WEATHERS = ["дождь", "туман", "снег", "гололёд"]

FEATURE_NAMES = [
    "Смещение",
    "Доля городских участков",
    "Утренний пик × город",
    "Вечерний пик × город",
    "Утренний пик",
    "Вечерний пик",
    "Ночь",
    "Выходной",
    "Выходной × город",
    "Пятница",
    "Дождь",
    "Туман",
    "Снег",
    "Гололёд",
    "Дорожное событие",
    "Плохое покрытие",
    "Федеральная трасса",
]


def features(road, weekday, hour, weather, event):
    urban = road["urban"]
    morning = math.exp(-((hour - 8) ** 2) / 4.0)
    evening = math.exp(-((hour - 18) ** 2) / 5.0)
    night = 1.0 if hour < 5 or hour >= 23 else 0.0
    weekend = 1.0 if weekday >= 5 else 0.0
    friday = 1.0 if weekday == 4 else 0.0
    fed = 1.0 if road["category"] == "федеральная" else 0.0
    x = [1.0, urban, urban * morning, urban * evening, morning, evening, night, weekend, weekend * urban, friday]
    x += [1.0 if weather == w else 0.0 for w in WEATHERS]
    x += [float(event), 1.0 - road["quality"], fed]
    return x


def solve(a, b):
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        p = m[col][col]
        if abs(p) < 1e-12:
            continue
        for j in range(col, n + 1):
            m[col][j] /= p
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col]
                for j in range(col, n + 1):
                    m[r][j] -= f * m[col][j]
    return [m[i][n] for i in range(n)]


class TrafficModel:
    def __init__(self, db):
        self.db = db
        self.coef = None
        self.metrics = {}
        self.load()

    def load(self):
        raw = self.db.scalar("SELECT value FROM model_meta WHERE key='traffic_model'")
        if raw:
            data = json.loads(raw)
            if len(data.get("coef", [])) == len(FEATURE_NAMES):
                self.coef = data["coef"]
                self.metrics = data.get("metrics", {})
                return
        self.train()

    def train(self, ridge=0.5):
        roads = {r["id"]: r for r in self.db.roads()}
        rows = self.db.q("SELECT road_id, weekday, hour, weather, event, congestion FROM traffic_history")
        data = [(features(roads[r["road_id"]], r["weekday"], r["hour"], r["weather"], r["event"]), r["congestion"]) for r in rows if r["road_id"] in roads]
        rng = random.Random(7)
        rng.shuffle(data)
        split = int(len(data) * 0.8)
        train, test = data[:split], data[split:]
        n = len(FEATURE_NAMES)
        xtx = [[0.0] * n for _ in range(n)]
        xty = [0.0] * n
        for x, y in train:
            for i in range(n):
                xi = x[i]
                if xi == 0.0:
                    continue
                xty[i] += xi * y
                row = xtx[i]
                for j in range(n):
                    row[j] += xi * x[j]
        for i in range(1, n):
            xtx[i][i] += ridge
        self.coef = solve(xtx, xty)
        mean_y = sum(y for _, y in test) / max(1, len(test))
        ss_res = sum((self._dot(x) - y) ** 2 for x, y in test)
        ss_tot = sum((y - mean_y) ** 2 for _, y in test) or 1.0
        mae = sum(abs(self._dot(x) - y) for x, y in test) / max(1, len(test))
        mape = sum(abs(self._dot(x) - y) / y for x, y in test) / max(1, len(test))
        self.metrics = {
            "r2": 1 - ss_res / ss_tot,
            "mae": mae,
            "mape": mape,
            "n_train": len(train),
            "n_test": len(test),
        }
        self.db.run(
            "INSERT OR REPLACE INTO model_meta(key, value) VALUES ('traffic_model', ?)",
            (json.dumps({"coef": self.coef, "metrics": self.metrics}),),
        )
        return self.metrics

    def _dot(self, x):
        return sum(c * v for c, v in zip(self.coef, x))

    def predict(self, road, weekday, hour, weather, event=0):
        return max(1.0, min(4.0, self._dot(features(road, weekday, int(hour) % 24, weather, event))))

    def importance(self):
        return list(zip(FEATURE_NAMES[1:], self.coef[1:]))
