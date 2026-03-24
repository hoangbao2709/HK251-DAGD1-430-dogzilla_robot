import heapq
from warehouse_map import GRAPH, START_NODE, normalize_target


class PathPlanner:
    def __init__(self, graph=None, start_node=None):
        self.graph = graph if graph is not None else GRAPH
        self.start_node = start_node if start_node is not None else START_NODE

    def shortest_path(self, start, goal):
        if start not in self.graph:
            raise ValueError(f"Unknown start node: {start}")
        if goal not in self.graph:
            raise ValueError(f"Unknown goal node: {goal}")

        distances = {node: float("inf") for node in self.graph}
        previous = {node: None for node in self.graph}
        distances[start] = 0

        pq = [(0, start)]
        visited = set()

        while pq:
            current_dist, current_node = heapq.heappop(pq)

            if current_node in visited:
                continue
            visited.add(current_node)

            if current_node == goal:
                break

            for neighbor, weight in self.graph[current_node].items():
                new_dist = current_dist + weight
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    previous[neighbor] = current_node
                    heapq.heappush(pq, (new_dist, neighbor))

        if distances[goal] == float("inf"):
            return []

        return self._reconstruct_path(previous, goal)

    def shortest_from_start(self, target):
        target = normalize_target(target)
        return self.shortest_path(self.start_node, target)

    def distance(self, start, goal):
        path = self.shortest_path(start, goal)
        if not path:
            return float("inf")

        total = 0
        for i in range(len(path) - 1):
            total += self.graph[path[i]][path[i + 1]]
        return total

    def distance_from_start(self, target):
        target = normalize_target(target)
        return self.distance(self.start_node, target)

    def all_paths_from_start(self):
        result = {}
        for target in ["A", "B", "C", "D", "E", "F"]:
            result[target] = {
                "path": self.shortest_from_start(target),
                "distance": self.distance_from_start(target),
            }
        return result

    def _reconstruct_path(self, previous, goal):
        path = []
        current = goal

        while current is not None:
            path.append(current)
            current = previous[current]

        path.reverse()
        return path


if __name__ == "__main__":
    planner = PathPlanner()

    for target in ["A", "B", "C", "D", "E", "F"]:
        path = planner.shortest_from_start(target)
        dist = planner.distance_from_start(target)
        print(f"{target}: path={path}, distance={dist}")