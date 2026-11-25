# Calibration diagnosis

- Generated : 2026-10-17 13:37
- BANKNIFTY | horizon 15m | deadband 0.1%
- Protocol : fit 8d, isotonic calibrate 5d, test next unseen day
- Test days : 30 (2021-06-18 .. 2021-07-30)
- Rows      : 696,482

## Headline
```
  Base rate (UP)        : 0.422
  AUC                   : 0.5325  (0.5 = no skill)  [min 0.433 max 0.650]
  Accuracy @0.5         : 0.576
  Brier, raw            : 0.2802
  Brier, calibrated     : 0.2442
  Calibrator fitted on  : 30/30 days
```

## Reliability: what the probability promises vs. what happened
```
                rows  predicted  actual    gap
bucket                                        
[0.0, 0.35)    53544      0.327   0.415 -0.088
[0.35, 0.45)  520651      0.409   0.411 -0.001
[0.45, 0.55)  109380      0.483   0.447  0.036
[0.55, 0.65)   10700      0.575   0.480  0.094
[0.65, 0.7)     1849      0.668   0.391  0.277
[0.7, 0.75)      276      0.740   0.678  0.062
[0.75, 0.8)       18      0.759   0.833 -0.075
[0.8, 1.01)       64      0.963   0.625  0.338
```

## Precision at the thresholds we trade
```
  p > 0.55 :  12,907 rows  actually UP 0.473  (lift +0.055)
  p > 0.60 :   4,111 rows  actually UP 0.435  (lift +0.018)
  p > 0.65 :   2,207 rows  actually UP 0.437  (lift +0.019)
  p > 0.70 :     358 rows  actually UP 0.676  (lift +0.258)
  p > 0.75 :      75 rows  actually UP 0.640  (lift +0.222)
  p > 0.80 :      64 rows  actually UP 0.625  (lift +0.207)
```
