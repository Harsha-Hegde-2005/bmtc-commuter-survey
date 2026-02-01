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
# AUTO TERMINAL DETECTION (GENERIC)
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
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def bmtc_fare(distance):
    slabs = [
        (2, 6), (4, 12), (6, 18), (8, 23), (10, 23),
        (12, 24), (14, 24), (16, 28), (18, 28), (20, 28),
        (22, 30), (24, 30), (26, 30), (28, 30), (30, 30)
    ]
    for d, f in slabs:
        if distance <= d:
            return f
    return 32

# =====================================================
# STRICT SURVEY-ONLY BUS FETCH (IMPORTANT)
# =====================================================
def find_survey_buses(src, dst):
    """
    ONLY buses that go from src -> dst directly
    Correct direction, no terminals, no transfers.
    """
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
# PLANNER BUS FETCH (DIRECT + TERMINAL FALLBACK)
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

# =====================================================
# MAIN PLANNER (UNCHANGED LOGIC)
# =====================================================
def plan_journey_ui(src_raw, dst_raw):
    src = norm(src_raw)
    dst = norm(dst_raw)

    if src not in stops_df.stop_norm.values:
        raise Exception("Source stop not found")

    # DIRECT BUS SHORT-CIRCUIT
    direct_candidates = []
    for r in find_all_possible_buses(src, dst):
        g = stops_df[stops_df.route_no == r]
        if dst in g.stop_norm.values:
            direct_candidates.append(r)

    if direct_candidates:
        best = max(direct_candidates, key=lambda r: len(stops_df[stops_df.route_no == r]))
        g = stops_df[stops_df.route_no == best]

        s_seq = g[g.stop_norm == src].stop_sequence.values[0]
        d_seq = g[g.stop_norm == dst].stop_sequence.values[0]
        lo, hi = min(s_seq, d_seq), max(s_seq, d_seq)

        seg = g[(g.stop_sequence >= lo) & (g.stop_sequence <= hi)].sort_values("stop_sequence")

        dist = 0
        for i in range(len(seg) - 1):
            a, b = seg.iloc[i], seg.iloc[i + 1]
            dist += haversine(a.latitude, a.longitude, b.latitude, b.longitude)

        return (
            [(best, seg.iloc[0].stop_name, seg.iloc[-1].stop_name, seg.stop_name.tolist())],
            dist,
            0,
            bmtc_fare(dist),
            find_all_possible_buses(src, dst)
        )

    raise Exception("No direct bus – graph routing omitted here for brevity")
