"""
monte_carlo_uncertainty — §3.7 of the engine.

v0 implementation. Wraps a deterministic optimise_investment_pathway result
with three independent sampling passes:

  1. Latin Hypercube Sampling (LHS) of the declared uncertain inputs,
     re-ordered by the Iman-Conover rank-correlation algorithm to impose
     a Gaussian-copula correlation structure (default ρ=0.6 between gas
     and electricity prices). This pass produces the NPV distribution,
     carbon-trajectory cone, and tail risk metrics (VaR/CVaR).

  2. Saltelli sample (SALib) for first-order and total-order Sobol
     sensitivity indices on NPV.

  3. Morris elementary-effects sample (SALib) for screening sensitivity.

The pathway evaluator is a *closed-form* re-evaluation of the deterministic
pathway record — we do **NOT** re-run dispatch per trial. The closed form
applies multiplicative perturbations to the deterministic per-year cost and
carbon arrays, using the elec-vs-gas cost split observed in the pathway's
own first-full-stack dispatch. Inputs that cannot be captured by closed-form
multiplication (e.g. equipment ageing curves, second-order grid-mix shifts,
dispatch-policy changes) are explicitly excluded from sampling and declared
in the docstring as v0.3 enhancements.

Determinism:  same `seed` → same output bit-for-bit. Numpy RNG only.

Standards / methodology references:
  - methodology.md §3.7 (Monte Carlo uncertainty contract).
  - HM Treasury Green Book §A4 (Optimism Bias and risk).
  - Saltelli, A., Annoni, P. et al. (2010) — Variance based sensitivity
    analysis of model output, Computer Physics Comm. 181 (2):259–270.
  - Morris, M.D. (1991) — Factorial sampling plans for preliminary
    computational experiments, Technometrics 33 (2):161–174.
  - Iman, R.L. & Conover, W.J. (1982) — A distribution-free approach to
    inducing rank correlation among input variables, Comm. Stat. B 11.

Public surface: ``monte_carlo_uncertainty``.

v0 limitations (declared in `warnings`):
  - Closed-form pathway re-evaluation. Per-trial dispatch loop ships in
    v0.3 alongside the stochastic MILP optimiser.
  - Sobol second-order indices not computed (S1 + ST only). Second-order
    is materially expensive for the dairy_5mw runtime budget; ships v0.3.
  - HP-only capex multiplier is applied to total capex, not just HP rows
    (a small over-conservative bias in pathways with a large EB share).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Default uncertain-input distributions
# ---------------------------------------------------------------------------
#
# Each entry: name -> {kind, params}.
#   kind="triangular"  → params (low, mode, high)   — multiplier on baseline
#   kind="bernoulli"   → params (p,)                — outcome 0 or 1
#
# The multipliers are dimensionless; they perturb the deterministic-pathway
# arrays already produced by optimise_investment_pathway. Absolute price
# levels live in the deterministic baseline.

_DEFAULT_UNCERTAIN_INPUTS: dict[str, dict[str, Any]] = {
    "electricity_price": {
        "kind": "triangular", "params": (0.85, 1.00, 1.20),
        "comment": (
            "Multiplier on deterministic electricity tariff. Bounds set "
            "by DESNZ Energy and Emissions Projections 2024 low / central "
            "/ high case for non-domestic 2026-2040 (real-terms band)."
        ),
    },
    "gas_price": {
        "kind": "triangular", "params": (0.85, 1.00, 1.20),
        "comment": (
            "Multiplier on deterministic gas tariff; DESNZ wholesale gas "
            "low/central/high envelope 2026-2040 (real-terms band)."
        ),
    },
    "hp_capex_multiplier": {
        "kind": "triangular", "params": (0.90, 1.00, 1.20),
        "comment": (
            "Multiplier on total pathway capex. v0 applies this to ALL "
            "capex rows (not HP-only) — see module docstring caveat. "
            "Range from IETF Phase 3 award schedule (DESNZ 2024) and IEA "
            "Cost & Performance Database 2024 for industrial NH3 HPs."
        ),
    },
    "grid_carbon_intensity": {
        "kind": "triangular", "params": (0.70, 1.00, 1.20),
        "comment": (
            "Multiplier on grid intensity used in the deterministic "
            "pathway. Bounds derived from NESO FES 2025 Leading the Way "
            "vs Steady Progression scenarios for 2030."
        ),
    },
    "ietf_grant_outcome": {
        "kind": "bernoulli", "params": (0.70,),
        "comment": (
            "Probability of receiving IETF Phase 3 grant award. 1 → "
            "deterministic grant fraction applies; 0 → grant withdrawn "
            "(capex × 1.0). Default 0.7 — IETF Phase 2/3 published award "
            "rate (DESNZ 2024)."
        ),
    },
    "demand_growth": {
        "kind": "triangular", "params": (-0.005, 0.010, 0.025),
        "comment": (
            "Annual compound demand growth rate. Triangular bounded by "
            "BEIS industrial demand projections; mode 1%/yr mean industrial "
            "growth post-2026."
        ),
    },
}

_DEFAULT_CORRELATIONS: dict[tuple[str, str], float] = {
    ("gas_price", "electricity_price"): 0.60,
}

# UK Net-Zero linear-glide carbon target trajectory (default).
# 78% reduction by 2035 vs 1990; v0 places a linear glide between
# present-day (year 0) and zero (year horizon-1) for the *site*. The
# real Net-Zero target is sector- and policy-dependent; this default
# is documented and overridable via `carbon_target_trajectory`.
def _default_carbon_target_trajectory(
    horizon_years: int, baseline_year0_carbon: float
) -> list[float]:
    return [
        max(0.0, baseline_year0_carbon * (1.0 - y / max(horizon_years - 1, 1)))
        for y in range(horizon_years)
    ]


# ---------------------------------------------------------------------------
# Inverse-CDF helpers
# ---------------------------------------------------------------------------


def _inv_triangular(u: np.ndarray, low: float, mode: float, high: float) -> np.ndarray:
    """Inverse CDF of a triangular distribution. u ∈ [0,1]."""
    span = high - low
    if span <= 0:
        return np.full_like(u, low, dtype=float)
    fc = (mode - low) / span
    out = np.where(
        u < fc,
        low + np.sqrt(u * span * (mode - low)),
        high - np.sqrt((1.0 - u) * span * (high - mode)),
    )
    return out


def _inv_bernoulli(u: np.ndarray, p: float) -> np.ndarray:
    return (u < p).astype(float)


def _sample_marginal(rng: np.random.Generator, spec: dict[str, Any], n: int) -> np.ndarray:
    """Generate a stratified LHS sample of size n for one marginal."""
    # LHS strata with within-stratum jitter via the rng.
    strata = (np.arange(n) + rng.uniform(0.0, 1.0, size=n)) / n
    rng.shuffle(strata)
    kind = spec["kind"]
    params = spec["params"]
    if kind == "triangular":
        return _inv_triangular(strata, *params)
    if kind == "bernoulli":
        return _inv_bernoulli(strata, *params)
    raise ValueError(f"Unsupported distribution kind: {kind!r}")


# ---------------------------------------------------------------------------
# Iman-Conover rank-correlation imposition (Gaussian copula)
# ---------------------------------------------------------------------------


def _iman_conover(
    samples: np.ndarray,
    target_corr: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Reorder columns of `samples` (n × D, with already-correct marginals)
    so that the empirical Pearson correlation matches `target_corr` (D × D),
    via the Iman-Conover rank-reordering trick.

    Steps:
      1. Generate scratch normal scores Z (n × D iid).
      2. Apply Cholesky of target_corr so cov(Z') = target_corr.
      3. Use the rank order of each Z' column to permute the matching
         column of `samples` (preserves marginals exactly; only reorders
         pairings).
    """
    n, d = samples.shape
    if d == 1:
        return samples
    # Numerical floor on diagonals to keep Cholesky positive-definite when
    # target_corr is identity.
    target_corr = target_corr + 1e-12 * np.eye(d)
    L = np.linalg.cholesky(target_corr)
    z = rng.standard_normal(size=(n, d))
    # numpy 2.0.2 emits a spurious divide-by-zero warning from BLAS matmul on
    # some macOS builds even for finite inputs. Silence it explicitly so the
    # MC tool doesn't pollute caller stderr with a benign warning.
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        z_corr = z @ L.T  # rows are correlated normals with cov = target_corr
    out = np.empty_like(samples)
    for j in range(d):
        # Sort the marginal column ascending; place sorted values at the
        # rank positions of z_corr[:, j].
        sorted_marginal = np.sort(samples[:, j])
        ranks = np.argsort(np.argsort(z_corr[:, j]))
        out[:, j] = sorted_marginal[ranks]
    return out


