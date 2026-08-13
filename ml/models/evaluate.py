"""Metric contract from configs/evaluation_spec.json.

  - regression : RMSE (primary), MAE, MAPE, R2, Spearman
  - binary     : PR-AUC (primary), ROC-AUC, F1@best, precision@k, Brier, ECE
  - survival   : Harrell C-index (primary), integrated-Brier is future work
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import auc, precision_recall_curve, precision_score, recall_score, roc_auc_score, roc_curve


def regression_metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    valid = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true, y_pred = y_true[valid], y_pred[valid]
    if len(y_true) == 0:
        return {"rmse": np.nan, "mae": np.nan, "mape": np.nan, "r2": np.nan, "spearman": np.nan}
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, np.nan, y_true))) * 100)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rho = np.nan if np.all(y_pred == y_pred[0]) else float(spearmanr(y_true, y_pred)[0])
    return {"rmse": round(rmse, 4), "mae": round(mae, 4), "mape": round(mape, 4), "r2": round(r2, 4), "spearman": rho, "n": int(len(y_true))}


def expected_calibration_error(y_true, y_prob, bins: int = 10) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (y_prob >= lo) & (y_prob < hi) if hi < 1.0 else (y_prob >= lo) & (y_prob <= hi)
        if mask.sum() == 0:
            continue
        acc = y_true[mask].mean()
        conf = y_prob[mask].mean()
        ece += (mask.sum() / len(y_true)) * abs(acc - conf)
    return float(ece)


def binary_metrics(y_true, y_prob, k: int = 1000) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.asarray(y_prob, dtype=float)
    valid = ~(np.isnan(y_true) | np.isnan(y_prob))
    y_true, y_prob = y_true[valid], y_prob[valid]
    if len(y_true) == 0 or y_true.sum() == 0 or y_true.sum() == len(y_true):
        return {"pr_auc": np.nan, "roc_auc": np.nan, "f1_at_best": np.nan, "precision_at_k": np.nan, "brier": np.nan, "ece": np.nan, "n": int(len(y_true)), "positive_rate": float(np.nanmean(y_true))}
    prevalence = float(y_true.mean())
    # Constant-score baseline (e.g. dummy): theoretical reference, not a degenerate curve.
    if np.all(y_prob == y_prob[0]):
        return {"pr_auc": round(prevalence, 4), "roc_auc": 0.5, "f1_at_best": np.nan, "best_threshold": float(y_prob[0]), "precision_at_k": round(prevalence, 4), "brier": round(float(np.mean((y_prob - y_true) ** 2)), 4), "ece": round(float(np.abs(y_prob[0] - prevalence)), 4), "n": int(len(y_true)), "positive_rate": round(prevalence, 4)}
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    pr_auc = float(auc(recall, precision))
    roc_auc = float(roc_auc_score(y_true, y_prob))
    fpr, tpr, roc_thr = roc_curve(y_true, y_prob)
    youden = tpr - fpr
    best = float(roc_thr[np.argmax(youden)])
    y_best = (y_prob >= best).astype(int)
    p, r = precision_score(y_true, y_best, zero_division=0), recall_score(y_true, y_best, zero_division=0)
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    order = np.argsort(-y_prob)
    top = order[:k]
    precision_at_k = float(y_true[top].mean())
    brier = float(np.mean((y_prob - y_true) ** 2))
    ece = expected_calibration_error(y_true, y_prob)
    return {"pr_auc": round(pr_auc, 4), "roc_auc": round(roc_auc, 4), "f1_at_best": round(f1, 4), "best_threshold": round(best, 4), "precision_at_k": round(precision_at_k, 4), "brier": round(brier, 4), "ece": round(ece, 4), "n": int(len(y_true)), "positive_rate": round(prevalence, 4)}


def concordance_index(time, event, risk_score) -> float:
    """Harrell C-index for right-censored survival. Higher risk_score = shorter time.

    Among pairs where the earlier observation is an uncensored event, the fraction
    where the model ranks it higher-risk than the later observation.
    """
    time = np.asarray(time, dtype=float)
    event = np.asarray(event, dtype=float)
    risk = np.asarray(risk_score, dtype=float)
    valid = ~(np.isnan(time) | np.isnan(event) | np.isnan(risk))
    time, event, risk = time[valid], event[valid], risk[valid]
    events = np.where(event.astype(bool))[0]
    if len(events) == 0:
        return np.nan
    total = 0.0
    concordant = 0.0
    for i in events:
        comparable = time >= time[i]
        comparable[i] = False
        if comparable.sum() == 0:
            continue
        total += comparable.sum()
        concordant += (risk[comparable] < risk[i]).sum()
    return float(concordant / total) if total > 0 else np.nan


def survival_metrics(time, event, risk_score) -> dict:
    c = concordance_index(time, event, risk_score)
    return {"c_index": round(c, 4) if not np.isnan(c) else None, "n": int(np.asarray(time).size)}
