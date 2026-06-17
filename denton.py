"""
Proportional Denton temporal disaggregation (Denton 1971).

Reference: IMF Quarterly National Accounts Manual, Annex 6.1 (Bloem et al. 2001).
"""
import numpy as np


def denton_proportional(indicator: np.ndarray, benchmarks: np.ndarray) -> np.ndarray:
    """
    Disaggregate annual benchmarks to quarterly frequency using a quarterly
    indicator series.  Minimises sum of squared changes in the ratio q_t / p_t
    subject to exact annual aggregation constraints.

    Parameters
    ----------
    indicator  : 1-D array, length n = 4 * m.  Must be strictly positive.
    benchmarks : 1-D array of annual totals, length m.

    Returns
    -------
    q : 1-D array, length n.  Satisfies sum(q[4y : 4y+4]) == benchmarks[y].
    """
    p = np.asarray(indicator, dtype=float)
    b = np.asarray(benchmarks, dtype=float)
    n, m = len(p), len(b)

    if n != 4 * m:
        raise ValueError(f"len(indicator)={n} must equal 4*len(benchmarks)={4 * m}")
    if np.any(p <= 0):
        raise ValueError("indicator values must be strictly positive")

    # First-difference matrix D (n-1 × n)
    D = np.zeros((n - 1, n))
    for i in range(n - 1):
        D[i, i], D[i, i + 1] = -1.0, 1.0

    # Aggregation matrix J (m × n): J[y, 4y : 4y+4] = 1
    J = np.zeros((m, n))
    for y in range(m):
        J[y, 4 * y : 4 * y + 4] = 1.0

    W = np.diag(p)          # diagonal weight matrix
    H = D.T @ D             # n × n, rank n-1 (null space = span(1_n))

    # KKT bordered system — minimise z'Hz s.t. J·W·z = b, where q = p * z
    #   [2H + ε·I   W·J' ] [z  ]   [0]
    #   [J·W        0    ] [μ/2] = [b]
    # ε = 1e-10 regularises the singular H without affecting solution accuracy.
    K = np.zeros((n + m, n + m))
    K[:n, :n] = 2.0 * H + 1e-10 * np.eye(n)
    K[:n, n:] = W @ J.T
    K[n:, :n] = J @ W

    rhs = np.zeros(n + m)
    rhs[n:] = b

    sol = np.linalg.solve(K, rhs)
    q = p * sol[:n]

    # Enforce exact annual constraints (remove floating-point residuals)
    for y in range(m):
        s = q[4 * y : 4 * y + 4].sum()
        if abs(s) > 0:
            q[4 * y : 4 * y + 4] *= b[y] / s

    return q


def pro_rata(indicator: np.ndarray, benchmarks: np.ndarray) -> np.ndarray:
    """
    Simple pro-rata distribution — proportional within each year, no smoothing.
    Used for sanity checks; denton_proportional is the paper's method.
    """
    p = np.asarray(indicator, dtype=float)
    b = np.asarray(benchmarks, dtype=float)
    n, m = len(p), len(b)
    q = np.empty(n)
    for y in range(m):
        s = p[4 * y : 4 * y + 4].sum()
        q[4 * y : 4 * y + 4] = p[4 * y : 4 * y + 4] * (b[y] / s)
    return q
