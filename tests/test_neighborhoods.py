import itertools
import math

from biorefinery.optimization.neighborhoods import (
    neighborhood_k_eq_1,
    neighborhood_k_eq_2,
    neighborhood_k_eq_3,
    neighborhood_k_eq_4,
    neighborhood_k_eq_5,
    find_actual_neighbors,
)


def test_neighborhood_cardinalities_small_vector():
    current = (1, 2, 3)
    ub = (3, 3, 4)
    lb = (0, 0, 0)

    n1 = neighborhood_k_eq_1(current, lb, ub)
    # Each position can +1 or -1 if within bounds. For (1,2,3) with lb (0,0,0) and ub (3,3,4):
    # idx0: can go to 0 or 2 (2 moves)
    # idx1: can go to 1 or 3 (2 moves)
    # idx2: can go to 2 or 4 (2 moves)
    assert len(n1) == 6

    n2 = neighborhood_k_eq_2(current, lb, ub)
    # Rough upper bound choose(3,2)*2^2 = 3*4=12; some may violate bounds; ensure <=12 and >0
    assert 0 < len(n2) <= 12

    n3 = neighborhood_k_eq_3(current, lb, ub)
    # choose(3,3)*2^3 = 8 theoretical max
    assert 0 < len(n3) <= 8

    n4 = neighborhood_k_eq_4(current, lb, ub)
    n5 = neighborhood_k_eq_5(current, lb, ub)
    # For vector length 3 higher-k neighborhoods should be empty
    assert n4 == []
    assert n5 == []


def test_find_actual_neighbors_filters_duplicates_and_bounds():
    current = (0, 0)
    lb = (0, 0)
    ub = (1, 1)

    raw = [
        (0, 0),  # current (should be pruned if function excludes current)
        (1, 0),
        (0, 1),
        (1, 1),
        (1, 0),  # duplicate
        (2, 0),  # out of bounds
    ]

    filtered = find_actual_neighbors(raw, current, lb, ub)

    # Expect (1,0), (0,1), (1,1)
    assert set(filtered) == {(1, 0), (0, 1), (1, 1)}


def test_neighborhood_symmetry():
    current = (2, 2, 2)
    lb = (0, 0, 0)
    ub = (4, 4, 4)

    n1 = neighborhood_k_eq_1(current, lb, ub)
    # For each move +d there should be a corresponding -d unless at boundary
    plus_moves = [p for p in n1 if sum(pi - ci for pi, ci in zip(p, current)) > 0]
    minus_moves = [p for p in n1 if sum(pi - ci for pi, ci in zip(p, current)) < 0]
    assert len(plus_moves) == len(minus_moves)
