"""ANN forecaster for carbon intensity: temporal CNN over the past 96 h, residual target.

Same setup as forecast_v2.py: direct horizon h in {1, 24}, train 2021-23, early-stop on 2024,
test 2025, target = y - persistence, L1 loss (matches MAE). Inputs:
  window (96 h ending at t-h): carbon intensity, clean share, demand, missing-mask
  static (known at origin)    : hour/dow/day-of-year sin-cos, EIA day-ahead demand forecast at t,
                                forecast minus last observed demand
1 seed (CPU-only, compute-limited). Compared with persistence / seasonal-naive / LightGBM on the SAME rows.

Outputs: results/forecast_nn_metrics.csv, data/processed/forecast_nn_test_preds.parquet
"""
import glob
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from numpy.lib.stride_tricks import sliding_window_view

warnings.filterwarnings("ignore")
torch.set_num_threads(8)
ROOT = Path(__file__).resolve().parents[1]
W, HORIZONS, SEEDS = 96, [1, 24], [0]


def load() -> pd.DataFrame:
    ci = pd.read_parquet(ROOT / "data/processed/carbon_intensity.parquet")
    d = pd.concat(pd.read_parquet(f) for f in glob.glob(str(ROOT / "data/raw/eia930_demand/*.parquet")))
    d["ts"] = pd.to_datetime(d["period"], format="%Y-%m-%dT%H")
    d = d.pivot_table(index=["respondent", "ts"], columns="type", values="value").reset_index()
    return ci.merge(d, on=["respondent", "ts"], how="left")


def prepare(g: pd.DataFrame, h: int):
    s = g.set_index("ts").sort_index()
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="h"))
    ok = ~s["data_flag"].fillna(True).astype(bool)
    ci = s["ci_kg_per_mwh"].where(ok)
    train = s.index.year <= 2023
    stats = {}
    def stdz(x, name):
        m, sd = x[train].mean(), x[train].std()
        stats[name] = (m, sd)
        return ((x - m) / sd)
    ci_f = stdz(ci.ffill(limit=6), "ci").fillna(0).values
    cs_f = stdz(s["clean_share"].where(ok).ffill(limit=6), "cs").fillna(0).values
    D_raw = s["D"].ffill(limit=6)
    D_f = stdz(D_raw, "D").fillna(0).values
    miss = (~ok | ci.isna()).astype(float).values
    chans = np.stack([ci_f, cs_f, D_f, miss], axis=1)           # (T, 4)
    T = len(s)
    win = sliding_window_view(chans, W, axis=0)                  # (T-W+1, 4, W)
    idx = np.arange(W + h - 1, T)                                # target indices with a full window
    e = idx - h                                                  # window end index
    Xw = np.ascontiguousarray(win[e - (W - 1)]).astype(np.float32)
    loc = s.index[idx] - pd.Timedelta(hours=7)
    DF = stdz(s["DF"], "DF").values[idx]
    dfd = ((s["DF"].values[idx] - D_raw.values[e]) / (stats["D"][1] or 1))
    st = np.column_stack([
        np.sin(2 * np.pi * loc.hour / 24), np.cos(2 * np.pi * loc.hour / 24),
        np.sin(2 * np.pi * loc.dayofweek / 7), np.cos(2 * np.pi * loc.dayofweek / 7),
        np.sin(2 * np.pi * loc.dayofyear / 365.25), np.cos(2 * np.pi * loc.dayofyear / 365.25),
        np.nan_to_num(DF), np.nan_to_num(dfd), np.isnan(DF).astype(float)]).astype(np.float32)
    persist = ci.shift(h).values[idx]
    snaive = ci.shift(168).values[idx]
    y = ci.values[idx]
    return pd.DataFrame({"ts": s.index[idx], "y": y, "persist": persist, "snaive": snaive}), Xw, st


