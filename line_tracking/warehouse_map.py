GRAPH = {
    "S": {"J1": 1},
    "J1": {"S": 1, "J2": 1, "A": 1, "B": 1},
    "J2": {"J1": 1, "J3": 1, "C": 1, "D": 1},
    "J3": {"J2": 1, "E": 1, "F": 1},
    "A": {"J1": 1},
    "B": {"J1": 1},
    "C": {"J2": 1},
    "D": {"J2": 1},
    "E": {"J3": 1},
    "F": {"J3": 1},
}

START_NODE = "S"
VALID_TARGETS = ["A", "B", "C", "D", "E", "F"]
JUNCTION_SEQUENCE_FROM_START = ["J1", "J2", "J3"]

# đổi mapping ở đây theo thực tế camera của bạn
DESTINATION_TO_TURN = {
    "A": {"junction": "J1", "choice": "right"},
    "B": {"junction": "J1", "choice": "left"},
    "C": {"junction": "J2", "choice": "right"},
    "D": {"junction": "J2", "choice": "left"},
    "E": {"junction": "J3", "choice": "right"},
    "F": {"junction": "J3", "choice": "left"},
}

def is_valid_target(target):
    if target is None:
        return False
    return str(target).strip().upper() in VALID_TARGETS


def normalize_target(target):
    if target is None:
        raise ValueError("Target cannot be None")

    normalized = str(target).strip().upper()
    if normalized not in VALID_TARGETS:
        raise ValueError(f"Invalid target '{target}'. Valid targets: {VALID_TARGETS}")
    return normalized


def get_graph():
    return GRAPH


def get_neighbors(node):
    return GRAPH.get(node, {})


def get_turn_info(target):
    target = normalize_target(target)
    return DESTINATION_TO_TURN[target]