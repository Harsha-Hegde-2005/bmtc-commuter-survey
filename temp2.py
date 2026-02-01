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

AUTO_TERMINALS = {s for s,c in terminal_count.items() if c >= 5}

# =====================================================
# HELPERS
# =====================================================
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2-lat1)
    dlon = radians(lon2-lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 2*R*atan2(sqrt(a), sqrt(1-a))

def bmtc_fare(distance):
    slabs = [(2,6),(4,12),(6,18),(8,23),(10,23),(12,24),
             (14,24),(16,28),(18,28),(20,28),(22,30),
             (24,30),(26,30),(28,30),(30,30)]
    for d,f in slabs:
        if distance <= d:
            return f
    return 32

# =====================================================
# FIND ALL POSSIBLE DIRECT / TERMINAL BUSES (CLEAN)
# =====================================================
def find_all_possible_buses(src, dst):
    buses = set()
    src_routes = set(stops_df[stops_df.stop_norm == src].route_no)

    for r in src_routes:
        g = stops_df[stops_df.route_no == r]
        if src not in g.stop_norm.values:
            continue

        src_seq = g[g.stop_norm == src].stop_sequence.values[0]

        # direct
        if dst in g.stop_norm.values:
            if g[g.stop_norm == dst].stop_sequence.values[0] > src_seq:
                if len(g) >= 15:
                    buses.add(r)
                continue

        # terminal fallback
        for t in AUTO_TERMINALS & set(g.stop_norm.values):
            if g[g.stop_norm == t].stop_sequence.values[0] > src_seq:
                if len(g) >= 15:
                    buses.add(r)
                break

    return sorted(buses)

# =====================================================
# MAIN PLANNER (HUMAN-CORRECT)
# =====================================================
def plan_journey_ui(src_raw, dst_raw):
    src = norm(src_raw)
    dst = norm(dst_raw)

    if src not in stops_df.stop_norm.values:
        raise Exception("Source stop not found")

    # -------------------------------
    # DIRECT BUS SHORT-CIRCUIT
    # -------------------------------
    direct_candidates = []
    for r in find_all_possible_buses(src, dst):
        g = stops_df[stops_df.route_no == r]
        if dst in g.stop_norm.values:
            direct_candidates.append(r)

    if direct_candidates:
        # pick strongest corridor (most stops)
        best = max(direct_candidates,
                   key=lambda r: len(stops_df[stops_df.route_no == r]))

        g = stops_df[stops_df.route_no == best]
        s_seq = g[g.stop_norm == src].stop_sequence.values[0]
        d_seq = g[g.stop_norm == dst].stop_sequence.values[0]
        lo, hi = min(s_seq,d_seq), max(s_seq,d_seq)

        seg_stops = g[
            (g.stop_sequence >= lo) & (g.stop_sequence <= hi)
        ].sort_values("stop_sequence")

        dist = 0
        for i in range(len(seg_stops)-1):
            a,b = seg_stops.iloc[i], seg_stops.iloc[i+1]
            dist += haversine(a.latitude,a.longitude,b.latitude,b.longitude)

        return (
            [(best,
              seg_stops.iloc[0].stop_name,
              seg_stops.iloc[-1].stop_name,
              seg_stops.stop_name.tolist())],
            dist,
            0,
            bmtc_fare(dist),
            find_all_possible_buses(src, dst)
        )

    # -------------------------------
    # GRAPH (PRUNED)
    # -------------------------------
    routes_from_src = set(stops_df[stops_df.stop_norm == src].route_no)
    routes_to_dst = set(stops_df[stops_df.stop_norm == dst].route_no)
    top_routes = set(routes_df.route_no.value_counts().head(50).index)

    candidate_routes = routes_from_src | routes_to_dst | top_routes
    filtered = stops_df[stops_df.route_no.isin(candidate_routes)]

    graph = {}
    for r, g in filtered.groupby("route_no"):
        g = g.sort_values("stop_sequence")
        for i in range(len(g)-1):
            a,b = g.iloc[i], g.iloc[i+1]
            u = (a.stop_norm, r)
            v = (b.stop_norm, r)
            d = haversine(a.latitude,a.longitude,b.latitude,b.longitude)
            graph.setdefault(u, []).append((v,d))
            graph.setdefault(v, []).append((u,d))

    for stop in filtered.stop_norm.unique():
        rs = filtered[filtered.stop_norm==stop].route_no.unique()
        for r1 in rs:
            for r2 in rs:
                if r1 != r2:
                    graph.setdefault((stop,r1), []).append(((stop,r2),0))

    # -------------------------------
    # DIJKSTRA (MAX 1 TRANSFER)
    # -------------------------------
    pq, dist, parent = [], {}, {}
    best_fallback = None

    for r in routes_from_src:
        pq.append((0,0,(src,r)))
        dist[(src,r)] = (0,0)

    while pq:
        t,d,u = heapq.heappop(pq)
        if dist.get(u,(1e9,1e9)) < (t,d):
            continue

        stop,route = u

        if stop == dst:
            end = u
            break

        if stop in AUTO_TERMINALS and best_fallback is None:
            best_fallback = u

        for v,w in graph.get(u,[]):
            ns,nr = v
            nt = t + (0 if nr==route else 1)
            if nt > 1:   # 🚫 HARD TRANSFER CAP
                continue

            nd = d + w
            route_len = len(stops_df[stops_df.route_no == nr])
            penalty = 0 if route_len >= 25 else 5

            if v not in dist or (nt,nd+penalty) < dist[v]:
                dist[v] = (nt,nd+penalty)
                parent[v] = u
                heapq.heappush(pq,(nt,nd+penalty,v))
    else:
        if best_fallback:
            end = best_fallback
        else:
            raise Exception("No route found")

    # -------------------------------
    # PATH → SEGMENTS
    # -------------------------------
    path=[]
    cur=end
    while cur:
        path.append(cur)
        cur=parent.get(cur)
    path.reverse()

    segments=[]
    cur_route=path[0][1]
    start=path[0][0]

    for i in range(1,len(path)):
        s,r=path[i]
        if r!=cur_route:
            segments.append((cur_route,start,path[i-1][0]))
            cur_route=r
            start=s
    segments.append((cur_route,start,path[-1][0]))

    ui_segments=[]
    for r,s,e in segments:
        g = stops_df[stops_df.route_no == r]
        sname = g[g.stop_norm==s].iloc[0].stop_name
        ename = g[g.stop_norm==e].iloc[0].stop_name

        s_seq = g[g.stop_norm==s].stop_sequence.values[0]
        e_seq = g[g.stop_norm==e].stop_sequence.values[0]
        lo,hi = min(s_seq,e_seq), max(s_seq,e_seq)

        stops = g[
            (g.stop_sequence>=lo)&(g.stop_sequence<=hi)
        ].sort_values("stop_sequence").stop_name.tolist()

        ui_segments.append((r,sname,ename,stops))

    total_distance = dist[end][1]
    transfers = dist[end][0]

    return (
        ui_segments,
        total_distance,
        transfers,
        bmtc_fare(total_distance),
        find_all_possible_buses(src, dst)
    )
