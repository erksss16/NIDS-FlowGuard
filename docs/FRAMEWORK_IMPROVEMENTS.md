# NIDS Framework Improvements

## Current Decisions

- The runtime model must stay dataset-specific until a unified feature schema is implemented. NSL/KDD uses 121 input features in this package, while UNSW uses 196 input features. Feeding one dataset into the other model is invalid because the feature dimensions and categorical encodings differ.
- The runtime split is controlled by `--percent` or the optional `--pretrain-ratio`. The launcher passes `--percent 0.8` and enables `--stream`; inspect the split logic in `ssf.py` when comparing training experiments.
- The demo launcher keeps `--dataset nsl` and `--stream`, so the NSL model predicts NSL test traffic. UNSW should be treated as an auxiliary validation/domain-transfer experiment, not as data for the same binary model.

## Unified Feature Schema Path

To build one model for real traffic, introduce a `FeatureSchema` layer before SSF:

1. Define a canonical flow schema with stable fields such as `duration`, `src_bytes`, `dst_bytes`, `protocol`, `service`, `flag/state`, count/rate statistics, and optional IP/session aggregates.
2. Map NSL/KDD and UNSW raw columns into this schema with explicit adapters. Missing columns should be filled with documented defaults or learned imputation, not silently dropped.
3. Fit one categorical encoder and scaler on the canonical schema only, then persist the encoder metadata next to the checkpoint.
4. Train and serve one model against the canonical tensor dimension. Dataset-specific models can remain as baselines.

## Drift Strategy

KS p-value drift detection has been replaced with Wasserstein Distance. The system records:

- `drift_score`: maximum Wasserstein distance for the processed batch.
- `drift_level`: `none`, `low`, `medium`, or `high`.

Propagation now changes with drift level:

- `none`: conservative propagation, stronger distillation.
- `low`: normal propagation.
- `medium`: higher new-sample weight, weaker distillation.
- `high`: strongest adaptation to new samples, weakest distillation.

This gives a continuous severity signal instead of a single hypothesis-test p-value.
