# Figure inventory — Phase 2 report

`docs/phase2_report.tex` loads images from `docs/figures/` (set via `\graphicspath`).
All files below are already copied there. Source files stay untouched in `reports/`.

## Used in the paper

| File in `docs/figures/` | Copied from | Used as |
|---|---|---|
| `fig01_baseline_equity.png` | `reports/walkforward_banknifty_20260706_154902/equity.png` | Fig. 2 — Phase 2 baseline, full-year 2020, net −Rs.349,791 |
| `fig02_h15_equity.png` | `reports/walkforward_banknifty_20260706_162404/equity.png` | Fig. 3 — best pre-risk config, h=15m, net −Rs.9,983 |
| `fig03_stop12_equity.png` | `reports/walkforward_banknifty_20260706_165719/equity.png` | Fig. 4 — the 12% stop damage, net −Rs.39,734 |
| `fig04_final2020_equity.png` | `reports/walkforward_banknifty_20260706_174950/equity.png` | Fig. 5 — final config, 2020 |
| `fig05_final2021_equity.png` | `reports/walkforward_banknifty_20260706_180124/equity.png` | Fig. 6 — final config, 2021 |

Figure 1 is drawn in TikZ inside the `.tex` (the architecture diagram) — no image file needed.

## Optional extras (already copied, not yet referenced)

| File | Source | Suggested use |
|---|---|---|
| `fig06_h5_equity_optional.png` | `..._161234/equity.png` | horizon sweep appendix, h=5m |
| `fig07_h30_equity_optional.png` | `..._163536/equity.png` | horizon sweep appendix, h=30m |
| `fig08_stop12_2021_optional.png` | `..._170841/equity.png` | show the 12% stop failing in 2021 too |
| `fig09_singleday_postcost_optional.png` | `reports/charts/sim_BANKNIFTY16JAN2032200CE_2020-01-10.png` | continuity with Phase 1: same day, now post-cost |

To use an optional figure, add:

```latex
\begin{figure}[H]
\centering
\includegraphics[width=0.92\textwidth]{fig06_h5_equity_optional.png}
\caption{...}
\label{fig:h5}
\end{figure}
```

## Do NOT use

`data/processed_features/*.png` are Phase 1 charts (RandomForest era, pre-cost-model,
pre-label-fix). They already appear in the Phase 1 paper; reusing them here would show
numbers this report disowns.

## Building

The team study guide and presentation outline are kept local (see `.gitignore`),
so they are not in this repository.

No LaTeX toolchain is installed on this machine. Easiest path: upload
`phase2_report.tex` plus the `figures/` folder to Overleaf, or install MiKTeX and run:

```
pdflatex phase2_report.tex
pdflatex phase2_report.tex     # second pass for ToC and references
```

Packages used are all standard (amsmath, booktabs, graphicx, listings, algorithm,
algpseudocode, tikz, hyperref).
