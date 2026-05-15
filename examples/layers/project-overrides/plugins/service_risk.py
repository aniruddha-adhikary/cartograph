def run(graph, args):
    risky = {}
    for edge in graph.get("edges", []):
        if edge.get("cross_repo") and edge.get("confidence") != "high":
            risky.setdefault(edge["from_service"], 0)
            risky[edge["from_service"]] += 1
            risky.setdefault(edge["to_service"], 0)
            risky[edge["to_service"]] += 1
    return dict(sorted(risky.items(), key=lambda item: item[1], reverse=True))
