"""Generate a fictional consumer-PC market for the battery-life investigation scenario.

Everything here is invented: manufacturers, models, documents, sell-out and consumer
signals. Parameters are hand-set; no real data is read. Output tables follow
`mei.contracts`. The answer key is written to a separate directory that the
application never reads.

Variants:
  positive  Product A has a genuine sales advantage over its launch cohort and a lower
            post-launch battery complaint rate.
  null      Product A behaves like its cohort (zero-effect control).
In both variants Product B outperforms only while its ASP is cut, and its complaints do
not fall; Product C is a battery-positioned model whose first observed sale is an
artefact of a panel coverage expansion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

GENERATOR_VERSION = "0.1.0"

OEMS = ["Altura", "Brevik", "Corvane", "Dunmore", "Elsari", "Fenwick"]
SEGMENTS = {
    # segment: (base monthly units, annual trend, base ASP, n models, form factor, sizes)
    "Premium Thin & Light": (60_000, 0.06, 1150, 34, "Notebook", ["13.3", "14", "14"]),
    "Mainstream": (150_000, -0.03, 700, 40, "Notebook", ["14", "15.6", "15.6"]),
    "Gaming": (50_000, 0.02, 1350, 30, "Notebook", ["15.6", "16", "17.3"]),
    "Budget": (120_000, -0.04, 400, 30, "Notebook", ["11.6", "14", "15.6"]),
}
SERIES = {
    "Premium Thin & Light": ["Aero", "Slate", "Lumen", "Feather", "Vista", "Halo"],
    "Mainstream": ["Core", "Daily", "Metro", "Ridge", "Civic", "Plain"],
    "Gaming": ["Raptor", "Volt", "Strike", "Forge", "Nova", "Blaze"],
    "Budget": ["Basic", "Go", "Lite", "Start", "Value", "Easy"],
}
SEASONALITY = np.array([0.85, 0.80, 0.90, 0.85, 0.90, 0.95, 1.05, 1.25, 1.00, 0.95, 1.35, 1.50])
SEASONALITY = SEASONALITY / SEASONALITY.mean()

HIST_START = (2021, 1)
N_MONTHS = 60                 # 2021-M01 .. 2025-M12
COVERAGE_EXPANSION = 15       # month index (2022-M04) when the panel adds retailers
TARGET_SEG = "Premium Thin & Light"


def p_str(i: int) -> str:
    y, m = HIST_START[0] + (HIST_START[1] - 1 + i) // 12, (HIST_START[1] - 1 + i) % 12 + 1
    return f"{y}-M{m:02d}"


@dataclass
class Product:
    pid: str
    oem: str
    model: str
    segment: str
    size: str
    launch: int            # true commercial launch (month index; may be < 0 = before history)
    life: int
    attract: float
    asp0: float
    battery_hr: float
    role: str = "background"


def _lifecycle(age: np.ndarray, life: int) -> np.ndarray:
    ramp = np.select([age == 0, age == 1], [0.35, 0.70], 1.0)
    plateau_end = int(life * 0.6)
    decline = np.where(age > plateau_end, 1.0 - 0.8 * (age - plateau_end) / max(life - plateau_end, 1), 1.0)
    out = ramp * np.clip(decline, 0.2, 1.0)
    return np.where((age >= 0) & (age < life), out, 0.0)


def build_products(rng: np.random.Generator, variant: str) -> tuple[list[Product], dict]:
    products: list[Product] = []
    counter = 0

    def new(segment, launch, attract=None, battery=None, role="background", oem=None):
        nonlocal counter
        counter += 1
        base_units, trend, base_asp, _, _, sizes = SEGMENTS[segment]
        oem = oem or rng.choice(OEMS)
        series = rng.choice(SERIES[segment])
        size = rng.choice(sizes)
        gen = 1 + (max(launch, -18) + 18) // 14
        model = f"{oem} {series} {size.split('.')[0]} G{gen}"
        if battery is None:
            battery = {"Premium Thin & Light": rng.uniform(9, 13), "Mainstream": rng.uniform(7, 11),
                       "Gaming": rng.uniform(4, 7), "Budget": rng.uniform(6, 10)}[segment]
        p = Product(
            pid=f"P{counter:04d}", oem=str(oem), model=model, segment=segment, size=str(size),
            launch=int(launch), life=int(rng.integers(20, 34)),
            attract=float(attract if attract is not None else rng.lognormal(0, 0.45)),
            asp0=float(base_asp * rng.lognormal(0, 0.12)), battery_hr=float(battery), role=role,
        )
        products.append(p)
        return p

    # background launches across (and before) the history window
    for seg, (_, _, _, n_models, _, _) in SEGMENTS.items():
        for _ in range(n_models):
            new(seg, int(rng.integers(-18, N_MONTHS - 4)))

    # scenario products ------------------------------------------------------
    oems = list(rng.permutation(OEMS))
    la = int(rng.integers(29, 34))                      # A launches 2023-M06 .. 2023-M10
    lb = la + int(rng.integers(1, 3))
    # cohort: guarantee enough comparable premium thin-and-light launches near A
    for off in [-5, -4, -3, -2, -1, 1, 2, 3, 4, 5]:
        new(TARGET_SEG, la + off, attract=float(rng.lognormal(0, 0.35)))
    effect = 3.0 if variant == "positive" else 1.0
    a = new(TARGET_SEG, la, attract=1.0 * effect, battery=rng.uniform(19, 21), role="A", oem=oems[0])
    b = new(TARGET_SEG, lb, attract=1.0, battery=rng.uniform(16, 18), role="B", oem=oems[1])
    for p in (a, b):                              # keep A and B near the segment's typical price
        p.asp0 = SEGMENTS[TARGET_SEG][2] * float(rng.uniform(0.95, 1.05))
    c = new(TARGET_SEG, COVERAGE_EXPANSION - int(rng.integers(5, 8)), attract=1.3,
            battery=rng.uniform(18, 20), role="C", oem=oems[2])
    g = new("Gaming", la - 2, battery=rng.uniform(8, 9), role="G", oem=oems[3])
    # other models whose pre-expansion history the panel did not track
    hidden = [p for p in products if p.role == "background" and 3 <= p.launch < COVERAGE_EXPANSION - 2]
    hidden = list(rng.choice(hidden, size=min(11, len(hidden)), replace=False))
    for p in hidden:
        p.role = "coverage_hidden"
    # shuffle IDs so creation order (scenario products last) leaks nothing
    perm = rng.permutation(len(products))
    for p, k in zip(products, perm):
        p.pid = f"P{int(k) + 1:04d}"
    products.sort(key=lambda p: p.pid)
    roles = {"A": a.pid, "B": b.pid, "C": c.pid, "G": g.pid, "launch_A": la, "launch_B": lb}
    return products, roles


def build_sellout(rng, products: list[Product], roles: dict) -> pd.DataFrame:
    t = np.arange(N_MONTHS)
    rows = []
    by_seg: dict[str, list[Product]] = {}
    for p in products:
        by_seg.setdefault(p.segment, []).append(p)
    lb = roles["launch_B"]
    for seg, plist in by_seg.items():
        base, trend, *_ = SEGMENTS[seg]
        demand = base * (1 + trend) ** (t / 12) * SEASONALITY[(t + HIST_START[1] - 1) % 12]
        weights = np.array([p.attract * _lifecycle(t - p.launch, p.life) for p in plist])
        boost = np.ones_like(weights)
        asp_mult = np.ones_like(weights)
        for i, p in enumerate(plist):
            if p.role == "B":                       # price cut months 3-6 after launch
                cut = (t >= lb + 3) & (t <= lb + 6)
                asp_mult[i, cut] = 0.80
                boost[i, cut] = 1.8
            elif p.role == "background" and rng.random() < 0.06:   # unflagged price events elsewhere
                s = int(rng.integers(max(p.launch, 0) + 2, max(p.launch, 0) + 12))
                cut = (t >= s) & (t < s + 2)
                asp_mult[i, cut] = 0.86
                boost[i, cut] = 1.45
        eff = weights * boost
        share = eff / np.maximum(eff.sum(axis=0), 1e-9)
        for i, p in enumerate(plist):
            for j in t:
                if weights[i, j] <= 0:
                    continue
                if p.role in ("coverage_hidden", "C") and j < COVERAGE_EXPANSION:
                    continue                          # not tracked by the panel yet
                units_total = rng.poisson(max(demand[j] * share[i, j], 0.1))
                if units_total == 0:
                    continue
                age = j - p.launch
                asp = p.asp0 * (1 - 0.008 * age) * asp_mult[i, j] * rng.lognormal(0, 0.02)
                online = rng.binomial(units_total, 0.45)
                for ch, u in (("Retail Online", online), ("Retail Offline", units_total - online)):
                    if u == 0:
                        continue
                    row_asp = asp * rng.lognormal(0, 0.01)
                    lo = int(row_asp // 100 * 100)
                    rows.append({
                        "period_month": p_str(j), "source": "PANEL_SO_US", "country": "US",
                        "channel_type": ch, "product_id": p.pid,
                        "price_band": f"${lo}-${lo + 99}",
                        "battery_run_time": "N/A" if rng.random() < 0.12 else f"{p.battery_hr:.0f} hr",
                        "cpu_family": f"CPU_FAM_{chr(ord('Q') + max(0, min(5, (p.launch + 18) // 14)))}",
                        "units": int(u), "revenue_usd": round(float(u * row_asp), 2),
                    })
    return pd.DataFrame(rows).sort_values(["period_month", "product_id", "channel_type"]).reset_index(drop=True)


def battery_segment_rate(seg: str, j: int) -> float:
    if seg != TARGET_SEG:
        return 0.040
    if j < 18:
        return 0.050
    if j < 27:
        return 0.050 + (0.100 - 0.050) * (j - 18) / 9
    if j < 42:
        return 0.100
    return 0.085


def build_signals(rng, products: list[Product], sell: pd.DataFrame, variant: str) -> pd.DataFrame:
    units = sell.groupby(["period_month", "product_id"])["units"].sum()
    prod = {p.pid: p for p in products}
    month_idx = {p_str(k): k for k in range(N_MONTHS)}
    persistent = {p.pid: (1.0 if p.role in ("A", "B", "C") else float(rng.lognormal(0, 0.25)))
                  for p in products}   # persistent product-level complaint factor
    rows = []
    for (pm, pid), u in units.items():
        p = prod[pid]
        j = month_idx[pm]
        comments = int(rng.poisson(max(5.0, u * 0.03)))
        if comments == 0:
            continue
        authors = int(round(comments * rng.uniform(0.85, 0.97)))
        factor = rng.lognormal(0, 0.15) * persistent[pid]
        for theme in ("battery", "thermals", "display"):
            if theme == "battery":
                rate = battery_segment_rate(p.segment, j) * factor
                if p.role == "A" and variant == "positive":
                    rate *= 0.45
            else:
                rate = {"thermals": 0.03, "display": 0.025}[theme] * factor
            true_c = rng.binomial(comments, min(rate, 0.9))
            other = rng.binomial(comments - true_c, 0.06)
            # classifier-like noise: misses some complaints, mislabels a few other mentions
            obs_c = rng.binomial(true_c, 0.85) + rng.binomial(other, 0.03)
            rows.append({
                "period_month": pm, "product_id": pid, "segment": p.segment, "theme": theme,
                "comments": comments, "theme_mentions": int(true_c + other),
                "complaints": int(obs_c), "unique_authors": authors,
            })
    return pd.DataFrame(rows).sort_values(["period_month", "product_id", "theme"]).reset_index(drop=True)


SPEC_TEMPLATE = ("{model} spec sheet. {size}-inch display, {cpu} processor, {mem} GB memory, "
                 "{wh} Wh battery, {weight} kg. Ports: USB-C, USB-A, HDMI.")
ANNOUNCE = {
    "A": "Introducing the {model}: engineered for endurance, with up to {hr} hours of battery life "
         "so you can work a full day and evening without a charger.",
    "B": "The new {model} brings all-day battery that lasts up to {hr} hours, in a design under 1.3 kg.",
    "C": "Meet the {model}: up to {hr} hours of battery life and a brilliant OLED display.",
    "G": "The {model} delivers a long-lasting battery for gaming on the go and a 165 Hz display.",
}
DISTRACT = [
    "The {model} features a vivid display with 100% sRGB coverage and a refined aluminium chassis.",
    "Performance unleashed: the {model} pairs the latest processors with advanced cooling.",
    "The {model} adds intelligent battery saver mode and battery health monitoring in the companion app.",
    "Lighter than ever, the {model} weighs just 1.2 kg and opens with one hand.",
    "The {model} brings a quieter fan profile and a larger touchpad.",
]


def build_docs(rng, products: list[Product]) -> pd.DataFrame:
    rows = []
    for p in products:
        pub = max(p.launch - 1, -24)
        pm = p_str(pub) if pub >= 0 else f"{2021 + (pub // 12)}-M{pub % 12 + 1:02d}"
        rows.append({
            "doc_id": f"D{p.pid[1:]}S", "product_id": p.pid, "doc_type": "spec_sheet", "published_month": pm,
            "text": SPEC_TEMPLATE.format(model=p.model, size=p.size, cpu=f"CPU_FAM_{rng.integers(1, 6)}",
                                         mem=int(rng.choice([8, 16, 16, 32])), wh=int(30 + p.battery_hr * 3.2),
                                         weight=round(float(rng.uniform(1.1, 2.6)), 1)),
        })
        if p.role in ANNOUNCE:
            text = ANNOUNCE[p.role].format(model=p.model, hr=int(round(p.battery_hr)))
        elif rng.random() < 0.55:
            text = rng.choice(DISTRACT).format(model=p.model)
        else:
            continue
        rows.append({"doc_id": f"D{p.pid[1:]}A", "product_id": p.pid, "doc_type": "announcement",
                     "published_month": pm, "text": text})
    return pd.DataFrame(rows).sort_values("doc_id").reset_index(drop=True)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(seed: int, variant: str, out_root: Path, key_root: Path) -> dict:
    assert variant in ("positive", "null")
    rng = np.random.default_rng(seed)
    products, roles = build_products(rng, variant)
    sell = build_sellout(rng, products, roles)
    signals = build_signals(rng, products, sell, variant)
    docs = build_docs(rng, products)
    observed = set(sell["product_id"])
    prod_df = pd.DataFrame([{
        "product_id": p.pid, "oem": p.oem, "model": p.model, "form_factor": SEGMENTS[p.segment][4],
        "segment": p.segment, "screen_size": p.size,
    } for p in products if p.pid in observed])
    docs = docs[docs["product_id"].isin(observed)]

    scenario_id = f"battery_s{seed}"
    out = out_root / scenario_id
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "products.csv": prod_df, "sellout_monthly.csv": sell,
        "product_docs.csv": docs, "signal_counts.csv": signals,
    }
    for name, df in files.items():
        df.to_csv(out / name, index=False)
    manifest = {
        "scenario_id": scenario_id, "generator_version": GENERATOR_VERSION, "synthetic": True,
        "history": [p_str(0), p_str(N_MONTHS - 1)], "source": "PANEL_SO_US (fictional)",
        "files": {n: _sha(out / n) for n in files},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # ---------------- answer key: written OUTSIDE the data directory ----------------
    key = {
        "scenario_id": scenario_id, "seed": seed, "variant": variant,
        "roles": {k: roles[k] for k in ("A", "B", "C", "G")},
        "true_launch_month": {"A": p_str(roles["launch_A"]), "B": p_str(roles["launch_B"])},
        "coverage_expansion_month": p_str(COVERAGE_EXPANSION),
        "expected": {
            "signal_rising_in_segment": TARGET_SEG,
            "A": {"positioned_on_battery": True,
                  "sales_outperformance": variant == "positive",
                  "lower_battery_complaints": variant == "positive"},
            "B": {"positioned_on_battery": True, "price_volume_pattern": True,
                  "lower_battery_complaints": False},
            "C": {"positioned_on_battery": True, "first_sale_flag": "coverage_expansion"},
            "G": {"positioned_on_battery": True, "segment_mismatch": True},
        },
    }
    key_root.mkdir(parents=True, exist_ok=True)
    (key_root / f"{scenario_id}.json").write_text(json.dumps(key, indent=2))
    return {"scenario_id": scenario_id, "data_dir": str(out), "rows": {k: len(v) for k, v in files.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate a synthetic battery-life scenario.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--variant", choices=["positive", "null"], default="positive")
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--keys", default="evaluation/answer_keys")
    a = ap.parse_args(argv)
    print(json.dumps(generate(a.seed, a.variant, Path(a.out), Path(a.keys)), indent=2))


if __name__ == "__main__":
    main()
