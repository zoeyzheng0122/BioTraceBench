"""Diagnostic counts before eligibility and reporting-state checks."""


def diagnostic_metrics(tp, predicted, gold):
    """Summarize the unprojected inventory; this is not a final paper score."""
    precision = tp / predicted if predicted else (1.0 if not gold else 0.0)
    recall = tp / gold if gold else (1.0 if not predicted else 0.0)
    return {"tp": tp, "predicted": predicted, "gold": gold, "precision": precision,
            "recall": recall, "f1": 2*precision*recall/(precision+recall) if precision+recall else 0.0}
