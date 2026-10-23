"""Monte Carlo valuation of a pass-through MBS (FN FS9548).

Everything is discrete and monthly, following the course framework:

    1. simulate monthly short-rate paths, calibrated so the average path
       discount factor reprices the Treasury zero curve;
    2. project prepayments with a PSA model whose speed responds to the
       simulated rate shock (so cash flows differ by path);
    3. build investor cash flows (pass-through interest + scheduled
       principal + prepaid principal) on every path;
    4. discount each path's cash flows with that path's cumulative discount
       factors and average across paths;
    5. (Part II) replace promised cash flows by expected cash flows using a
       guarantor survival curve and recovery rate.

All functions are vectorised over paths: arrays are shaped (n_paths, T).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
def load_inputs(path: Path = DATA_DIR / "pool_inputs.json") -> dict:
    with open(path) as f:
        return json.load(f)


def price_from_32nds(handle: int, thirty_seconds: float) -> float:
    """97-23 5/8 -> 97 + 23.625/32."""
    return handle + thirty_seconds / 32.0


def load_gt10(path: Path = DATA_DIR / "GT10_monthly_bloomberg.xlsx") -> pd.Series:
    """Month-end 10-year Treasury yields (percent) exported from Bloomberg GT10 Govt."""
    raw = pd.read_excel(path, header=None, skiprows=2, names=["date", "yield_pct"])
    raw = raw.dropna()
    raw["date"] = pd.to_datetime(raw["date"])
    return raw.set_index("date")["yield_pct"].astype(float).sort_index()


def estimate_monthly_vol(gt10: pd.Series, end: str = "2026-04-30") -> tuple[float, pd.Series]:
    """Sample st. dev. of month-over-month changes in the 10y yield, as a decimal.

    Observations after the valuation date are excluded (the Bloomberg export
    also contains a 5 May 2026 print, which is not a month-end).
    """
    s = gt10[gt10.index <= pd.Timestamp(end)]
    changes = s.diff().dropna() / 100.0
    return float(changes.std(ddof=1)), changes


# --------------------------------------------------------------------------
# Treasury zero curve
# --------------------------------------------------------------------------
def bootstrap_zero_curve(par_curve: dict, horizon_years: float = 5.0) -> pd.DataFrame:
    """Bootstrap semiannual zero-coupon discount factors from Treasury par yields.

    Bills (<= 1y) are treated as zero-coupon bond-equivalent yields; for
    1.5y..horizon the par yield is linearly interpolated between the quoted
    tenors and the discount factor is solved from the par-bond condition
        1 = c * sum_{k<n} P(t_k) + (1 + c) * P(t_n),   c = y/2.
    """
    tenors = np.array(sorted(float(k) for k in par_curve))
    yields = np.array([par_curve[k] for k in sorted(par_curve, key=float)])

    def par(t):
        return float(np.interp(t, tenors, yields))

    rows = []
    for t in (0.25, 0.5, 1.0):
        y = par(t)
        rows.append((t, y, (1 + y / 2) ** (-2 * t)))

    semi = {0.5: rows[1][2], 1.0: rows[2][2]}
    t = 1.5
    while t <= horizon_years + 1e-9:
        y = par(t)
        c = y / 2
        annuity = sum(semi[s] for s in semi if s < t)
        p = (1 - c * annuity) / (1 + c)
        semi[t] = p
        rows.append((t, y, p))
        t = round(t + 0.5, 10)

    df = pd.DataFrame(rows, columns=["years", "par_yield", "discount_factor"])
    df["zero_cc"] = -np.log(df["discount_factor"]) / df["years"]
    df["zero_bey"] = 2 * (df["discount_factor"] ** (-1 / (2 * df["years"])) - 1)
    return df


def monthly_discount_factors(zero_curve: pd.DataFrame, T: int) -> np.ndarray:
    """P(0, t/12) for t = 0..T, by linear interpolation of continuously-compounded zero rates."""
    t = np.arange(T + 1) / 12.0
    z = np.interp(t, zero_curve["years"], zero_curve["zero_cc"])  # flat before 3m
    return np.exp(-z * t)


# --------------------------------------------------------------------------
# Interest-rate paths
# --------------------------------------------------------------------------
def simulate_shocks(n_paths: int, T: int, seed: int = 2026, antithetic: bool = True) -> np.ndarray:
    """Standard-normal monthly shocks, shape (n_paths, T). Antithetic pairs halve the noise."""
    rng = np.random.default_rng(seed)
    if antithetic:
        half = rng.standard_normal((n_paths // 2, T))
        return np.vstack([half, -half])
    return rng.standard_normal((n_paths, T))


@dataclass
class RatePaths:
    """Monthly short rates r[:, k] apply from month k to k+1 (annualised, monthly compounding)."""
    rates: np.ndarray          # (n, T)  r_0 .. r_{T-1}
    theta: np.ndarray          # (T,)    calibrated drift level, theta_0 = r_0
    shock: np.ndarray          # (n, T)  sigma * W_k, cumulative shock, shock[:, 0] = 0
    sigma: float
    market_df: np.ndarray      # (T+1,)  P(0, t)
    eps: np.ndarray = field(repr=False, default=None)

    @property
    def n_paths(self) -> int:
        return self.rates.shape[0]

    @property
    def T(self) -> int:
        return self.rates.shape[1]


def calibrate_short_rate_paths(eps: np.ndarray, sigma: float, market_df: np.ndarray,
                               floor: float = 0.0) -> RatePaths:
    """Discrete arbitrage-free short-rate paths (Ho-Lee style, calibrated by Monte Carlo).

        r_k^(i) = max(floor, theta_k + sigma * W_k^(i)),   W_k = eps_1 + ... + eps_k,

    with r_0 equal to the 1-month rate implied by the zero curve. theta_k is
    solved month by month so that the average simulated discount factor equals
    the Treasury discount factor P(0, k+1) exactly.
    """
    n, T = eps.shape
    W = np.zeros((n, T))
    W[:, 1:] = np.cumsum(eps[:, : T - 1], axis=1)
    shock = sigma * W

    rates = np.empty((n, T))
    theta = np.empty(T)
    theta[0] = 12 * (market_df[0] / market_df[1] - 1)
    rates[:, 0] = max(floor, theta[0])
    D = 1.0 / (1 + rates[:, 0] / 12)                     # D_1 on each path

    for k in range(1, T):
        target = market_df[k + 1]

        def gap(th):
            r = np.maximum(floor, th + shock[:, k])
            return np.mean(D / (1 + r / 12)) - target

        theta[k] = brentq(gap, -0.20, 0.40, xtol=1e-14)
        rates[:, k] = np.maximum(floor, theta[k] + shock[:, k])
        D = D / (1 + rates[:, k] / 12)

    return RatePaths(rates=rates, theta=theta, shock=shock, sigma=sigma,
                     market_df=market_df, eps=eps)


def path_discount_factors(rates: np.ndarray, spread: float = 0.0) -> np.ndarray:
    """D_t = prod_{k=0}^{t-1} 1/(1 + (r_k + spread)/12) for t = 1..T, shape (n, T)."""
    return np.cumprod(1.0 / (1 + (rates + spread) / 12), axis=1)


def payment_discount_factors(rates: np.ndarray, spread: float = 0.0, lag: float = 25 / 30) -> np.ndarray:
    """Discount factors for the actual MBS payment dates.

    The cash flow for accrual month t is paid on the 25th of the following
    month, i.e. lag = 25/30 of a month after the end of month t-1 measured
    from the 30 Apr valuation date:  DF_t = D_{t-1} * (1 + (r_{t-1}+s)/12)^(-lag).
    lag = 1 gives the simple end-of-month convention.
    """
    D_end = path_discount_factors(rates, spread)
    D_prev = np.hstack([np.ones((rates.shape[0], 1)), D_end[:, :-1]])
    return D_prev * (1 + (rates + spread) / 12) ** (-lag)


# --------------------------------------------------------------------------
# Prepayments and cash flows
# --------------------------------------------------------------------------
def psa_cpr(loan_age_months: np.ndarray, psa: float) -> np.ndarray:
    """PSA benchmark: CPR = 6% * min(age, 30)/30, scaled by the PSA speed."""
    base = 0.06 * np.minimum(loan_age_months, 30) / 30.0
    return base * psa


def cpr_to_smm(cpr: np.ndarray) -> np.ndarray:
    return 1 - (1 - cpr) ** (1 / 12)


def refi_multiplier(rate_change: np.ndarray, beta: float, lo: float = 0.75, hi: float = 1.75) -> np.ndarray:
    """PSA multiplier from the change in long rates since the valuation date.

    rate_change is the simulated cumulative shock sigma*W (decimal). A 100bp
    fall in rates raises the speed by beta*100%; a rise slows it (lock-in),
    bounded to [lo, hi]. beta = 0 recovers a pure, path-independent PSA model.
    """
    return np.clip(1 - beta * rate_change / 0.01, lo, hi)


@dataclass
class CashFlows:
    begin_balance: np.ndarray
    scheduled_payment: np.ndarray
    gross_interest: np.ndarray
    investor_interest: np.ndarray
    scheduled_principal: np.ndarray
    cpr: np.ndarray
    smm: np.ndarray
    prepayment: np.ndarray
    total_principal: np.ndarray
    end_balance: np.ndarray
    cash_flow: np.ndarray


def project_cash_flows(inputs: dict, psa: float, rate_change: np.ndarray | None = None,
                       beta: float = 0.0, n_paths: int | None = None) -> CashFlows:
    """Investor cash flows for every path, months 1..WAM.

    rate_change[:, t-1] (the shock known at the start of month t) drives the
    prepayment speed in month t. With rate_change None or beta 0 every path has
    the same cash flows.
    """
    T = inputs["wam_months"]
    if rate_change is None:
        rate_change = np.zeros((n_paths or 1, T))
    n = rate_change.shape[0]

    wac_m = inputs["wac"] / 12
    ptr_m = inputs["coupon"] / 12
    age = inputs["wala_months"] + np.arange(1, T + 1)
    cpr_path = np.minimum(psa_cpr(age, psa)[None, :] * refi_multiplier(rate_change, beta), 0.999)
    smm_path = cpr_to_smm(cpr_path)

    out = {k: np.zeros((n, T)) for k in CashFlows.__dataclass_fields__}
    B = np.full(n, float(inputs["current_balance"]))
    for t in range(T):
        remaining = T - t
        pmt = B * wac_m / (1 - (1 + wac_m) ** (-remaining))
        gross = B * wac_m
        inv = B * ptr_m
        sched = np.minimum(pmt - gross, B)
        prepay = smm_path[:, t] * (B - sched)
        principal = sched + prepay
        end = np.maximum(B - principal, 0.0)

        out["begin_balance"][:, t] = B
        out["scheduled_payment"][:, t] = pmt
        out["gross_interest"][:, t] = gross
        out["investor_interest"][:, t] = inv
        out["scheduled_principal"][:, t] = sched
        out["cpr"][:, t] = cpr_path[:, t]
        out["smm"][:, t] = smm_path[:, t]
        out["prepayment"][:, t] = prepay
        out["total_principal"][:, t] = principal
        out["end_balance"][:, t] = end
        out["cash_flow"][:, t] = inv + principal
        B = end
    return CashFlows(**out)


# --------------------------------------------------------------------------
# Valuation
# --------------------------------------------------------------------------
def path_prices(cash_flow: np.ndarray, discount: np.ndarray, balance: float) -> np.ndarray:
    """Price per 100 of current face on each path."""
    return (cash_flow * discount).sum(axis=1) / balance * 100


def summarize(prices: np.ndarray, antithetic: bool = True) -> dict:
    """Mean, standard error and 95% CI. With antithetic sampling the pair averages are the iid draws."""
    if antithetic:
        h = len(prices) // 2
        draws = 0.5 * (prices[:h] + prices[h:])
    else:
        draws = prices
    mean = float(prices.mean())
    se = float(draws.std(ddof=1) / np.sqrt(len(draws)))
    return {"price": mean, "std_error": se, "ci_low": mean - 1.96 * se, "ci_high": mean + 1.96 * se,
            "path_std": float(prices.std(ddof=1)), "n_paths": int(len(prices))}


def accrued_interest(inputs: dict) -> float:
    """Accrued coupon per 100 from the 1st of the month to settlement (30/360)."""
    return inputs["coupon"] / 12 * inputs["accrued_days_30_360"] / 30 * 100


def solve_oas(cash_flow: np.ndarray, rates: np.ndarray, balance: float, target_full_price: float,
              lag: float = 25 / 30) -> float:
    """Constant spread over the simulated short rates that equates the mean model full price to the target."""
    def gap(s):
        return path_prices(cash_flow, payment_discount_factors(rates, s, lag), balance).mean() - target_full_price
    return brentq(gap, -0.05, 0.10, xtol=1e-12)


# --------------------------------------------------------------------------
# Credit risk (Part II): expected cash-flow approach
# --------------------------------------------------------------------------
def survival_curve(pd_annual: float, T: int) -> np.ndarray:
    """S_t = (1 - PD_annual)^(t/12) for t = 0..T (constant monthly hazard)."""
    return (1 - pd_annual) ** (np.arange(T + 1) / 12.0)


def expected_cash_flows(cf: CashFlows, pd_annual: float, recovery: float) -> tuple[np.ndarray, np.ndarray]:
    """E[CF_t] = S_t * CF_t + (S_{t-1} - S_t) * R * B_{t-1}.

    If the guarantor survives through month t the investor receives the
    promised cash flow; if it defaults during month t the investor recovers
    R times the outstanding principal claim B_{t-1} and nothing afterwards.
    Returns (expected cash flows, survival curve S_0..S_T).
    """
    T = cf.cash_flow.shape[1]
    S = survival_curve(pd_annual, T)
    marginal = S[:-1] - S[1:]
    ecf = S[1:] * cf.cash_flow + marginal * recovery * cf.begin_balance
    return ecf, S


# --------------------------------------------------------------------------
# Base case set-up shared by the notebooks
# --------------------------------------------------------------------------
BASE = {
    "n_paths": 10_000,
    "seed": 2026,
    "psa": 1.78,
    "beta": 0.20,
    "pd_annual": 0.0010,
    "recovery": 0.40,
}


def build_base_case(n_paths: int = BASE["n_paths"], seed: int = BASE["seed"], sigma: float | None = None,
                    curve_shift: float = 0.0) -> dict:
    """Load data, estimate volatility, bootstrap the curve and calibrate rate paths."""
    inputs = load_inputs()
    gt10 = load_gt10()
    sigma_hat, _ = estimate_monthly_vol(gt10, inputs["valuation_date"])
    sigma = sigma_hat if sigma is None else sigma
    curve = {k: v + curve_shift for k, v in inputs["treasury_par_curve"].items()}
    zero = bootstrap_zero_curve(curve)
    T = inputs["wam_months"]
    mkt_df = monthly_discount_factors(zero, T)
    eps = simulate_shocks(n_paths, T, seed)
    paths = calibrate_short_rate_paths(eps, sigma, mkt_df)
    return {"inputs": inputs, "gt10": gt10, "sigma": sigma, "sigma_hat": sigma_hat,
            "zero_curve": zero, "paths": paths}


def _with_clean(summary: dict, inputs: dict) -> dict:
    ai = accrued_interest(inputs)
    summary["accrued"] = ai
    summary["full_price"] = summary["price"]
    summary["clean_price"] = summary["price"] - ai
    return summary


def value_agency(case: dict, psa: float = BASE["psa"], beta: float = BASE["beta"], spread: float = 0.0):
    """Part I value per 100 on the case's paths. Returns (summary dict, per-path full prices, CashFlows).

    summary["price"] / ["full_price"] is the value including accrued interest
    (what the cash flows are worth); summary["clean_price"] is comparable with
    the quoted BVAL price.
    """
    inputs, paths = case["inputs"], case["paths"]
    cf = project_cash_flows(inputs, psa, paths.shock, beta)
    D = payment_discount_factors(paths.rates, spread, inputs["payment_lag_months_after_month_start"])
    prices = path_prices(cf.cash_flow, D, inputs["current_balance"])
    return _with_clean(summarize(prices), inputs), prices, cf


def value_private_label(case: dict, psa: float = BASE["psa"], beta: float = BASE["beta"],
                        pd_annual: float = BASE["pd_annual"], recovery: float = BASE["recovery"],
                        spread: float = 0.0):
    """Part II credit-adjusted value per 100. Returns (summary, per-path full prices, expected CFs, survival)."""
    inputs, paths = case["inputs"], case["paths"]
    cf = project_cash_flows(inputs, psa, paths.shock, beta)
    ecf, S = expected_cash_flows(cf, pd_annual, recovery)
    D = payment_discount_factors(paths.rates, spread, inputs["payment_lag_months_after_month_start"])
    prices = path_prices(ecf, D, inputs["current_balance"])
    return _with_clean(summarize(prices), inputs), prices, ecf, S


def market_prices(inputs: dict) -> dict:
    return {"bid": price_from_32nds(97, inputs["bval_bid_32nds"]),
            "mid": price_from_32nds(97, inputs["bval_mid_32nds"]),
            "ask": price_from_32nds(97, inputs["bval_ask_32nds"])}
