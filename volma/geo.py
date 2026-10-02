import math


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fmt_hours(h):
    if h is None:
        return "—"
    total = int(round(h * 60))
    d, rem = divmod(total, 1440)
    hh, mm = divmod(rem, 60)
    if d:
        return f"{d} д {hh} ч {mm:02d} м"
    return f"{hh} ч {mm:02d} м"


def fmt_rub(v):
    return f"{v:,.0f} ₽".replace(",", " ")


def fmt_num(v, digits=0):
    return f"{v:,.{digits}f}".replace(",", " ")
