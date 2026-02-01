import pandas as pd
import heapq
from math import radians, sin, cos, sqrt, atan2

# =====================================================
# LOAD DATA
# =====================================================
stops_df = pd.read_csv("bmtc_stop_level.csv")
routes_df = pd.read_excel("bmtc_dump.xlsx", engine="openpyxl")

def norm(x):
    return str(x).strip().lower()

stops_df["stop_norm"] = stops_df["stop_name"].apply(norm)

# =====================================================
# AUTO TERMINAL DETECTION
# =====================================================
terminal_count = {}
for r, g in stops_df.groupby("route_no"):
    last_stop = g.sort_values("stop_sequence").iloc[-1].stop_norm
    terminal_count[last_stop] = terminal_count.get(last_stop, 0) + 1

AUTO_TERMINALS = {s for s, c in terminal_count.items() if c >= 5}

# =====================================================
# HELPERS
# =====================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2*R*atan2(sqrt(a), sqrt(1-a))

def bmtc_fare(distance):
    slabs = [
        (2,6),(4,12),(6,18),(8,23),(10,23),
        (12,24),(14,24),(16,28),(18,28),(20,28),
        (22,30),(24,30),(26,30),(28,30),(30,30)
    ]
    for d,f in slabs:
        if distance <= d:
            return f
    return 32

# =====================================================
# STRICT SURVEY-ONLY BUS FETCH
# =====================================================
def find_survey_buses(src, dst):
    buses = set()
    src_routes = set(stops_df[stops_df.stop_norm == src].route_no)

    for r in src_routes:
        g = stops_df[stops_df.route_no == r]

        if src not in g.stop_norm.values or dst not in g.stop_norm.values:
            continue

        src_seq = g[g.stop_norm == src].stop_sequence.values[0]
        dst_seq = g[g.stop_norm == dst].stop_sequence.values[0]

        if dst_seq > src_seq and len(g) >= 15:
            buses.add(r)

    return sorted(buses)

# =====================================================
# PLANNER BUS FETCH (USED BY MAIN APP)
# =====================================================
def find_all_possible_buses(src, dst):
    buses = set()
    src_routes = set(stops_df[stops_df.stop_norm == src].route_no)

    for r in src_routes:
        g = stops_df[stops_df.route_no == r]
        src_seq = g[g.stop_norm == src].stop_sequence.values[0]

        if dst in g.stop_norm.values:
            if g[g.stop_norm == dst].stop_sequence.values[0] > src_seq:
                if len(g) >= 15:
                    buses.add(r)
                continue

        for t in AUTO_TERMINALS & set(g.stop_norm.values):
            if g[g.stop_norm == t].stop_sequence.values[0] > src_seq:
                if len(g) >= 15:
                    buses.add(r)
                break

    return sorted(buses)
