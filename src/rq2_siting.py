"""RQ2: transparent site-suitability ranking over 192 Arizona cells (0.25 deg).

IMPORTANT (state this in the report): there is no observed ground truth for "suitable".
suitability = weighted mean of percentile ranks of criteria; label = top tercile. The ML models
are then trained on that label from the SAME features, so their AUC is a RECONSTRUCTION check,
not validation. The informative outputs are (1) rank stability under random weights,
(2) leave-county-out generalisation, (3) SHAP/coefficients (which recover the weights), and
(4) a face-validity look at where publicly reported Arizona data-center clusters fall.

Criteria (direction): gw_depth_med (-), gw_trend (-, missing -> neutral 0.5), wetbulb_summer_c (-),
ghi_kwh (+), q_active_mw (-, county-level generator-queue strain; direction is an assumption).
Default weights are an assumption: depth .30, trend .10, wetbulb .20, ghi .15, queue .25.

Outputs: results/rq2_*.csv, data/processed/sites_scored.parquet
"""
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from scipy.stats import spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
CRIT = {"gw_depth_med": (-1, 0.30), "gw_trend": (-1, 0.10), "wetbulb_summer_c": (-1, 0.20),
        "ghi_kwh": (+1, 0.15), "q_active_mw": (-1, 0.25)}
HUBS = {  # approximate city centres of publicly reported data-center clusters (face-validity only)
    "Chandler": (33.30, -111.84), "Mesa": (33.42, -111.83), "Goodyear": (33.44, -112.36),
    "Phoenix-DeerValley": (33.68, -112.08), "Tucson": (32.22, -110.97),
    "Marana": (32.44, -111.20), "CasaGrande": (32.88, -111.75)}


def pct(s, sign):
    r = s.rank(pct=True, method="average")
    return r if sign > 0 else 1 - r


def score(d, w):
    comp = pd.DataFrame({c: pct(d[c], CRIT[c][0]) for c in CRIT})
    comp["gw_trend"] = comp["gw_trend"].where(d.gw_trend.notna(), 0.5)  # neutral when unobserved
    W = np.array([w[c] for c in CRIT]); W = W / W.sum()
    return comp.values @ W, comp


