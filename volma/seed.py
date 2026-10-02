import math
import random
from datetime import datetime, timedelta

from .geo import haversine

PLANTS = [
    ("VLG", "ВОЛМА-Волгоград", "Волгоградская обл.", "RU", 48.786, 44.585, "г. Волгоград, ул. Крепильная, 128", 1800, 5200, "ГКЛ, ПГП, сухие смеси"),
    ("VTR", "ВОЛМА-ВТР", "Волгоградская обл.", "RU", 48.540, 44.520, "г. Волгоград, ул. Шкирятова, 29", 1200, 3100, "сухие смеси, цемент"),
    ("VSK", "ВОЛМА-Воскресенск", "Московская обл.", "RU", 55.322, 38.680, "г. Воскресенск, ул. Кирова, 3", 1500, 4100, "ГКЛ, сухие смеси"),
    ("CHL", "ВОЛМА-Челябинск", "Челябинская обл.", "RU", 55.205, 61.470, "г. Челябинск, ул. Героев Танкограда, 67П", 1300, 3600, "ГКЛ, сухие смеси"),
    ("ORB", "ВОЛМА-Оренбург", "Оренбургская обл.", "RU", 51.460, 56.420, "п. Дубенский, ул. Заводская, 1", 1100, 2900, "сухие смеси, ПГП"),
    ("ABS", "ВОЛМА-Абсалямово", "Республика Татарстан", "RU", 54.905, 52.590, "с. Абсалямово, ул. Советская, 120", 1400, 3800, "ГКЛ, сухие смеси, ПГП"),
    ("MKP", "ВОЛМА-Майкоп", "Республика Адыгея", "RU", 44.300, 40.180, "п. Каменномостский, ул. К. Маркса, 66", 1600, 4400, "ГКЛ, сухие смеси"),
    ("BKL", "ВОЛМА-Байкал", "Иркутская обл.", "RU", 52.540, 103.890, "г. Ангарск", 900, 2300, "ГКЛ, сухие смеси"),
    ("IND", "ИндерГипс", "Атырауская обл.", "KZ", 48.550, 51.780, "п. Индерборский", 1000, 2700, "гипсовый вяжущий, сухие смеси"),
]

DEPOSITS = [
    ("D_ABS", "Месторождение гипса «Абсалямовское»", "Республика Татарстан", "RU", 54.860, 52.700, "Альметьевский р-н", 3500, 42000, "гипсовый камень"),
    ("D_DUB", "Месторождение гипса «Дубенское»", "Оренбургская обл.", "RU", 51.380, 56.520, "Беляевский р-н", 3000, 36000, "гипсовый камень"),
    ("D_KMM", "Месторождение гипса «Каменномостское»", "Республика Адыгея", "RU", 44.250, 40.230, "Майкопский р-н", 3200, 39000, "гипсовый камень"),
    ("D_IND", "Месторождение гипса «Индерское»", "Атырауская обл.", "KZ", 48.640, 51.880, "Индерский р-н", 2800, 33000, "гипсовый камень"),
]

HUBS = [
    ("MSK", "Москва (РЦ)", "Москва", "RU", 55.756, 37.617),
    ("SPB", "Санкт-Петербург (РЦ)", "Санкт-Петербург", "RU", 59.939, 30.316),
    ("NNV", "Нижний Новгород", "Нижегородская обл.", "RU", 56.327, 44.006),
    ("KZN", "Казань", "Республика Татарстан", "RU", 55.796, 49.106),
    ("SMR", "Самара", "Самарская обл.", "RU", 53.195, 50.100),
    ("SRT", "Саратов", "Саратовская обл.", "RU", 51.533, 46.034),
    ("UFA", "Уфа", "Республика Башкортостан", "RU", 54.735, 55.958),
    ("EKB", "Екатеринбург (РЦ)", "Свердловская обл.", "RU", 56.838, 60.605),
    ("ROV", "Ростов-на-Дону (РЦ)", "Ростовская обл.", "RU", 47.222, 39.720),
    ("KRD", "Краснодар", "Краснодарский край", "RU", 45.035, 38.975),
    ("AST", "Астрахань", "Астраханская обл.", "RU", 46.348, 48.033),
    ("VRN", "Воронеж", "Воронежская обл.", "RU", 51.672, 39.184),
    ("TMB", "Тамбов", "Тамбовская обл.", "RU", 52.721, 41.452),
    ("ORN", "Оренбург", "Оренбургская обл.", "RU", 51.768, 55.097),
    ("KRG", "Курган", "Курганская обл.", "RU", 55.441, 65.341),
    ("OMS", "Омск", "Омская обл.", "RU", 54.989, 73.368),
    ("NSK", "Новосибирск (РЦ)", "Новосибирская обл.", "RU", 55.030, 82.920),
    ("KRS", "Красноярск", "Красноярский край", "RU", 56.010, 92.852),
    ("IRK", "Иркутск", "Иркутская обл.", "RU", 52.287, 104.281),
    ("ATR", "Атырау", "Атырауская обл.", "KZ", 47.094, 51.923),
    ("URL", "Уральск", "Западно-Казахстанская обл.", "KZ", 51.227, 51.386),
    ("AKT", "Актобе", "Актюбинская обл.", "KZ", 50.283, 57.167),
]

