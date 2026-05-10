"""Effective-distance metric on the air-mobility graph.

After Brockmann & Helbing (2013, "Hidden Geometry of Complex, Network-Driven
Contagion Phenomena", Science 342, 1337). For a directed flow matrix F where
F[i, j] is the flow from i to j, the per-edge effective distance is

    d_eff(i -> j) = 1 - log(p_ij),  p_ij = F[i, j] / sum_k F[i, k]

and the path effective distance from a seed s to any t is the min over all
paths of the sum of edge effective distances. Brockmann's empirical result is
that outbreak arrival times are approximately linear in this metric.

We compute single-source shortest paths from the seed via a simple Dijkstra
over a per-row-normalised version of the air-flow matrix; n is small (~70
countries) so the heap variant is more than fast enough.
"""

from __future__ import annotations

import heapq
import math

import numpy as np


def edge_weights(flow: np.ndarray) -> np.ndarray:
    """Per-edge effective-distance weights w[i, j] = 1 - log(F[i, j] / row_sum_i).

    Cells with zero or negative flow get +inf (no edge). The diagonal is +inf
    because a node has no edge to itself.
    """
    row_sum = flow.sum(axis=1, keepdims=True)
    safe = np.where(row_sum > 0, row_sum, 1.0)
    p = flow / safe
    with np.errstate(divide="ignore", invalid="ignore"):
        w = 1.0 - np.log(p)
    w = np.where(p > 0, w, np.inf)
    np.fill_diagonal(w, np.inf)
    return w


def dijkstra(weights: np.ndarray, source: int) -> np.ndarray:
    """Single-source shortest path on a dense adjacency matrix.

    Returns d[t] = effective distance from source to t. Unreachable nodes
    receive +inf. The source itself receives 0.
    """
    n = weights.shape[0]
    dist = np.full(n, np.inf, dtype=np.float64)
    dist[source] = 0.0
    heap: list[tuple[float, int]] = [(0.0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        row = weights[u]
        for v in range(n):
            w = row[v]
            if not math.isfinite(w):
                continue
            alt = d + w
            if alt < dist[v]:
                dist[v] = alt
                heapq.heappush(heap, (alt, v))
    return dist


def effective_distance_from(flow: np.ndarray, source: int) -> np.ndarray:
    """Convenience wrapper: weights + Dijkstra from a seed index."""
    return dijkstra(edge_weights(flow), source)
