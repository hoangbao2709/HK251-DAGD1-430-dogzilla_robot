import math, heapq, numpy as np
from .a_star import neighbors8  # dùng chung neighbors8 để đồng nhất corner-cutting

def dijkstra(grid, start, goal, no_corner_cutting=True):
    expanded = 0
    max_open = 0
    visited  = 0

    if start == goal:
        return [start], {"expanded": expanded, "max_open": max_open, "visited": visited}

    h, w = grid.shape
    if grid[start] == 1 or grid[goal] == 1:
        return [], {"expanded": expanded, "max_open": max_open, "visited": visited}

    open_set = [(0.0, start)]
    came = {}
    g_cost = {start: 0.0}
    closed = set()

    while open_set:
        if len(open_set) > max_open:
            max_open = len(open_set)

        gc, cur = heapq.heappop(open_set)
        if cur in closed:
            continue
        closed.add(cur)
        expanded += 1

        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()

            visited = len(g_cost)
            stats = {
                "expanded": expanded,
                "max_open": max_open,
                "visited": visited,
            }
            return path, stats

        r, c = cur
        for nr, nc, step in neighbors8(grid, r, c, no_corner_cutting):
            if grid[nr, nc] == 1:
                continue
            ng = gc + step
            nxt = (nr, nc)
            if ng < g_cost.get(nxt, float('inf')):
                g_cost[nxt] = ng
                came[nxt] = cur
                heapq.heappush(open_set, (ng, nxt))

    visited = len(g_cost)
    stats = {
        "expanded": expanded,
        "max_open": max_open,
        "visited": visited,
    }
    return [], stats

