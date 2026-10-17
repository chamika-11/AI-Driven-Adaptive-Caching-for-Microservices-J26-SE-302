import pathlib
p = pathlib.Path("src/rlcache/analysis/signal.py"); s = p.read_text(encoding="utf-8")
a = s.index("def fit_and_score_mlp(")
b = s.index("def feature_regression(")
new = '''def fit_and_score_mlp(Xtr, ytr, Xte, yte, seed: int = 0, epochs: int = 8, hidden: int = 64) -> float:
    """Held-out R^2 of a small MLP regressor (2 hidden ReLU layers, Adam, minibatch 512).

    Pure numpy: PyTorch is blocked on this machine by a Windows Application Control policy
    (WinError 4551, 2026-10-15), and this diagnostic only needs *a* 64-64 regressor.
    """
    rng = np.random.default_rng(seed)
    Xtr = np.asarray(Xtr, np.float64)
    Xte = np.asarray(Xte, np.float64)
    mu, sd = float(ytr.mean()), float(ytr.std() + 1e-8)
    yt = (np.asarray(ytr, np.float64) - mu) / sd
    d = Xtr.shape[1]
    sizes = [d, hidden, hidden, 1]
    W = [rng.normal(0, np.sqrt(2.0 / sizes[i]), (sizes[i], sizes[i + 1])) for i in range(3)]
    B = [np.zeros(sizes[i + 1]) for i in range(3)]
    m = [np.zeros_like(w) for w in W] + [np.zeros_like(b) for b in B]
    v = [np.zeros_like(w) for w in W] + [np.zeros_like(b) for b in B]
    lr, b1, b2, eps, step = 1e-3, 0.9, 0.999, 1e-8, 0
    n = len(Xtr)

    def forward(X):
        h1 = np.maximum(X @ W[0] + B[0], 0.0)
        h2 = np.maximum(h1 @ W[1] + B[1], 0.0)
        return h1, h2, (h2 @ W[2] + B[2]).ravel()

    for _ in range(epochs):
        perm = rng.permutation(n)
        for i in range(0, n, 512):
            j = perm[i:i + 512]
            X, y = Xtr[j], yt[j]
            h1, h2, out = forward(X)
            g = (2.0 / len(j)) * (out - y)[:, None]                 # d loss / d out (MSE)
            gW2 = h2.T @ g
            gB2 = g.sum(0)
            g2 = (g @ W[2].T) * (h2 > 0)
            gW1, gB1 = h1.T @ g2, g2.sum(0)
            g1 = (g2 @ W[1].T) * (h1 > 0)
            gW0, gB0 = X.T @ g1, g1.sum(0)
            grads = [gW0, gW1, gW2, gB0, gB1, gB2]
            params = W + B
            step += 1
            for k, (p_, g_) in enumerate(zip(params, grads)):
                m[k] = b1 * m[k] + (1 - b1) * g_
                v[k] = b2 * v[k] + (1 - b2) * g_ * g_
                mh, vh = m[k] / (1 - b1 ** step), v[k] / (1 - b2 ** step)
                p_ -= lr * mh / (np.sqrt(vh) + eps)
    pred = forward(Xte)[2] * sd + mu
    sse = float(((yte - pred) ** 2).sum())
    sst = float(((yte - yte.mean()) ** 2).sum())
    return 1.0 - sse / max(sst, 1e-12)


'''
p.write_text(s[:a] + new + s[b:], encoding="utf-8")