ROADS = [
    ("MSK", "SPB", "М-11 «Нева»", "федеральная", 0.95, 0.25, 9.5, 0),
    ("MSK", "VSK", "М-5 / А-108", "федеральная", 0.85, 0.55, 0, 0),
    ("MSK", "NNV", "М-12 «Восток»", "федеральная", 0.95, 0.2, 7.0, 0),
    ("NNV", "KZN", "М-12 «Восток»", "федеральная", 0.93, 0.15, 7.0, 0),
    ("MSK", "VRN", "М-4 «Дон»", "федеральная", 0.92, 0.2, 6.0, 0),
    ("VRN", "ROV", "М-4 «Дон»", "федеральная", 0.88, 0.1, 4.5, 0),
    ("ROV", "KRD", "М-4 «Дон»", "федеральная", 0.85, 0.2, 0, 0),
    ("KRD", "MKP", "Р-253 / А-159", "региональная", 0.7, 0.15, 0, 0),
    ("MKP", "D_KMM", "Подъездная дорога карьера", "местная", 0.55, 0.0, 0, 0),
    ("ROV", "VLG", "Р-260", "федеральная", 0.75, 0.1, 0, 0),
    ("VLG", "VTR", "Городская магистраль Волгограда", "местная", 0.7, 0.9, 0, 0),
    ("VSK", "TMB", "Р-22 «Каспий»", "федеральная", 0.8, 0.1, 0, 0),
    ("TMB", "VLG", "Р-22 «Каспий»", "федеральная", 0.78, 0.1, 0, 0),
    ("VRN", "TMB", "Р-193", "региональная", 0.72, 0.05, 0, 0),
    ("VLG", "SRT", "Р-228", "федеральная", 0.74, 0.1, 0, 0),
    ("SRT", "SMR", "Р-226", "федеральная", 0.76, 0.1, 0, 0),
    ("VTR", "AST", "Р-22 «Каспий»", "федеральная", 0.72, 0.05, 0, 0),
    ("AST", "ATR", "А-27 (МАПП Караозек)", "федеральная", 0.6, 0.05, 0, 1),
    ("ATR", "IND", "Атырау — Индерборский", "региональная", 0.58, 0.05, 0, 0),
    ("IND", "D_IND", "Подъездная дорога карьера", "местная", 0.5, 0.0, 0, 0),
    ("IND", "URL", "Индерборский — Уральск", "региональная", 0.55, 0.0, 0, 0),
    ("URL", "SRT", "А-298 (МАПП Озинки)", "региональная", 0.62, 0.05, 0, 1),
    ("URL", "ORN", "Р-336 (МАПП Маштаково)", "региональная", 0.64, 0.05, 0, 1),
    ("SMR", "KZN", "Р-241", "федеральная", 0.8, 0.1, 0, 0),
    ("KZN", "ABS", "Р-239", "федеральная", 0.82, 0.1, 0, 0),
    ("ABS", "D_ABS", "Подъездная дорога карьера", "местная", 0.6, 0.0, 0, 0),
    ("ABS", "UFA", "М-12 / М-7", "федеральная", 0.85, 0.1, 0, 0),
    ("ABS", "ORN", "Р-239", "федеральная", 0.75, 0.05, 0, 0),
    ("SMR", "UFA", "М-5 «Урал»", "федеральная", 0.83, 0.1, 0, 0),
    ("SMR", "ORN", "Р-246 / Р-239", "региональная", 0.73, 0.05, 0, 0),
    ("ORN", "ORB", "Р-335", "региональная", 0.68, 0.05, 0, 0),
    ("ORB", "D_DUB", "Подъездная дорога карьера", "местная", 0.55, 0.0, 0, 0),
    ("ORN", "AKT", "А-300 / М-32 (МАПП Сагарчин)", "федеральная", 0.65, 0.05, 0, 1),
    ("ORN", "UFA", "Р-240", "федеральная", 0.77, 0.05, 0, 0),
    ("UFA", "CHL", "М-5 «Урал»", "федеральная", 0.8, 0.1, 0, 0),
    ("CHL", "EKB", "Р-254 / М-5", "федеральная", 0.86, 0.25, 0, 0),
    ("UFA", "EKB", "Р-242", "региональная", 0.7, 0.05, 0, 0),
    ("CHL", "KRG", "Р-254 «Иртыш»", "федеральная", 0.8, 0.1, 0, 0),
    ("KRG", "OMS", "Р-254 «Иртыш»", "федеральная", 0.78, 0.05, 0, 0),
    ("EKB", "KRG", "Р-351 / Р-354", "региональная", 0.72, 0.05, 0, 0),
    ("OMS", "NSK", "Р-254 «Иртыш»", "федеральная", 0.82, 0.1, 0, 0),
    ("NSK", "KRS", "Р-255 «Сибирь»", "федеральная", 0.78, 0.1, 0, 0),
    ("KRS", "BKL", "Р-255 «Сибирь»", "федеральная", 0.72, 0.05, 0, 0),
    ("BKL", "IRK", "Р-255 «Сибирь»", "федеральная", 0.84, 0.35, 0, 0),
]

