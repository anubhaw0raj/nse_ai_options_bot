# Calibration diagnosis

- Generated : 2026-10-17 13:33
- BANKNIFTY | horizon 15m | deadband 0.1%
- Protocol : fit 8d, isotonic calibrate 2d, test next unseen day
- Test days : 30 (2020-02-14 .. 2020-03-30)
- Rows      : 565,798

## Headline
```
  Base rate (UP)        : 0.448
  AUC                   : 0.5149  (0.5 = no skill)  [min 0.378 max 0.633]
  Accuracy @0.5         : 0.552
  Brier, raw            : 0.3002
  Brier, calibrated     : 0.2499
  Calibrator fitted on  : 30/30 days
```

## Reliability: what the probability promises vs. what happened
```
                rows  predicted  actual    gap
bucket                                        
[0.0, 0.35)    15330      0.285   0.440 -0.155
[0.35, 0.45)  286432      0.422   0.438 -0.015
[0.45, 0.55)  247074      0.475   0.450  0.025
[0.55, 0.65)   13332      0.571   0.494  0.078
[0.65, 0.7)      569      0.682   0.467  0.215
[0.7, 0.75)      283      0.731   0.548  0.183
[0.75, 0.8)      389      0.778   0.542  0.236
[0.8, 1.01)     2389      0.893   0.427  0.466
```

## Precision at the thresholds we trade
```
  p > 0.55 :  16,962 rows  actually UP 0.486  (lift +0.041)
  p > 0.60 :   5,817 rows  actually UP 0.433  (lift -0.011)
  p > 0.65 :   3,630 rows  actually UP 0.455  (lift +0.010)
  p > 0.70 :   3,061 rows  actually UP 0.453  (lift +0.008)
  p > 0.75 :   2,747 rows  actually UP 0.446  (lift +0.001)
  p > 0.80 :   2,358 rows  actually UP 0.425  (lift -0.019)
```
