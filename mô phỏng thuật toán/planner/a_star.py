import math, heapq, numpy as np

def neighbors8(grid, r, c, no_corner_cutting=True):
    """
    Sinh láng giềng 8 hướng.
    - grid: 0=free, 1=obstacle
    - no_corner_cutting: True => cấm đi chéo nếu hai ô cạnh kề là obstacle (tránh 'lách' góc)
    Yields: (nr, nc, step_cost)
    """
    h, w = grid.shape

    # 4-connected
    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
        nr, nc = r+dr, c+dc
        if 0 <= nr < h and 0 <= nc < w:
            yield nr, nc, 1.0

    # diagonals
    for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
        nr, nc = r+dr, c+dc
        if 0 <= nr < h and 0 <= nc < w:
            if no_corner_cutting:
                ar, ac = r+dr, c     # ô "kẹp" 1
                br, bc = r, c+dc     # ô "kẹp" 2
                if grid[ar, ac] == 1 or grid[br, bc] == 1:
                    continue
            yield nr, nc, math.sqrt(2.0)

def octile(a, b):
    """
    Heuristic Octile cho 8 hướng (admissible & consistent nếu cost như trên).
    a,b: (r, c)
    """
    dx, dy = abs(a[0]-b[0]), abs(a[1]-b[1])
    m, n = max(dx, dy), min(dx, dy)
    return (m - n) + n * math.sqrt(2.0)

def a_star(grid, start, goal, no_corner_cutting=True):
    expanded = 0
    max_open = 0
    visited  = 0

    if start == goal:
        return [start], {"expanded": expanded, "max_open": max_open, "visited": visited}

    h, w = grid.shape
    if grid[start] == 1 or grid[goal] == 1:
        return [], {"expanded": expanded, "max_open": max_open, "visited": visited}

    open_set = [(octile(start, goal), 0.0, start)]
    came = {}
    g_cost = {start: 0.0}
    closed = set()

    while open_set:
        # theo dõi open_set lớn nhất
        if len(open_set) > max_open:
            max_open = len(open_set)

        f, gc, cur = heapq.heappop(open_set)
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

            visited = len(g_cost)  # số node từng được chạm
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
                heapq.heappush(open_set, (ng + octile(nxt, goal), ng, nxt))

    visited = len(g_cost)
    stats = {
        "expanded": expanded,
        "max_open": max_open,
        "visited": visited,
    }
    return [], stats