CARGO = [
    ("GYPSUM_STONE", "Гипсовый камень (навалом)", "самосвал", 950, 0.0016, 2.2, 0.5),
    ("CEMENT_BULK", "Цемент навалом", "цементовоз", 6400, 0.0006, 0.8, 0.3),
    ("CEMENT_BAG", "Цемент в мешках", "тент", 6900, 0.0010, 1.4, 2.0),
    ("DRY_MIX", "Сухие смеси в мешках", "тент", 11500, 0.0010, 1.5, 2.4),
    ("GKL", "Гипсокартон (ГКЛ)", "тент", 10200, 0.0018, 3.0, 2.6),
    ("PGP", "Пазогребневые плиты (ПГП)", "тент", 8800, 0.0014, 2.6, 1.0),
]

VEHICLE_MODELS = {
    "самосвал": [("КАМАЗ 65115", 15, 34), ("SITRAK C7H 6x4", 25, 38), ("Shacman X3000 6x4", 25, 39)],
    "цементовоз": [("КАМАЗ 5490 + ППЦ", 30, 35), ("Shacman X3000 + ППЦ", 32, 36)],
    "тент": [("КАМАЗ 54901 + полуприцеп", 20, 31), ("Volvo FH + тент", 22, 30), ("Shacman X3000 + тент", 22, 32)],
}

FLEET_PLAN = {
    "VLG": [("тент", 3), ("цементовоз", 1)],
    "VTR": [("тент", 2), ("цементовоз", 2)],
    "VSK": [("тент", 4), ("самосвал", 1)],
    "CHL": [("тент", 3), ("самосвал", 1)],
    "ORB": [("тент", 2), ("самосвал", 2)],
    "ABS": [("тент", 3), ("самосвал", 2)],
    "MKP": [("тент", 3), ("самосвал", 2)],
    "BKL": [("тент", 2), ("самосвал", 1)],
    "IND": [("тент", 1), ("самосвал", 2)],
}

PLATE_LETTERS = "АВЕКМНОРСТУХ"
REGION_CODES = {"VLG": "34", "VTR": "34", "VSK": "50", "CHL": "74", "ORB": "56", "ABS": "16", "MKP": "01", "BKL": "38"}

ROAD_FACTOR = {"федеральная": 1.18, "региональная": 1.25, "местная": 1.35}


def true_congestion(rng, road, weekday, hour, weather, event):
    urban = road["urban"]
    cat = road["category"]
    morning = math.exp(-((hour - 8) ** 2) / 4.0)
    evening = math.exp(-((hour - 18) ** 2) / 5.0)
    night = 1.0 if hour < 5 or hour >= 23 else 0.0
    weekend = 1.0 if weekday >= 5 else 0.0
    c = 1.0 + 0.06
    c += urban * (0.75 * morning + 0.95 * evening)
    c += 0.12 * (morning + evening) * (1 if cat == "федеральная" else 0.5)
    c -= weekend * (0.25 * urban + 0.05)
    c -= night * 0.05
    c += {"ясно": 0.0, "дождь": 0.12, "туман": 0.15, "снег": 0.32, "гололёд": 0.45}[weather]
    c += 0.25 * (1.0 - road["quality"])
    c += event * 0.6
    if weekday == 4:
        c += 0.08 * evening + 0.05
    c += rng.gauss(0, 0.06)
    return max(1.0, c)


