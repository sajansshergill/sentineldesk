# SentinelDesk Local Eval Results

These metrics are generated from synthetic data and local stubs. They are engineering regression checks, not production compliance claims.

## Summary

- Extraction field accuracy: 92.14% over 700 fields.
- Anomaly precision/recall: 17.54% / 67.57%.
- Trajectory success rate: 100.00%.
- Citation valid rate: 100.00%.

## Raw JSON

```json
{
  "extraction": {
    "messages": 100,
    "field_accuracy": 0.9214,
    "fields_checked": 700
  },
  "anomaly": {
    "rows": 2574,
    "precision": 0.1754,
    "recall": 0.6757,
    "alerts": 285
  },
  "trajectory": {
    "runs": 3,
    "pending_approval": 3,
    "halted": 0,
    "success_rate": 1.0
  },
  "citations": {
    "citations": 4,
    "valid_rate": 1.0
  }
}
```
