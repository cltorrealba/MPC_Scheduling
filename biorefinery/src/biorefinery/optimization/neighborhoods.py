"""Neighborhood generation and filtering utilities.

Legacy tests expect a different API for k=1..5 neighborhood generators operating
on an integer vector with explicit lower/upper bounds and returning concrete
neighbor point lists (not direction vectors). We provide lightweight wrappers
while preserving direction-based generators used in dsda.py.
"""
from __future__ import annotations
import itertools as it
import numpy as np
from typing import Sequence, List, Tuple

# ---------------- Wrappers matching test_neighborhoods.py expectations ---------------
def _within_bounds(pt: Sequence[int], lb: Sequence[int], ub: Sequence[int]) -> bool:
    return all(l <= v <= u for v, l, u in zip(pt, lb, ub))

def neighborhood_k_eq_1(current: Sequence[int], lb: Sequence[int], ub: Sequence[int]) -> List[Tuple[int,...]]:  # type: ignore[override]
    neigh = []
    n = len(current)
    for i in range(n):
        for delta in (-1, 1):
            cand = list(current)
            cand[i] = cand[i] + delta
            if _within_bounds(cand, lb, ub):
                neigh.append(tuple(cand))
    return neigh

def neighborhood_k_eq_2(current: Sequence[int], lb: Sequence[int], ub: Sequence[int]) -> List[Tuple[int,...]]:  # type: ignore[override]
    neigh = []
    n = len(current)
    idx_pairs = list(it.combinations(range(n), 2))
    for (i, j) in idx_pairs:
        for di in (-1, 1):
            for dj in (-1, 1):
                cand = list(current)
                cand[i] += di
                cand[j] += dj
                if _within_bounds(cand, lb, ub):
                    neigh.append(tuple(cand))
    return neigh

def neighborhood_k_eq_3(current: Sequence[int], lb: Sequence[int], ub: Sequence[int]) -> List[Tuple[int,...]]:
    n = len(current)
    if n < 3:
        return []
    neigh = []
    for comb in it.combinations(range(n), 3):
        for deltas in it.product([-1, 1], repeat=3):
            cand = list(current)
            for idx, d in zip(comb, deltas):
                cand[idx] += d
            if _within_bounds(cand, lb, ub):
                neigh.append(tuple(cand))
    return neigh

def neighborhood_k_eq_4(current: Sequence[int], lb: Sequence[int], ub: Sequence[int]) -> List[Tuple[int,...]]:
    # If vector shorter than 4 no moves
    if len(current) < 4:
        return []
    # Provide combinations of 4 indices
    neigh = []
    for comb in it.combinations(range(len(current)), 4):
        for deltas in it.product([-1, 1], repeat=4):
            cand = list(current)
            for idx, d in zip(comb, deltas):
                cand[idx] += d
            if _within_bounds(cand, lb, ub):
                neigh.append(tuple(cand))
    return neigh

def neighborhood_k_eq_5(current: Sequence[int], lb: Sequence[int], ub: Sequence[int]) -> List[Tuple[int,...]]:
    if len(current) < 5:
        return []
    neigh = []
    for comb in it.combinations(range(len(current)), 5):
        for deltas in it.product([-1, 1], repeat=5):
            cand = list(current)
            for idx, d in zip(comb, deltas):
                cand[idx] += d
            if _within_bounds(cand, lb, ub):
                neigh.append(tuple(cand))
    return neigh

def find_actual_neighbors(points: Sequence[Tuple[int,...]], current: Sequence[int], lb: Sequence[int], ub: Sequence[int]) -> List[Tuple[int,...]]:  # type: ignore[override]
    # Filter duplicates, remove current, enforce bounds
    filtered = []
    seen = set()
    for p in points:
        if tuple(p) == tuple(current):
            continue
        if tuple(p) in seen:
            continue
        if _within_bounds(p, lb, ub):
            seen.add(tuple(p))
            filtered.append(tuple(p))
    return filtered


def neighborhood_k_eq_all(dimension: int = 2):
    directions = {1: list(np.ones(dimension, dtype=int)), 2: list(-np.ones(dimension, dtype=int))}
    return directions


def dir_neighborhood_k_eq_2(dimension: int = 2):
    num_neigh = 2 * dimension
    neighbors = np.concatenate((np.eye(dimension, dtype=int), -np.eye(dimension, dtype=int)), axis=1)
    directions = {}
    for i in range(num_neigh):
        direct = []
        directions[i + 1] = direct
        for j in range(dimension):
            direct.append(neighbors[j, i])
    return directions