def make_plate(rng, code):
    if code == "IND":
        return f"{rng.randint(100, 999)} {rng.choice('ABCDEFHK')}{rng.choice('ABCDEFHK')}{rng.choice('ABCDEFHK')} 06"
    l = PLATE_LETTERS
    return f"{rng.choice(l)}{rng.randint(100, 999)}{rng.choice(l)}{rng.choice(l)} {REGION_CODES[code]}"


def seed(db):
    rng = random.Random(2026)
    c = db.conn
    for code, name, region, country, lat, lon, addr, cap, stock, prod in PLANTS:
        c.execute(
            "INSERT INTO nodes(code,name,kind,region,country,lat,lon,address,capacity_tpd,stock_t,products) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (code, name, "plant", region, country, lat, lon, addr, cap, stock, prod),
        )
    for code, name, region, country, lat, lon, addr, cap, stock, prod in DEPOSITS:
        c.execute(
            "INSERT INTO nodes(code,name,kind,region,country,lat,lon,address,capacity_tpd,stock_t,products) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (code, name, "deposit", region, country, lat, lon, addr, cap, stock, prod),
        )
    for code, name, region, country, lat, lon in HUBS:
        c.execute(
            "INSERT INTO nodes(code,name,kind,region,country,lat,lon,address) VALUES (?,?,?,?,?,?,?,?)",
            (code, name, "hub", region, country, lat, lon, "распределительный центр / клиент"),
        )
    ids = {r["code"]: r["id"] for r in c.execute("SELECT id, code FROM nodes")}
    coords = {r["code"]: (r["lat"], r["lon"]) for r in c.execute("SELECT code, lat, lon FROM nodes")}
    for a, b, name, cat, q, urban, toll, border in ROADS:
        d = haversine(*coords[a], *coords[b]) * ROAD_FACTOR[cat]
        d = max(d, 6.0)
        c.execute(
            "INSERT INTO roads(a,b,name,category,distance_km,quality,urban,toll_rub_km,border) VALUES (?,?,?,?,?,?,?,?,?)",
            (ids[a], ids[b], name, cat, round(d, 1), q, urban, toll, border),
        )
    for row in CARGO:
        c.execute("INSERT INTO cargo_types VALUES (?,?,?,?,?,?,?)", row)
    regions = sorted({r[0] for r in c.execute("SELECT DISTINCT region FROM nodes")})
    special = {"Иркутская обл.": "снег", "Красноярский край": "снег", "Воронежская обл.": "дождь", "Западно-Казахстанская обл.": "гололёд", "Курганская обл.": "туман"}
    for reg in regions:
        c.execute("INSERT INTO weather(region, condition) VALUES (?, ?)", (reg, special.get(reg, "ясно")))

    for code, plan in FLEET_PLAN.items():
        for body, n in plan:
            for _ in range(n):
                model, cap, fuel = rng.choice(VEHICLE_MODELS[body])
                plate = make_plate(rng, code)
                while c.execute("SELECT 1 FROM vehicles WHERE plate=?", (plate,)).fetchone():
                    plate = make_plate(rng, code)
                c.execute(
                    "INSERT INTO vehicles(plate,model,body,capacity_t,fuel_l_100,base_node,location_node,status,odometer_km) VALUES (?,?,?,?,?,?,?,?,?)",
                    (plate, model, body, cap, fuel, ids[code], ids[code], "свободна", rng.randint(40000, 380000)),
                )
    c.execute("UPDATE vehicles SET location_node=? WHERE id IN (SELECT id FROM vehicles WHERE base_node=? AND body='тент' LIMIT 1)", (ids["KZN"], ids["VSK"]))
    c.execute("UPDATE vehicles SET location_node=? WHERE id IN (SELECT id FROM vehicles WHERE base_node=? AND body='тент' LIMIT 1)", (ids["ROV"], ids["MKP"]))
    c.execute("UPDATE vehicles SET location_node=? WHERE id IN (SELECT id FROM vehicles WHERE base_node=? AND body='тент' LIMIT 1)", (ids["EKB"], ids["CHL"]))

    roads = c.execute("SELECT * FROM roads").fetchall()
    hist = []
    for road in roads:
        for _ in range(260):
            wd = rng.randint(0, 6)
            hr = rng.randint(0, 23)
            wx = rng.choice(["ясно"] * 6 + ["дождь", "дождь", "туман", "снег", "гололёд"])
            ev = 1 if rng.random() < 0.05 else 0
            hist.append((road["id"], wd, hr, wx, ev, round(true_congestion(rng, road, wd, hr, wx, ev), 3)))
    c.executemany("INSERT INTO traffic_history(road_id,weekday,hour,weather,event,congestion) VALUES (?,?,?,?,?,?)", hist)

    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    road_by_names = {}
    for r in roads:
        road_by_names[(r["a"], r["b"])] = r["id"]
        road_by_names[(r["b"], r["a"])] = r["id"]
    events = [
        (("VRN", "ROV"), "ремонт", 0.5, "Ремонт покрытия, реверсивное движение на участке 18 км"),
        (("CHL", "EKB"), "пробка", 0.7, "Затор на въезде в Екатеринбург"),
        (("TMB", "VLG"), "ДТП", 0.4, "ДТП с участием грузового ТС, одна полоса"),
        (("URL", "SRT"), "перекрытие", 1.0, "МАПП: ограничение пропуска грузового транспорта"),
    ]
    for (a, b), kind, sev, desc in events:
        c.execute(
            "INSERT INTO road_events(road_id,kind,severity,description,active,created_at) VALUES (?,?,?,?,1,?)",
            (road_by_names[(ids[a], ids[b])], kind, sev, desc, (now - timedelta(hours=rng.randint(1, 20))).strftime("%Y-%m-%d %H:%M")),
        )

    orders = [
        ("VSK", "SPB", "GKL", 18), ("VSK", "SPB", "DRY_MIX", 12), ("VSK", "NNV", "DRY_MIX", 9),
        ("VSK", "KZN", "GKL", 19), ("ABS", "MSK", "DRY_MIX", 20), ("ABS", "NNV", "PGP", 8),
        ("ABS", "SMR", "GKL", 15), ("MKP", "ROV", "GKL", 20), ("MKP", "KRD", "DRY_MIX", 14),
        ("MKP", "VRN", "PGP", 11), ("VLG", "ROV", "DRY_MIX", 7), ("VLG", "SRT", "GKL", 16),
        ("VLG", "AST", "PGP", 10), ("VTR", "SRT", "CEMENT_BULK", 28), ("VTR", "VRN", "CEMENT_BULK", 26),
        ("VTR", "AST", "CEMENT_BAG", 18), ("CHL", "EKB", "GKL", 20), ("CHL", "UFA", "DRY_MIX", 13),
        ("CHL", "OMS", "GKL", 17), ("ORB", "ORN", "DRY_MIX", 6), ("ORB", "SMR", "PGP", 15),
        ("ORB", "UFA", "DRY_MIX", 9), ("BKL", "IRK", "GKL", 14), ("BKL", "KRS", "DRY_MIX", 18),
        ("IND", "ATR", "DRY_MIX", 12), ("IND", "URL", "GKL", 10),
        ("D_ABS", "ABS", "GYPSUM_STONE", 25), ("D_ABS", "ABS", "GYPSUM_STONE", 24), ("D_DUB", "ORB", "GYPSUM_STONE", 25),
        ("D_KMM", "MKP", "GYPSUM_STONE", 25), ("D_KMM", "VLG", "GYPSUM_STONE", 25), ("D_IND", "IND", "GYPSUM_STONE", 23),
        ("D_DUB", "CHL", "GYPSUM_STONE", 25), ("D_ABS", "VSK", "GYPSUM_STONE", 25),
    ]
    for o, d, cargo, w in orders:
        due = now + timedelta(days=rng.randint(1, 5))
        c.execute(
            "INSERT INTO orders(created_at,origin,destination,cargo,weight_t,due_date,priority,status) VALUES (?,?,?,?,?,?,?,?)",
            (now.strftime("%Y-%m-%d %H:%M"), ids[o], ids[d], cargo, w, due.strftime("%Y-%m-%d"), rng.choice([1, 2, 2, 3]), "новый"),
        )
    db.conn.commit()
