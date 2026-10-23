# Monte Carlo Valuation of an Agency and Private-Label MBS (FN FS9548)

Individual final project for Fixed Income Securities (QFGB-8931), Fordham University, Spring 2026.
James Huang.

## The question

Value the assigned mortgage pass-through, **FN FS9548**, in two ways. The pool is a Fannie Mae UMBS 15-year
pool with a 3.0% coupon and $2.99M outstanding.

1. **Agency MBS.** Payment is guaranteed by the U.S. government. Generate interest-rate paths, choose and justify
   a prepayment model, project cash flows along each path, and value the security as the average discounted
   value across paths. Is it fairly priced? Are you sure?
2. **Private-label MBS.** The guarantor is an A-rated private institution. Repeat the valuation, adjusting for
   credit risk with the expected cash-flow approach (default probability, survival, recovery).

The framework is discrete and monthly, with every step shown and no black-box pricing functions.

## Results (30 April 2026)

| | Agency | Private label (A, PD 0.10%, R 40%) |
|---|---|---|
| Model value, clean, per 100 | **98.198** | **98.090** |
| Monte Carlo standard error | 0.0003 | 0.0003 |
| BVAL bid | 97.738 | 97.738 |
| Model − market | +0.460 | +0.352 |
| OAS implied by the bid | **25.7 bp** (Bloomberg BAM TOAS: 17.9 bp) | 19.7 bp |

- **Agency.** The security is cheap relative to Treasuries at zero spread, which is normal for agency MBS. The
  OAS the market price implies is close to Bloomberg's own estimate, so it is **fairly priced to slightly cheap**.
  The verdict depends on prepayment speed: the OAS ranges from 18 bp to 39 bp across 100–300 PSA. Effective
  duration is 1.79 years.
- **Private label.** With historical A-rated default rates, the credit adjustment costs only about 0.11 points.
  It would push the value below today's agency price only if the guarantor's annual PD exceeded **0.43%**.
  Market-implied PDs for A-rated financials are usually higher than that, so the adjustment here is a lower bound.

## Method

1. **Rates.** The model simulates 10,000 monthly one-month Treasury rate paths (antithetic, seed 2026):
   $r_k = \max(0, \theta_k + \sigma W_k)$.
   - $\sigma$ = 25.2 bp per month, from ten years of month-end GT10 yields.
   - $\theta_k$ is solved so that the average path discount factor reprices the bootstrapped Treasury zero curve
     exactly.
2. **Prepayments.** Bloomberg's projected 178 PSA, scaled on each path by the simulated rate change (β = 0.20,
   bounded 0.75×–1.75×). This makes the cash flows path-dependent and gives the prepayment option a value.
3. **Cash flows.** Investor cash flow is pass-through interest plus scheduled principal (from the WAC
   amortization) plus prepayment, along every path.
4. **Valuation.** Cash flows are discounted with each path's cumulative short-rate discount factors on the actual
   payment dates (54-day delay). Value is the average over paths, reported as a clean price for comparison with
   BVAL. OAS is solved against the bid.
5. **Credit.** $E[CF_t] = S_t\,CF_t + (S_{t-1}-S_t)\,R\,B_{t-1}$, on the same paths.

## Repository layout

```
notebooks/
  01_inputs_and_rate_paths.ipynb          data checks, volatility, zero curve, calibrated rate paths
  02_part1_agency_valuation.ipynb         PSA model, path cash flows, valuation, OAS, sensitivities, reconciliation
  03_part2_private_label_valuation.ipynb  survival curve, expected cash flows, credit sensitivity
  04_build_excel_workbook.ipynb           writes and verifies the Excel workbook
src/mbs_model.py                          model code shared by the notebooks
src/plot_style.py                         figure styling
data/pool_inputs.json                     Bloomberg pool, price and curve inputs
data/GT10_monthly_bloomberg.xlsx          month-end 10-year Treasury yields (Bloomberg)
data/screenshots/                         Bloomberg source screens (DES, BVAL, ALLQ, curve, GT10)
excel/FN_FS9548_MBS_Pricing_Model.xlsx    corrected workbook: one path in live formulas + Monte Carlo results
outputs/                                  results.json, per-path prices, figures
report/Report.pdf (.docx, .md)            revised written report
Final_Project_Prompt.pdf                  assignment
```

## Reproduce

```bash
pip install -r requirements.txt
cd notebooks
jupyter nbconvert --to notebook --execute --inplace 01_*.ipynb 02_*.ipynb 03_*.ipynb 04_*.ipynb
```

The notebooks must run in order: 02 and 03 write `outputs/results.json`, and 04 reads it. Results are
deterministic (fixed seed). The full run takes under a minute. Notebook 04 recalculates the workbook with
LibreOffice if it is installed. Otherwise Excel calculates the formulas when the file is opened.

## Corrections to the originally submitted version

The submitted Excel model and report (May 2026) concluded the pool was **rich** (97.49 vs. 97.74). This revision
fixes the following:

| # | Issue in the submitted version | Fix |
|---|---|---|
| 1 | Discounting at a random walk from the **10-year** yield, unrelated to the curve, for a 1.9-year-WAL security | Short-rate paths calibrated to the Treasury zero curve |
| 2 | Discount factor $1/(1+r_t/12)^t$ used only the month-*t* rate | Cumulative path discount factor $\prod_k (1+r_k/12)^{-1}$ |
| 3 | Cash flows identical on every path, so the prepayment option had no value | Rate-dependent PSA speed |
| 4 | `RAND()` with 100 paths: results changed on every recalculation, and run-to-run st.dev was 0.27, so the PSA sensitivity flipped between rich and cheap at random | 10,000 antithetic paths, fixed seed, common random numbers |
| 5 | Report quoted inconsistent prices (97.5371 and 97.4949 for the same case; market 97.7383 and 97.7393) | One set of reproducible numbers |
| 6 | Clean BVAL price compared with cash flows assumed to be paid at month-end | Actual payment dates; accrued interest subtracted |
| 7 | Expected cash flow $CF_t(S_t + R\,q_t)$: recovery on one month's cash flow only | Recovery on the outstanding principal, $q_t R B_{t-1}$ |
| 8 | Part II was valued on a different random draw from Part I, so the private-label price came out *above* the agency price | Same paths for both parts |
| 9 | Volatility sample included a 5-day change (30 Apr to 5 May) | Month-end changes through the valuation date |

Notebook 02 has a step-by-step bridge from the submitted method (97.51 with 10,000 paths) to the corrected
value (98.20). Almost all of the difference comes from fix 1.

## Data

The inputs are Bloomberg terminal data captured on 30 April 2026: FN FS9548 DES/BVAL/ALLQ screens,
the US Treasury Actives curve (YCGT0025), and GT10 Govt monthly history. Screenshots are in `data/screenshots/`,
cropped to remove terminal account details. Fabozzi, *Bond Markets, Analysis, and Strategies* (10th ed.) is the
methodological reference and is not included.