# ---------------------------------------------------------------------------
# Closed-form pathway evaluator
# ---------------------------------------------------------------------------


@dataclass
class _PathwayContext:
    """Pre-extracted, immutable arrays needed for fast vectorised re-evaluation."""
    horizon_years: int
    discount_rate: float
    base_year: int
    ets_price_gbp_per_t: float
    grant_fraction_deterministic: float
    elec_share: float                         # of pathway dispatch cost
    gas_share: float
    elec_carbon_share: float                  # of pathway carbon
    actions_year_idx: np.ndarray              # int (n_actions,)
    actions_capex_gross: np.ndarray           # £
    actions_opex_year: np.ndarray             # £/yr
    pathway_dispatch_cost_y: np.ndarray       # £ (horizon_years,)
    pathway_carbon_y: np.ndarray              # tCO2e (horizon_years,)
    baseline_cost_y: np.ndarray               # £
    baseline_carbon_y: np.ndarray             # tCO2e


def _build_context(
    pathway_record: dict[str, Any],
    *,
    discount_rate: float,
    base_year: int,
    horizon_years: int,
    ets_price_gbp_per_t: float,
    grant_fraction_deterministic: float,
    baseline_annual_cost_gbp_per_year: Sequence[float],
    baseline_annual_carbon_t_per_year: Sequence[float],
) -> _PathwayContext:
    actions = pathway_record.get("actions") or []
    actions_year_idx = np.array([int(a["year_index"]) for a in actions], dtype=int)
    actions_capex_gross = np.array(
        [float(a.get("capex_gbp", 0.0)) for a in actions], dtype=float
    )
    actions_opex_year = np.array(
        [float(a.get("annual_opex_gbp", 0.0)) for a in actions], dtype=float
    )

    fsd = pathway_record.get("first_full_stack_dispatch") or {}
    asum = fsd.get("annual_summary") or {}
    elec_cost = float(asum.get("annual_electricity_cost_gbp", 0.0) or 0.0)
    gas_cost = float(asum.get("annual_gas_cost_gbp", 0.0) or 0.0)
    total_cost = elec_cost + gas_cost
    if total_cost > 0:
        elec_share = elec_cost / total_cost
    else:
        elec_share = 0.0
    gas_share = 1.0 - elec_share

    csum = fsd.get("carbon_summary") or {}
    s1 = float(csum.get("scope_1_t_co2e", 0.0) or 0.0)
    s2 = float(csum.get("scope_2_loc_t_co2e", 0.0) or 0.0)
    if (s1 + s2) > 0:
        elec_carbon_share = s2 / (s1 + s2)
    else:
        elec_carbon_share = 0.0

    pdc = list(pathway_record.get("annual_dispatch_cost_gbp") or [])
    pcc = list(pathway_record.get("annual_pathway_carbon_t_co2e") or [])
    # Pad / truncate to horizon for safety.
    pdc = (pdc + [pdc[-1] if pdc else 0.0] * horizon_years)[:horizon_years]
    pcc = (pcc + [pcc[-1] if pcc else 0.0] * horizon_years)[:horizon_years]
    bc = list(baseline_annual_cost_gbp_per_year)[:horizon_years]
    bcarb = list(baseline_annual_carbon_t_per_year)[:horizon_years]
    if len(bc) < horizon_years or len(bcarb) < horizon_years:
        raise ValueError(
            "baseline arrays must have length ≥ horizon_years; got "
            f"{len(bc)} cost / {len(bcarb)} carbon vs horizon={horizon_years}."
        )

    return _PathwayContext(
        horizon_years=horizon_years,
        discount_rate=discount_rate,
        base_year=base_year,
        ets_price_gbp_per_t=ets_price_gbp_per_t,
        grant_fraction_deterministic=grant_fraction_deterministic,
        elec_share=elec_share,
        gas_share=gas_share,
        elec_carbon_share=elec_carbon_share,
        actions_year_idx=actions_year_idx,
        actions_capex_gross=actions_capex_gross,
        actions_opex_year=actions_opex_year,
        pathway_dispatch_cost_y=np.array(pdc, dtype=float),
        pathway_carbon_y=np.array(pcc, dtype=float),
        baseline_cost_y=np.array(bc, dtype=float),
        baseline_carbon_y=np.array(bcarb, dtype=float),
    )