def main() -> None:
    d = pd.read_parquet(ROOT / "data/processed/sites_az.parquet").reset_index(drop=True)
    w0 = {c: CRIT[c][1] for c in CRIT}
    d["score"], comp = score(d, w0)
    d["rank"] = d.score.rank(ascending=False, method="first").astype(int)
    d["suitable"] = (d.score >= d.score.quantile(2 / 3)).astype(int)

    # ---- (1) rank stability under random weights (Dirichlet(1) over the 5 criteria)
    rng = np.random.default_rng(0)
    N = 2000
    ranks = np.empty((N, len(d)))
    top = np.zeros(len(d))
    for i in range(N):
        w = dict(zip(CRIT, rng.dirichlet(np.ones(len(CRIT)))))
        s, _ = score(d, w)
        r = pd.Series(s).rank(ascending=False, method="first").values
        ranks[i] = r
        top += r <= 0.10 * len(d)
    d["p_top10"] = top / N
    d["rank_lo"], d["rank_hi"] = np.percentile(ranks, 5, axis=0), np.percentile(ranks, 95, axis=0)
    rho = np.array([spearmanr(d["rank"], ranks[i])[0] for i in range(N)])
    print(f"Rank stability vs default: median Spearman rho = {np.median(rho):.2f} "
          f"(5th pct {np.percentile(rho, 5):.2f}) over {N} random weight vectors")
    print(f"Cells in top 10% in >=80% of draws: {(d.p_top10 >= 0.8).sum()} | >=50%: {(d.p_top10 >= 0.5).sum()} "
          f"| never: {(d.p_top10 == 0).sum()}")

    # ---- (2) models on the constructed label (reconstruction check)
    feats = list(CRIT)
    X = d[feats].copy()
    X["trend_missing"] = X.gw_trend.isna().astype(float)
    Xl = X.fillna({"gw_trend": X.gw_trend.median()})
    y = d.suitable.values
    groups = d.county_short.values
    res = []
    def cv(model_fn, Xm, splitter, name, cvname):
        oof = np.zeros(len(y))
        for tr, te in splitter:
            m = model_fn(); m.fit(Xm.iloc[tr] if hasattr(Xm, "iloc") else Xm[tr], y[tr])
            oof[te] = m.predict_proba(Xm.iloc[te])[:, 1]
        res.append({"model": name, "cv": cvname, "auc": roc_auc_score(y, oof)})
        return oof
    lr = lambda: __import__("sklearn.pipeline", fromlist=["make_pipeline"]).make_pipeline(
        StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    gb = lambda: lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, num_leaves=8, min_child_samples=5,
                                    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
    skf = list(StratifiedKFold(5, shuffle=True, random_state=0).split(Xl, y))
    gkf = list(GroupKFold(n_splits=min(6, len(set(groups)))).split(Xl, y, groups))
    cv(lr, Xl, skf, "logistic", "random 5-fold")
    cv(lr, Xl, gkf, "logistic", "leave-county-out")
    cv(gb, X, skf, "lightgbm", "random 5-fold")
    oof = cv(gb, X, gkf, "lightgbm", "leave-county-out")
    R = pd.DataFrame(res); R.to_csv(ROOT / "results/rq2_auc.csv", index=False)
    print("\nReconstruction AUC (label is a function of the features -> NOT validation):")
    print(R.round(3).to_string(index=False))

    # calibration of the leave-county-out LightGBM probabilities
    bins = pd.cut(oof, [0, .2, .4, .6, .8, 1.0], include_lowest=True)
    print("\nCalibration (leave-county-out LightGBM): predicted-prob bin -> observed suitable rate")
    print(pd.DataFrame({"bin": bins, "y": y}).groupby("bin").y.agg(["size", "mean"]).round(2).to_string())

    # ---- (3) SHAP on a full-data model + logistic coefficients
    m = gb(); m.fit(X, y)
    sv = shap.TreeExplainer(m).shap_values(X)
    sv = sv[1] if isinstance(sv, list) else sv
    imp = pd.Series(np.abs(sv).mean(axis=0), index=X.columns).sort_values(ascending=False)
    lrm = lr(); lrm.fit(Xl, y)
    coef = pd.Series(lrm[-1].coef_[0], index=Xl.columns)
    out = pd.DataFrame({"mean_abs_shap": imp, "logit_coef_std": coef}).round(3)
    out.to_csv(ROOT / "results/rq2_importance.csv")
    print("\nFeature importance (SHAP, standardised logit coefficients):"); print(out.to_string())
    d["shap_top_driver"] = np.array(X.columns)[np.abs(sv).argmax(axis=1)]

    # ---- (4) face validity vs reported hubs
    from sklearn.neighbors import BallTree
    tree = BallTree(np.radians(d[["lat", "lon"]].values), metric="haversine")
    rows = []
    for k, (la, lo) in HUBS.items():
        dist, idx = tree.query(np.radians([[la, lo]]), k=1)
        i = idx[0, 0]
        rows.append({"hub": k, "cell": d.cell_id[i], "dist_km": dist[0, 0] * 6371, "rank_of_192": int(d["rank"][i]),
                     "score_pct": round(100 * (d.score < d.score[i]).mean()), "gw_depth_ft": d.gw_depth_med[i],
                     "wetbulb_c": d.wetbulb_summer_c[i], "p_top10": d.p_top10[i]})
    H = pd.DataFrame(rows); H.to_csv(ROOT / "results/rq2_hub_check.csv", index=False)
    print("\nWhere reported data-center hubs fall (approximate city centres; face-validity only):")
    print(H.round(2).to_string(index=False))

    cols = ["cell_id", "county_short", "lat", "lon", "score", "rank", "rank_lo", "rank_hi", "p_top10",
            "gw_depth_med", "gw_trend", "wetbulb_summer_c", "ghi_kwh", "q_active_mw", "shap_top_driver"]
    d.sort_values("rank")[cols].to_csv(ROOT / "results/rq2_scores.csv", index=False)
    d.to_parquet(ROOT / "data/processed/sites_scored.parquet", index=False)
    print("\nTop 12 cells (default weights):")
    print(d.sort_values("rank").head(12)[["cell_id", "county_short", "lat", "lon", "score", "rank_lo", "rank_hi",
                                          "p_top10", "gw_depth_med", "wetbulb_summer_c", "q_active_mw"]].round(2).to_string(index=False))
    print("\nBy county: mean score / n cells in top tercile")
    print(d.groupby("county_short").agg(n=("cell_id", "size"), mean_score=("score", "mean"),
                                        n_suitable=("suitable", "sum")).round(2).sort_values("mean_score", ascending=False).to_string())


if __name__ == "__main__":
    main()
