# Calibration diagnosis

- Generated : 2026-10-17 13:35
- BANKNIFTY | horizon 15m | deadband 0.1%
- Protocol : fit 8d, isotonic calibrate 2d, test next unseen day
- Test days : 30 (2021-06-15 .. 2021-07-27)
- Rows      : 698,316

## Headline
```
  Base rate (UP)        : 0.422
  AUC                   : 0.5343  (0.5 = no skill)  [min 0.414 max 0.642]
  Accuracy @0.5         : 0.574
  Brier, raw            : 0.2767
  Brier, calibrated     : 0.2466
  Calibrator fitted on  : 30/30 days
```

## Reliability: what the probability promises vs. what happened
```
                rows  predicted  actual    gap
bucket                                        
[0.0, 0.35)    73667      0.312   0.410 -0.098
[0.35, 0.45)  496301      0.406   0.411 -0.005
[0.45, 0.55)  103093      0.483   0.449  0.034
[0.55, 0.65)   20002      0.581   0.496  0.085
[0.65, 0.7)     1568      0.672   0.323  0.349
[0.7, 0.75)     2246      0.718   0.455  0.263
[0.75, 0.8)      647      0.763   0.326  0.437
[0.8, 1.01)      792      0.944   0.365  0.580
```

## Precision at the thresholds we trade
```
  p > 0.55 :  25,241 rows  actually UP 0.473  (lift +0.054)
  p > 0.60 :  10,439 rows  actually UP 0.395  (lift -0.023)
  p > 0.65 :   5,253 rows  actually UP 0.386  (lift -0.033)
  p > 0.70 :   3,663 rows  actually UP 0.411  (lift -0.007)
  p > 0.75 :   1,439 rows  actually UP 0.347  (lift -0.071)
  p > 0.80 :     781 rows  actually UP 0.356  (lift -0.063)
```