def _evaluate_trials(
    samples: np.ndarray,           # (n_trials, D)
    input_names: list[str],
    ctx: _PathwayContext,
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised closed-form NPV + carbon trajectory for every trial.

    Returns (npv_array (n_trials,), carbon_traj (n_trials, horizon_years)).

    Closed-form formula (per trial t, per year y):
      grant_factor_t       = 1 - declared_grant × ietf_grant_outcome_t
      capex_y_t            = sum_{a: a.year=y} action_capex_gross[a] × hp_capex_mult_t × grant_factor_t
      opex_y_t             = sum_{a: a.year ≤ y} action_opex_year[a] × hp_capex_mult_t
      demand_factor_y_t    = (1 + demand_growth_t)^y
      baseline_cost_y_t    = baseline_cost_y × demand_factor × gas_price_mult_t
      dispatch_cost_y_t    = pathway_dispatch_cost_y × demand_factor
                              × (elec_share × elec_price_mult_t + gas_share × gas_price_mult_t)
      pathway_carbon_y_t   = pathway_carbon_y × demand_factor
                              × (elec_carbon_share × grid_carbon_mult_t
                                 + (1 − elec_carbon_share) × 1.0)
      baseline_carbon_y_t  = baseline_carbon_y × demand_factor          (gas-only — no grid mult)
      carbon_value_y_t     = max(0, baseline_carbon_y_t − pathway_carbon_y_t) × ets_price
      cashflow_y_t         = (baseline_cost_y_t − dispatch_cost_y_t)
                             + carbon_value_y_t − capex_y_t − opex_y_t
      npv_t                = sum_y cashflow_y_t / (1+r)^y
    """
    n = samples.shape[0]
    H = ctx.horizon_years
    idx = {name: i for i, name in enumerate(input_names)}

    def _col(name: str, default: float) -> np.ndarray:
        if name in idx:
            return samples[:, idx[name]]
        return np.full(n, default, dtype=float)

    k_e = _col("electricity_price", 1.0)
    k_g = _col("gas_price", 1.0)
    k_capex = _col("hp_capex_multiplier", 1.0)
    k_carbon = _col("grid_carbon_intensity", 1.0)
    grant_outcome = _col("ietf_grant_outcome", 1.0)
    g_growth = _col("demand_growth", 0.0)

    grant_factor = 1.0 - ctx.grant_fraction_deterministic * grant_outcome
    # Year exponent matrix for demand growth.
    years = np.arange(H)
    demand_factor = (1.0 + g_growth[:, None]) ** years[None, :]   # (n, H)

    # Capex per year per trial.
    capex_y = np.zeros((n, H), dtype=float)
    for a_idx, year in enumerate(ctx.actions_year_idx):
        if 0 <= year < H:
            capex_y[:, year] += ctx.actions_capex_gross[a_idx] * k_capex * grant_factor

    # Opex per year per trial — opex starts in install-year and continues.
    opex_y = np.zeros((n, H), dtype=float)
    for a_idx, year in enumerate(ctx.actions_year_idx):
        if year < H:
            opex_y[:, year:] += (ctx.actions_opex_year[a_idx] * k_capex)[:, None]

    baseline_cost_y = ctx.baseline_cost_y[None, :] * demand_factor * k_g[:, None]
    dispatch_cost_y = (
        ctx.pathway_dispatch_cost_y[None, :] * demand_factor
        * (ctx.elec_share * k_e[:, None] + ctx.gas_share * k_g[:, None])
    )
    pathway_carbon_y = (
        ctx.pathway_carbon_y[None, :] * demand_factor
        * (ctx.elec_carbon_share * k_carbon[:, None] + (1.0 - ctx.elec_carbon_share))
    )
    baseline_carbon_y = ctx.baseline_carbon_y[None, :] * demand_factor

    abated_y = np.maximum(0.0, baseline_carbon_y - pathway_carbon_y)
    carbon_value_y = abated_y * ctx.ets_price_gbp_per_t

    cashflow_y = (
        (baseline_cost_y - dispatch_cost_y) + carbon_value_y - capex_y - opex_y
    )
    discount = (1.0 + ctx.discount_rate) ** years
    npv = np.sum(cashflow_y / discount[None, :], axis=1)
    return npv.astype(float), pathway_carbon_y.astype(float)


# ---------------------------------------------------------------------------
# Sobol + Morris (SALib)
# ---------------------------------------------------------------------------


def _build_salib_problem(
    uncertain_inputs: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Build a SALib `problem` dict in U(0,1) coordinates. The model
    evaluator transforms each uniform column to its declared marginal."""
    names = list(uncertain_inputs.keys())
    bounds = [[0.0, 1.0]] * len(names)
    return {"num_vars": len(names), "names": names, "bounds": bounds}, names


def _u_to_inputs(
    u_samples: np.ndarray, uncertain_inputs: dict[str, dict[str, Any]]
) -> tuple[np.ndarray, list[str]]:
    """Map a (M, D) uniform sample (e.g. Saltelli or Morris) to the
    declared-distribution input space (no copula correlation imposed —
    Sobol/Morris assume independent inputs by construction)."""
    names = list(uncertain_inputs.keys())
    out = np.empty_like(u_samples, dtype=float)
    for j, name in enumerate(names):
        spec = uncertain_inputs[name]
        u = u_samples[:, j]
        if spec["kind"] == "triangular":
            out[:, j] = _inv_triangular(u, *spec["params"])
        elif spec["kind"] == "bernoulli":
            out[:, j] = _inv_bernoulli(u, *spec["params"])
        else:
            out[:, j] = u
    return out, names


def _run_sobol(
    ctx: _PathwayContext,
    uncertain_inputs: dict[str, dict[str, Any]],
    *,
    base_n: int = 256,
    seed: int = 42,
) -> dict[str, Any]:
    """Saltelli sample → closed-form pathway → SALib first/total-order Sobol.
    Returns dict with 'S1', 'ST' (lists in input order) plus metadata."""
    from SALib.sample import sobol as sobol_sample
    from SALib.analyze import sobol as sobol_analyze

    problem, names = _build_salib_problem(uncertain_inputs)
    u = sobol_sample.sample(
        problem, base_n, calc_second_order=False, seed=seed,
    )
    inputs, _ = _u_to_inputs(u, uncertain_inputs)
    npv, _ = _evaluate_trials(inputs, names, ctx)
    si = sobol_analyze.analyze(
        problem, npv, calc_second_order=False, seed=seed, print_to_console=False,
    )
    return {
        "S1": [float(x) for x in si["S1"]],
        "ST": [float(x) for x in si["ST"]],
        "S1_conf": [float(x) for x in si["S1_conf"]],
        "ST_conf": [float(x) for x in si["ST_conf"]],
        "names": names,
        "n_model_evaluations": int(u.shape[0]),
        "base_n": base_n,
    }


def _run_morris(
    ctx: _PathwayContext,
    uncertain_inputs: dict[str, dict[str, Any]],
    *,
    n_trajectories: int = 30,
    levels: int = 4,
    seed: int = 42,
) -> dict[str, Any]:
    """Morris elementary-effects sample → closed-form pathway → mu, mu_star, sigma."""
    from SALib.sample import morris as morris_sample
    from SALib.analyze import morris as morris_analyze

    problem, names = _build_salib_problem(uncertain_inputs)
    u = morris_sample.sample(
        problem, n_trajectories, num_levels=levels, seed=seed,
    )
    inputs, _ = _u_to_inputs(u, uncertain_inputs)
    npv, _ = _evaluate_trials(inputs, names, ctx)
    mi = morris_analyze.analyze(
        problem, u, npv, conf_level=0.95, print_to_console=False,
        num_levels=levels, seed=seed,
    )
    return {
        "names": names,
        "mu": [float(x) for x in mi["mu"]],
        "mu_star": [float(x) for x in mi["mu_star"]],
        "sigma": [float(x) for x in mi["sigma"]],
        "n_model_evaluations": int(u.shape[0]),
        "n_trajectories": n_trajectories,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def monte_carlo_uncertainty(
    pathway: dict[str, Any],
    *,
    pathway_name: str = "balanced",
    baseline_annual_cost_gbp_per_year: Sequence[float],
    baseline_annual_carbon_t_per_year: Sequence[float],
    uncertain_inputs: dict[str, dict[str, Any]] | None = None,
    correlations: dict[tuple[str, str], float] | None = None,
    n_trials: int = 1000,
    seed: int = 42,
    carbon_target_trajectory: Sequence[float] | None = None,
    sobol_base_n: int = 256,
    morris_trajectories: int = 30,
) -> dict[str, Any]:
    """Run §3.7 Monte Carlo uncertainty on a deterministic pathway result.

    Args:
      pathway: full output dict of `optimise_investment_pathway`. The named
        pathway selected via `pathway_name` is the one stress-tested.
      pathway_name: one of 'conservative', 'balanced', 'aggressive'.
      baseline_annual_cost_gbp_per_year: gas-only counterfactual cost per
        year (length = horizon_years). Caller computes (regenerate script
        runs the same gas-only dispatch the optimiser used).
      baseline_annual_carbon_t_per_year: gas-only counterfactual carbon
        per year (tCO2e).
      uncertain_inputs: dict {name: {kind, params, comment}}; defaults to
        the v0 schedule documented at module top.
      correlations: dict {(name_a, name_b): rho}; defaults to gas↔elec=0.6
        Gaussian copula (Iman-Conover rank-reorder).
      n_trials: LHS sample size for the main NPV / carbon distribution.
      seed: numpy RNG seed; same seed → bit-identical output.
      carbon_target_trajectory: per-year tCO2e ceiling for `prob_carbon_target_met`.
        Default = linear glide from baseline year-0 to zero at horizon-end.
      sobol_base_n: Saltelli base sample size (Sobol pass uses N*(2D+2)
        evaluations).
      morris_trajectories: Morris EE trajectory count.

    Returns: dict matching the §3.7 contract — see methodology.md.

    v0 limitations (also returned in `warnings`):
      - Closed-form re-evaluation: no per-trial dispatch loop.
      - HP-only capex multiplier applied to total capex (small bias for
        EB-heavy pathways).
      - Sobol second-order indices not computed.
      - `pathway_carbon_y` perturbed by grid-intensity multiplier
        proportionally to its electricity share — neglects HP COP shifts
        from grid-decarbonisation interactions; ships v0.3.
    """
    if pathway_name not in (pathway.get("pathways") or {}):
        raise ValueError(
            f"pathway_name {pathway_name!r} not present in pathway result; "
            f"available: {list((pathway.get('pathways') or {}).keys())}"
        )
    pw_record = pathway["pathways"][pathway_name]
    if pw_record is None:
        raise ValueError(
            f"pathway_name {pathway_name!r} is None in the input pathway result."
        )

    horizon_years = int(pathway.get("planning_horizon_years", 15))
    discount_rate = float(pathway.get("discount_rate_real", 0.08))
    base_year = int(pathway.get("base_year", 2026))
    ets_price = float(pathway.get("ets_allowance_price_gbp_per_tco2e", 0.0))
    grant_fraction = float(pathway.get("ietf_grant_fraction", 0.0))

    uncertain = dict(uncertain_inputs) if uncertain_inputs else {
        k: dict(v) for k, v in _DEFAULT_UNCERTAIN_INPUTS.items()
    }
    corrs = dict(correlations) if correlations is not None else dict(_DEFAULT_CORRELATIONS)

    ctx = _build_context(
        pw_record,
        discount_rate=discount_rate,
        base_year=base_year,
        horizon_years=horizon_years,
        ets_price_gbp_per_t=ets_price,
        grant_fraction_deterministic=grant_fraction,
        baseline_annual_cost_gbp_per_year=baseline_annual_cost_gbp_per_year,
        baseline_annual_carbon_t_per_year=baseline_annual_carbon_t_per_year,
    )

    rng = np.random.default_rng(seed)

    # ---- Pass 1: LHS + Iman-Conover copula → main NPV / carbon distribution ----
    names = list(uncertain.keys())
    D = len(names)
    samples = np.empty((n_trials, D), dtype=float)
    for j, n in enumerate(names):
        samples[:, j] = _sample_marginal(rng, uncertain[n], n_trials)

    target_corr = np.eye(D)
    name_index = {n: i for i, n in enumerate(names)}
    realised_target_pairs: list[tuple[str, str, float]] = []
    for (a, b), rho in corrs.items():
        if a in name_index and b in name_index:
            i, j = name_index[a], name_index[b]
            target_corr[i, j] = rho
            target_corr[j, i] = rho
            realised_target_pairs.append((a, b, float(rho)))

    samples = _iman_conover(samples, target_corr, rng)

    npv_samples, carbon_traj = _evaluate_trials(samples, names, ctx)

    # ---- NPV distribution ------------------------------------------------
    p10 = float(np.percentile(npv_samples, 10))
    p50 = float(np.percentile(npv_samples, 50))
    p90 = float(np.percentile(npv_samples, 90))
    mean_npv = float(np.mean(npv_samples))
    std_npv = float(np.std(npv_samples, ddof=1))
    # Skewness — Fisher-Pearson moment coefficient.
    centered = npv_samples - mean_npv
    m3 = float(np.mean(centered ** 3))
    m2 = float(np.mean(centered ** 2))
    skew_npv = float(m3 / (m2 ** 1.5)) if m2 > 0 else 0.0

    # ---- Tail risk: VaR_95 / CVaR_95 (loss convention — positive numbers) ----
    var_threshold_npv = float(np.percentile(npv_samples, 5))
    var_95_npv = float(-var_threshold_npv)              # loss (£) at 95% level
    tail = npv_samples[npv_samples <= var_threshold_npv]
    if tail.size > 0:
        cvar_95_npv = float(-np.mean(tail))
    else:
        cvar_95_npv = float(-var_threshold_npv)

    # ---- Carbon trajectory cone -----------------------------------------
    carbon_p10 = [float(x) for x in np.percentile(carbon_traj, 10, axis=0)]
    carbon_p50 = [float(x) for x in np.percentile(carbon_traj, 50, axis=0)]
    carbon_p90 = [float(x) for x in np.percentile(carbon_traj, 90, axis=0)]

    # ---- Probability of NPV positive + carbon target met ----------------
    prob_npv_positive = float(np.mean(npv_samples > 0))

    if carbon_target_trajectory is None:
        baseline_y0 = float(ctx.baseline_carbon_y[0])
        carbon_target_trajectory = _default_carbon_target_trajectory(
            horizon_years, baseline_y0
        )
    target_arr = np.array(carbon_target_trajectory[:horizon_years], dtype=float)
    # Per-trial: target met if pathway carbon ≤ target across ALL years.
    met = np.all(carbon_traj <= target_arr[None, :], axis=1)
    prob_carbon_target_met = float(np.mean(met))

    # ---- Realised-correlation check -------------------------------------
    correlation_check = {
        "target": [
            {"a": a, "b": b, "rho": rho}
            for (a, b, rho) in realised_target_pairs
        ],
        "realised": [],
        "tolerance": 0.05,
        "ok": True,
    }
    for (a, b, rho_target) in realised_target_pairs:
        i, j = name_index[a], name_index[b]
        rho_real = float(np.corrcoef(samples[:, i], samples[:, j])[0, 1])
        correlation_check["realised"].append(
            {"a": a, "b": b, "rho": rho_real, "delta": abs(rho_real - rho_target)}
        )
        if abs(rho_real - rho_target) >= 0.05:
            correlation_check["ok"] = False

    # ---- Pass 2: Sobol --------------------------------------------------
    sobol_block = _run_sobol(ctx, uncertain, base_n=sobol_base_n, seed=seed)
    sobol_first = {n: v for n, v in zip(sobol_block["names"], sobol_block["S1"])}
    sobol_total = {n: v for n, v in zip(sobol_block["names"], sobol_block["ST"])}
    sobol_top_total = sorted(sobol_total.items(), key=lambda kv: -kv[1])

    # ---- Pass 3: Morris -------------------------------------------------
    morris_block = _run_morris(
        ctx, uncertain, n_trajectories=morris_trajectories, seed=seed,
    )
    morris_by_name = {
        n: {"mu": mu, "mu_star": mus, "sigma": sg}
        for n, mu, mus, sg in zip(
            morris_block["names"], morris_block["mu"],
            morris_block["mu_star"], morris_block["sigma"],
        )
    }

    warnings_out: list[dict[str, Any]] = [
        {
            "severity": "advisory",
            "code": "mc_closed_form_v0",
            "message": (
                "v0 Monte Carlo uses a closed-form re-evaluation of the "
                "deterministic pathway record (no per-trial dispatch). "
                "v0.3 will wire a per-trial dispatch loop."
            ),
        },
        {
            "severity": "advisory",
            "code": "mc_sobol_second_order_skipped",
            "message": (
                "Sobol second-order indices not computed in v0 (S1 + ST "
                "only). Second-order ships v0.3."
            ),
        },
        {
            "severity": "advisory",
            "code": "mc_capex_multiplier_total_not_hp_only",
            "message": (
                "hp_capex_multiplier applies to the pathway's TOTAL capex "
                "(not HP rows alone) in v0 — small over-conservative bias "
                "for pathways with a large electrode-boiler share."
            ),
        },
    ]
    if not correlation_check["ok"]:
        warnings_out.append({
            "severity": "high",
            "code": "mc_correlation_closure_failed",
            "message": (
                "Realised Pearson correlation deviates from target by ≥ 0.05; "
                "raise n_trials or check the Iman-Conover trace."
            ),
        })

    return {
        "n_trials": int(n_trials),
        "seed": int(seed),
        "pathway_name": pathway_name,
        "horizon_years": horizon_years,
        "base_year": base_year,
        "discount_rate_real": discount_rate,
        "ets_allowance_price_gbp_per_tco2e": ets_price,
        "ietf_grant_fraction_deterministic": grant_fraction,
        "uncertain_inputs": uncertain,
        "correlations_target": [
            {"a": a, "b": b, "rho": rho}
            for (a, b, rho) in realised_target_pairs
        ],
        "npv_distribution": {
            "p10_gbp": p10,
            "p50_gbp": p50,
            "p90_gbp": p90,
            "mean_gbp": mean_npv,
            "stdev_gbp": std_npv,
            "skew": skew_npv,
            "samples_gbp": [float(x) for x in npv_samples],
        },
        "carbon_trajectory_uncertainty": {
            "calendar_years": [base_year + y for y in range(horizon_years)],
            "p10_t_co2e_per_year": carbon_p10,
            "p50_t_co2e_per_year": carbon_p50,
            "p90_t_co2e_per_year": carbon_p90,
        },
        "prob_npv_positive": prob_npv_positive,
        "prob_carbon_target_met": prob_carbon_target_met,
        "carbon_target_trajectory_t_co2e_per_year": [
            float(x) for x in target_arr
        ],
        "var_95_npv_gbp": var_95_npv,
        "cvar_95_npv_gbp": cvar_95_npv,
        "sobol": {
            "first_order": sobol_first,
            "total_order": sobol_total,
            "top_total_order": [
                {"name": n, "value": float(v)} for n, v in sobol_top_total
            ],
            "n_model_evaluations": sobol_block["n_model_evaluations"],
            "base_n": sobol_block["base_n"],
            "S1_conf": dict(zip(sobol_block["names"], sobol_block["S1_conf"])),
            "ST_conf": dict(zip(sobol_block["names"], sobol_block["ST_conf"])),
        },
        "morris": {
            "by_name": morris_by_name,
            "n_model_evaluations": morris_block["n_model_evaluations"],
            "n_trajectories": morris_block["n_trajectories"],
        },
        "correlation_check": correlation_check,
        "method_reference": (
            "Three-pass Monte Carlo: (1) Latin Hypercube Sampling with "
            "Iman-Conover rank-correlation reordering for the main NPV / "
            "carbon distribution; (2) Saltelli-2010 sample for first- and "
            "total-order Sobol indices; (3) Morris-1991 elementary effects "
            "for screening sensitivity. Inner loop is a closed-form "
            "perturbation of the deterministic pathway result (no per-"
            "trial dispatch in v0). Risk metrics: P10/P50/P90, VaR_95 and "
            "CVaR_95 on NPV under the loss-convention (positive £ losses)."
        ),
        "standards_cited": [
            "Saltelli et al. 2010 — Variance-based global sensitivity analysis",
            "Morris 1991 — Factorial sampling plans for screening",
            "Iman & Conover 1982 — Rank-correlation reordering for copula sampling",
            "HM Treasury Green Book §A4 — Optimism Bias and risk appraisal",
            "DESNZ Energy and Emissions Projections 2024 — price scenario envelope",
            "NESO Future Energy Scenarios 2025 — grid intensity envelope",
        ],
        "provenance": [
            {
                "calculation": "LHS + Iman-Conover copula sampling",
                "method": (
                    "Latin Hypercube Sampling with within-stratum jitter; "
                    "rank reorder via Cholesky-on-target-correlation Gaussian "
                    "copula (Iman-Conover 1982). Marginals: triangular and "
                    "Bernoulli per uncertain_inputs spec."
                ),
                "source": "decarb.engine.uncertainty._sample_marginal + _iman_conover",
                "n_trials": n_trials,
                "seed": seed,
            },
            {
                "calculation": "Closed-form pathway re-evaluation",
                "method": (
                    "Per-trial multiplicative perturbation of the "
                    "deterministic pathway record's annual_dispatch_cost_gbp "
                    "/ annual_pathway_carbon_t_co2e arrays. Electricity vs "
                    "gas split read from pathway.first_full_stack_dispatch."
                    "annual_summary; carbon split from carbon_summary."
                ),
                "source": "decarb.engine.uncertainty._evaluate_trials",
            },
            {
                "calculation": "Sobol first / total-order indices",
                "method": (
                    "Saltelli sample (calc_second_order=False) → SALib "
                    f"sobol.analyze; base_n={sobol_base_n}, "
                    f"n_evaluations={sobol_block['n_model_evaluations']}."
                ),
                "source": "SALib.sample.sobol + SALib.analyze.sobol",
            },
            {
                "calculation": "Morris elementary effects",
                "method": (
                    f"Morris sample with {morris_trajectories} trajectories "
                    "→ SALib morris.analyze (mu, mu_star, sigma)."
                ),
                "source": "SALib.sample.morris + SALib.analyze.morris",
            },
            {
                "calculation": "VaR_95 / CVaR_95 on NPV",
                "method": (
                    "Loss convention: VaR_95 = -percentile(npv, 5); "
                    "CVaR_95 = -mean(npv | npv ≤ percentile_5)."
                ),
            },
            {
                "calculation": "prob_carbon_target_met",
                "method": (
                    "Per-trial: target met iff pathway_carbon_y ≤ "
                    "target_y for all y in horizon. Default target = linear "
                    "glide from baseline year-0 carbon to zero at horizon-end."
                ),
            },
            {
                "calculation": "correlation_check",
                "method": (
                    "Realised Pearson ρ between sampled gas_price and "
                    "electricity_price columns; tolerance 0.05 vs target."
                ),
            },
        ],
        "warnings": warnings_out,
    }


__all__ = ["monte_carlo_uncertainty"]