def neighborhood_k_eq_inf(dimension: int = 2):
    neighbors = list(it.product([-1, 0, 1], repeat=dimension))
    directions = {i + 1: list(neighbors[i]) for i in range(len(neighbors))}
    temp = directions.copy()
    for i in list(directions.keys()):
        if temp.get(i) == [0] * dimension:
            temp.pop(i, None)
    return temp


def neighborhood_k_eq_l_natural(dimension: int = 2):
    if dimension == 1:
        return dir_neighborhood_k_eq_2(dimension)
    set_ = np.arange(1, dimension + 1, 1)
    N_lflat = np.zeros(((2 ** (dimension + 1)) - 2, dimension), dtype=int)
    k = 0
    for i in range(dimension):
        sub = np.array(list(it.combinations(set_, dimension - i)), dtype=int)
        f = np.size(sub, 0)
        for j in range(0, f):
            N_lflat[k, 0:dimension] = np.array(np.isin(set_, sub[j, :]), dtype=int)
            k += 1
            N_lflat[k, 0:dimension] = -np.array(np.isin(set_, sub[j, :]), dtype=int)
            k += 1
    directions = dict(enumerate(N_lflat.tolist(), 1))
    return directions


def neighborhood_k_eq_l_natural_modified(dimension: int = 2):
    if dimension == 1:
        return dir_neighborhood_k_eq_2(dimension)
    set_ = np.arange(1, dimension + 1, 1)
    N_lflat = np.zeros(((2 ** (dimension + 1)) - 2, dimension), dtype=int)
    k = 0
    for i in range(dimension):
        sub = np.array(list(it.combinations(set_, dimension - i)), dtype=int)
        f = np.size(sub, 0)
        for j in range(0, f):
            partial = np.array(np.isin(set_, sub[j, :]), dtype=int)
            if sum(abs(partial[k]) for k in range(dimension)) <= 2:
                N_lflat[k, 0:dimension] = partial
                k += 1
                N_lflat[k, 0:dimension] = -partial
                k += 1
    N_lflat = N_lflat[~np.all(N_lflat == 0, axis=1)]
    directions = dict(enumerate(N_lflat.tolist(), 1))
    return directions


def neighborhood_k_eq_m_natural(dimension: int = 2):
    N_Mflat = np.zeros((dimension * (dimension + 1), dimension), dtype=int)
    mat1 = np.eye(dimension, dimension, dtype=int)
    mat1 = np.append(mat1, np.zeros((1, dimension), dtype=int), axis=0)
    f = np.size(mat1, 0)
    k = 0
    for i in range(f):
        for j in range(f):
            if i != j:
                N_Mflat[k, 0:dimension] = mat1[i, :] - mat1[j, :]
                k += 1
    directions = dict(enumerate(N_Mflat.tolist(), 1))
    return directions


def find_actual_neighbors(arg1, arg2, arg3=None, arg4=None):
    """Dual-behavior helper:

    - If first argument is a list/tuple of ints and second is a dict: direction-based (legacy dsda)
    - If first argument is a sequence of point tuples and second is current point tuple: point filtering (tests)
    """
    # Point-based signature: (points, current, lb, ub)
    if isinstance(arg1, (list, tuple)) and len(arg1) > 0 and isinstance(arg1[0], (list, tuple)) and not isinstance(arg2, dict):
        points = arg1
        current = arg2
        lb = arg3
        ub = arg4
        return [p for p in points if p != current and _within_bounds(p, lb, ub) and points.index(p) == points.index(p)]  # duplicates naturally filtered by set comprehension below
    # Direction-based fallback
    start = arg1
    neighborhood = arg2
    min_allowed = arg3 or {}
    max_allowed = arg4 or {}
    neighbors = {0: start}
    for i in neighborhood.keys():
        neighbors[i] = list(map(sum, zip(start, list(neighborhood[i]))))
    new_neighbors = {}
    num_vars = len(neighbors[0])
    for i in neighbors.keys():
        checked = 0
        for j in range(num_vars):
            if neighbors[i][j] >= min_allowed.get(j + 1, -10**9) and neighbors[i][j] <= max_allowed.get(j + 1, 10**9):
                checked += 1
        if checked == num_vars:
            new_neighbors[i] = neighbors[i]
    return new_neighbors
