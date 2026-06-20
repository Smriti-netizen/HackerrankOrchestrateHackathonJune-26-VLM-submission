def set_f1(pred, gold):
    if pred == "none" and gold == "none": return 1.0
    p = set(pred.split(";")) if pred != "none" else set()
    g = set(gold.split(";")) if gold != "none" else set()
    if not p and not g: return 1.0
    prec = len(p & g) / len(p) if p else 0
    rec = len(p & g) / len(g) if g else 0
    return 2 * prec * rec / (prec + rec) if (prec + rec) else 0

def accuracy(preds, golds):
    return sum(p == g for p, g in zip(preds, golds)) / len(preds)