class Net(nn.Module):
    def __init__(self, n_static):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(4, 32, 5, padding=2), nn.GELU(),
            nn.Conv1d(32, 32, 5, stride=2, padding=2), nn.GELU(),
            nn.Conv1d(32, 48, 5, stride=2, padding=2), nn.GELU(),
            nn.Conv1d(48, 48, 5, stride=2, padding=2), nn.GELU())
        self.head = nn.Sequential(nn.Linear(48 * 2 + 4 * 6 + n_static, 128), nn.GELU(),
                                  nn.Dropout(0.1), nn.Linear(128, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, xw, st):
        z = self.conv(xw)
        feats = torch.cat([z.mean(-1), z.amax(-1), xw[:, :, -6:].flatten(1), st], dim=1)
        return self.head(feats).squeeze(-1)


def fit_predict(Xw, st, r, tr, va, seed):
    torch.manual_seed(seed); np.random.seed(seed)
    net = Net(st.shape[1])
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    f = lambda a: torch.from_numpy(a)
    Xt, St, Rt = f(Xw[tr]), f(st[tr]), f(r[tr].astype(np.float32))
    Xv, Sv, Rv = f(Xw[va]), f(st[va]), f(r[va].astype(np.float32))
    best, best_state, bad = 1e9, None, 0
    for ep in range(30):
        net.train()
        perm = torch.randperm(len(Xt))
        for i in range(0, len(perm), 512):
            b = perm[i:i + 512]
            opt.zero_grad()
            loss = nn.functional.smooth_l1_loss(net(Xt[b], St[b]), Rt[b], beta=0.5)
            loss.backward(); opt.step()
        net.eval()
        with torch.no_grad():
            v = (net(Xv, Sv) - Rv).abs().mean().item()
        if v < best - 1e-4:
            best, bad = v, 0
            best_state = {k: x.clone() for k, x in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 4:
                break
    net.load_state_dict(best_state)
    net.eval()
    return net, best, ep + 1


def metrics(y, p):
    e = p - y
    big = y > 50
    return {"n": len(y), "MAE": float(np.abs(e).mean()), "RMSE": float(np.sqrt((e ** 2).mean())),
            "MAPE": float((np.abs(e[big]) / y[big]).mean() * 100)}


def main() -> None:
    ci = load()
    v2 = pd.read_parquet(ROOT / "data/processed/forecast_v2_test_preds.parquet")
    outs, rows = [], []
    for ba, g in ci.groupby("respondent"):
        for h in HORIZONS:
            df, Xw, st = prepare(g, h)
            yr = df.ts.dt.year.values
            ok = df.y.notna().values & df.persist.notna().values
            r = (df.y - df.persist).values
            scale = np.nanstd(r[ok & (yr <= 2023)])
            rs = np.where(ok, r / scale, 0.0)
            tr, va = ok & (yr <= 2023), ok & (yr == 2024)
            preds = []
            for sd in SEEDS:
                net, best, eps = fit_predict(Xw, st, rs, tr, va, sd)
                with torch.no_grad():
                    pr = net(torch.from_numpy(Xw), torch.from_numpy(st)).numpy()
                preds.append(pr)
                print(f"{ba} h={h} seed={sd}: val MAE(resid, scaled)={best:.3f} epochs={eps}", flush=True)
            df["nn"] = df.persist + np.mean(preds, axis=0) * scale
            te = df[yr == 2025][["ts", "nn"]].assign(ba=ba, horizon_h=h)
            outs.append(te)
    nn_te = pd.concat(outs)
    m = v2.merge(nn_te, on=["ts", "ba", "horizon_h"], how="inner")
    m = m[m.nn.notna()]
    m.to_parquet(ROOT / "data/processed/forecast_nn_test_preds.parquet", index=False)
    cols = ["persist", "snaive", "resid_lags", "resid_demand", "nn"]
    for (ba, h), g in m.groupby(["ba", "horizon_h"]):
        for c in cols:
            rows.append({"ba": ba, "horizon_h": h, "model": c, **metrics(g.y.values, g[c].values)})
    R = pd.DataFrame(rows)
    R.to_csv(ROOT / "results/forecast_nn_metrics.csv", index=False)
    pd.set_option("display.width", 200)
    for h in HORIZONS:
        for metric in ("MAE", "MAPE"):
            print(f"\n=== Test 2025, h={h}h, {metric} (same rows) ===")
            print(R[R.horizon_h == h].pivot(index="ba", columns="model", values=metric)[cols].round(1).to_string())
    print("\nrows per BA/h:", R.groupby(["ba", "horizon_h"]).n.first().to_dict())


if __name__ == "__main__":
    main()
