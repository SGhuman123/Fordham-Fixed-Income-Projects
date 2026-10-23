# The TIPS-Treasury Bond Puzzle, Revisited (March 2026)

Group project for Fixed Income Securities (QFGB-8931), Fordham University, Spring 2026.

## The question

Fleckenstein, Longstaff and Lustig (2014) show that a nominal Treasury bond can be replicated exactly
with a TIPS issue of the same maturity, a strip of zero-coupon inflation swaps and small positions in
Treasury STRIPS. Between 2004 and 2009, the replicating portfolio was almost always cheaper than the
Treasury it copies, sometimes by more than $20 per $100 notional. The assignment (Part II) asks us to build
the same strategy with current Bloomberg data and present it in the format of the paper's Table II.

**Scope.** The assignment also has a Part I (Treasury spot curves by linear and cubic interpolation, a
swap spot curve, mispriced securities). The submitted report and this repository cover **Part II
only**. See [Files left out](#files-left-out).

## Approach

Pair: **T 3.500% 2/15/2033** (target) and **TII 1.125% 1/15/2033**, a 31-day maturity mismatch, the
largest the paper allows. Settlement is 3/20/2026, with 14 semiannual cash-flow dates.

All amounts are per $100 notional, with semiannual coupons c = 1.75 and s = 0.5625.

| Leg | Date 0 | Date t < T | Date T |
|---|---|---|---|
| Buy Treasury | −P | c | c + 100 |
| Buy TIPS | −V | s·I_t | (s + 100)·I_T |
| Inflation swaps (zero-coupon) | 0 | s·(F_t − I_t) | (s + 100)·(F_T − I_T) |
| STRIPS | −Σ x_t·D(t) | x_t = c − s·F_t | x_T = (c + 100) − (s + 100)·F_T |
| Replicating portfolio | −(V + Σ x_t·D(t)) | c | c + 100 |

* F_t = (1 + f_t)^t, where f_t is the zero-coupon inflation swap rate and t is in years (Act/365.25
  from settlement).
* D(t) is the STRIPS ask price per $1 of face, which is the Bloomberg price divided by 100.
* Mispricing = P − (V + Σ x_t·D(t)). A positive value means the Treasury is rich. A negative value
  means TIPS are rich.
* Prices are full prices: the clean price plus Act/Act accrued interest.
* I_t is measured from the trade date. The TIPS position is therefore sized per $100 of *current*
  inflation-adjusted principal, so V is the real (unindexed) full price and the index ratio cancels out.
* Inflation swap rates come from the USSWIT1–USSWIT7 quotes. Half-year points are the average of the
  two neighbouring integer tenors, and the 1Y rate is used flat below one year. The paper uses a cubic
  spline with a CPI seasonal adjustment. The notebook shows how sensitive the result is to this choice.

## Data

Bloomberg Terminal, settlement 3/20/2026:

* Treasury and TIPS prices: 96-19+ and 97-15¼, quoted in 32nds.
* Zero-coupon USD inflation swap rates, USSWIT1–USSWIT7: 2.704%, 2.522%, 2.477%, 2.451%, 2.420%,
  2.444% and 2.425%.
* Treasury STRIPS ask prices.

The settlement date is taken from the workbook. The full STRIPS ask curve exported for the project is in
`data/strips_ask_prices.xlsx`. It has 228 maturities from 3/31/2026 to 2/15/2056. At some coupon dates its
prices differ from the workbook's by up to about 0.01. The source does not record whether the two price
sets were pulled at different times.

## Main findings

| Item (per $100) | Value |
|---|---|
| Treasury full price P | 96.9284 |
| TIPS full price V | 97.6755 |
| STRIPS cost Σ x_t·D(t) | 0.2251 |
| Synthetic price V + STRIPS | 97.9006 |
| **Mispricing P − synthetic** | **−0.9721** |

* The replicating portfolio costs about **$0.97 more** than the Treasury bond. TIPS are rich relative to
  nominal Treasuries, which is the *opposite* sign to FLL's 2004–2009 sample. The gap is about 1/24 of
  the $23.10 in the paper's December 2008 example.
* The sign does not depend on the method. The mispricing is −0.96 when swap rates are interpolated at
  the exact cash-flow dates, −0.93 with a cubic spline, and −0.97 with the alternative STRIPS curve.
  These figures are in the notebook.
* The mispricing is not adjusted for the 31-day maturity mismatch, for the TIPS paying on Jan/Jul 15
  rather than Feb/Aug 15, for CPI seasonality, or for transaction costs. FLL estimate transaction costs
  at roughly 20–70 cents per $100. A gap of under $1 is therefore weak evidence of a tradable arbitrage.

These numbers include the corrections listed below. The submitted report shows −1.0351.

## Files

| File | Contents |
|---|---|
| `report/Group_Project_1_Report.pdf` | The report as submitted, covering methodology, data, the Table II replication and the mispricing. See the errata before quoting its numbers. |
| `TIPS_Treasury_Replication.xlsx` | Corrected model with five sheets. `Inputs` holds the prices, the accrued-interest build-up, the swap quotes and interpolation, and the STRIPS. `Calculations` holds F_t, x_t and the STRIPS cost. `Table II` is the paper-format cash-flow table. `Mispricing` is the summary. `Corrections` logs every change made to the submitted workbook. |
| `tips_treasury_replication.ipynb` | Python cross-check. It reads the workbook inputs, rebuilds Table II, checks that the replication holds for any inflation path, and runs sensitivities on swap interpolation, accrued interest and the STRIPS source. |
| `data/strips_ask_prices.xlsx` | Bloomberg STRIPS ask-price curve, 228 maturities. |
| `docs/STRIPS_and_Swap_Data.pdf` | Supporting data appendix as submitted: STRIPS prices, year fractions, swap interpolation and F_t. Its values match the workbook. |
| `docs/Assignment_Prompt.pdf` | The assignment. |

## How to reproduce

```bash
pip install -r requirements.txt
jupyter nbconvert --to notebook --execute tips_treasury_replication.ipynb   # or open it in Jupyter
```

Run the notebook from the repository root, because it reads `TIPS_Treasury_Replication.xlsx` and
`data/strips_ask_prices.xlsx` by relative path. The workbook needs no add-ins. Its cached values were
recalculated in LibreOffice after the corrections.

## Corrections / errata

### Report (`report/Group_Project_1_Report.pdf`, left as submitted)

| # | Location | As submitted | Corrected | Reason |
|---|---|---|---|---|
| 1 | §2.2 | "Both bonds had 64 days of accrued interest" | Treasury 33 days (2/15→3/20/2026), TIPS 64 days (1/15→3/20/2026) | The report's own Treasury accrued, 0.3191 = 1.75 × 33/181, implies 33 days. |
| 2 | §2.2, Table 2.1 | TIPS accrued 0.2619, TIPS full price 97.7384 | 0.1989 (0.5625 × 64/181) and 97.6755 | The Bloomberg figure used ($2,618.64 per $1MM) does not match 64 days of real accrued. Multiplying by a plausible index ratio of about 1.09 would not reconcile it either. |
| 3 | Table 5, Table II date 0, §3.2 | V 97.7384; synthetic 97.9635; mispricing −1.0351 ("≈ $1.04") | V 97.6755; synthetic 97.9006; mispricing −0.9721 ("≈ $0.97") | Follows from #2. The sign and the interpretation (TIPS rich) are unchanged. |
| 4 | §2.3, column F | 1.01087, 1.02704, 1.03934, 1.05105, 1.06355, 1.07591, 1.08980, 1.10310, 1.11520, 1.12732, 1.14207, 1.15740, 1.17113, 1.18316 | 1.01087, 1.02455, 1.03689, 1.04868, 1.06121, 1.07381, 1.08644, 1.09930, 1.11183, 1.12455, 1.13867, 1.15334, 1.16661, 1.18007 | The model uses each cash flow's actual year fraction (0.405, 0.909, ... 6.910 years). After the first row, the printed values match neither that nor the nominal 0.5-year grid. The corrected values are the ones the calculation actually uses, and they agree with `docs/STRIPS_and_Swap_Data.pdf`. |
| 5 | Table II (pp. 5–6), STRIPS x_t column | 1.18862, 1.18245, 1.17637, 1.17093, 1.16513, 1.15926, 1.15192, 1.14731, 1.14169, 1.13521, 1.12912, 1.12288, 1.11669, −16.9362 | 1.18139, 1.17369, 1.16675, 1.16012, 1.15307, 1.14598, 1.13888, 1.13165, 1.12460, 1.11744, 1.10950, 1.10125, 1.09378, −16.92106 | x_t = c − s·F_t from the workbook. The printed values would give a STRIPS cost of 0.3762, which contradicts the 0.2251 in the same table. |
| 6 | Table II, column header "STRIPS Price D(t)" | Prices per $100 (98.5150, ...) | Label as price per $100. D(t) = price/100 | D(t) is defined per $1 in §1.2. The calculation itself is correct. |
| 7 | §1.3 | "Three simplifications" (only two listed) | Further simplifications not listed: TIPS coupons and principal (Jan/Jul 15) are treated as paid on the Treasury dates (Feb/Aug 15); swap rates are taken at the nearest half-year grid point; no CPI seasonal adjustment | Completeness. Their effect is small, as the notebook sensitivities show. |

### Workbook (`TIPS_Treasury_Replication.xlsx`, formerly `TIPS_Treasury_FLL.xlsx`)

* `Table II!G5`: the date-0 total was `=B5+C5+D5+E5` (−194.89). It now reads `=C5+D5+E5` (−97.90). The
  total for the replicating portfolio must exclude the Treasury leg it replicates, as in the paper's
  Table II.
* `Mispricing!B9`: the label test was `IF(B7<0, ...)`. B7 is the synthetic price, which is always
  positive, so the label read "Treasury relatively expensive", contradicting the result. The test now
  uses B8, the mispricing.
* `Inputs!E5`: the hardcoded TIPS full price 97.738427 is now built from the clean price plus 64-day
  real accrued, giving 97.675458 (errata #2). `Inputs!B5` is also formula-driven now. Its value is
  unchanged.
* `Inputs!A11:I25`: the swap block was mislabelled. For example, the 1.0-year row showed USSWIT2 at
  2.522%, and the interpolated rates sat under a "Period (yrs)" header. The seven quotes now sit in
  G11:I18 and the grid is relabelled. The interpolated values are unchanged.
* `Mispricing!A12`: the commentary is updated to the corrected figure.

### Notebook (`tips_treasury_replication.ipynb`, formerly `FICC project/code.ipynb`)

The original notebook was a draft that did not implement the paper's strategy and has been replaced:

* `settle_date` was used before it was defined, so the notebook failed when run from a fresh kernel.
* The "replication" added a flat 10-year swap rate (2.4875%) as an extra semiannual coupon. It had no
  (1 + f)^t compounding, no maturity-matched swaps and no STRIPS legs.
* It compared a clean price to a present value and used different inputs from the report: a 3/6/2026
  settlement and Treasury 97-14. Its result (−0.26) appears nowhere in the report.

## Files left out

* `Interpolating Bond Rates_ A Guide.xlsx`. The first sheet duplicates the swap interpolation in the
  workbook. The second sheet labels a cubic polynomial *trendline* fitted to **inflation** swap rates
  as a "spot curve". It is not a cubic spline, it misses the market quotes (for example 2.659% against
  2.704% at 1Y), and it is not a Treasury or nominal swap curve. Its "discount factors" are inflation
  compounding factors. It does not answer Part I and cannot be corrected without nominal Treasury and
  swap data, which are not in the project files.
* The FLL journal article (copyrighted). See the reference below.
* `.DS_Store` files.

## Reference

Fleckenstein, M., Longstaff, F. A., and Lustig, H. (2014). The TIPS-Treasury Bond Puzzle. *Journal of
Finance*, 69(5), 2151–2197.

## Credits

Aaryan Nannapaneni, Jazzy Dong and James Huang.
