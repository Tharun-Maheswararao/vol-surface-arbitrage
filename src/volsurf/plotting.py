"""Figures for the report (matplotlib) and the app (plotly).

Every function takes the dict returned by ``pipeline.load_results`` and only
draws; nothing here fits or computes arbitrage.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

from .essvi import essvi_w
from .ssvi import ssvi_w
from .svi import svi_w

# Categorical slots (fixed order) and neutral inks
COLORS = {"svi": "#2a78d6", "ssvi": "#eb6834", "ssvi_free": "#1baf7a", "essvi": "#8c4fd6"}
LABELS = {"svi": "SVI", "ssvi": "SSVI", "ssvi_free": "SSVI (unconstrained)", "essvi": "eSSVI"}
INK, INK_2, INK_3, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
QUOTE = "#6f6e69"
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SEQ = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)


def _style(ax, xlabel=None, ylabel=None):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK_3)
    ax.tick_params(colors=INK_2, labelsize=8)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK_2, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK_2, fontsize=9)


def _grid(n, ncols=3, size=(4.2, 3.0)):
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(size[0] * ncols, size[1] * nrows), squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    return fig, axes.flat


def expiries(res):
    return list(res["forwards"].sort_values("T")["expiry"])


def model_w(res, model, expiry, k):
    if model == "svi":
        return svi_w(k, res["svi"][expiry])
    if model == "essvi":
        p = res["essvi"]
        return essvi_w(k, *p.slice(list(p.expiries).index(expiry)))
    p = res["ssvi"] if model == "ssvi" else res["ssvi_free"]
    i = list(p.expiries).index(expiry)
    return ssvi_w(k, p.thetas[i], p.rho, p.eta, p.gamma)


# ----------------------------------------------------------------------------- matplotlib


def smiles_figure(res, models=("svi", "ssvi")):
    exps = expiries(res)
    fig, axes = _grid(len(exps))
    for ax, e in zip(axes, exps):
        q = res["quotes"][res["quotes"].expiry == e]
        T = q["T"].iloc[0]
        ax.vlines(q["k"], 100 * q["iv_bid"], 100 * q["iv_ask"], color=QUOTE, lw=0.8, alpha=0.8,
                  label="bid-ask vol")
        k = np.linspace(q["k"].min(), q["k"].max(), 400)
        for m in models:
            ax.plot(k, 100 * np.sqrt(model_w(res, m, e, k) / T), color=COLORS[m], lw=1.6,
                    ls="--" if m == "ssvi_free" else "-", label=LABELS[m])
        _style(ax, "log-moneyness k", "implied vol (%)")
        ax.set_title(f"{e}  (T={T:.3f}y)", fontsize=9, color=INK, loc="left")
    axes[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Smiles: bid-ask implied vol bars and fitted curves", color=INK, x=0.01, ha="left")
    fig.tight_layout()
    return fig


def total_variance_figure(res, model="svi", k_range=(-2.5, 1.0)):
    """All fitted slices on one axis; crossing slices are calendar arbitrage."""
    exps = expiries(res)
    c = res["curves"]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    fig.patch.set_facecolor(SURFACE)
    cols = SEQ(np.linspace(0.25, 1.0, len(exps)))
    for e, col in zip(exps, cols):
        d = c[c.expiry == e]
        m = (d.k >= k_range[0]) & (d.k <= k_range[1])
        ax.plot(d.k[m], d[f"w_{model}"][m], color=col, lw=1.4, label=e)
    for rep in res["fitted_arbitrage"][model]["calendar"].values():
        for lo, hi in rep["crossing_intervals"]:
            ax.axvspan(lo, hi, color="#e34948", alpha=0.06, lw=0)
    _style(ax, "log-moneyness k", "total implied variance w")
    ax.set_title(f"{LABELS[model]} total variance slices (shaded: some pair crosses)",
                 fontsize=10, color=INK, loc="left")
    ax.legend(fontsize=7, frameon=False, ncol=2, title="expiry", title_fontsize=7)
    fig.tight_layout()
    return fig


def g_figure(res, models=("svi", "ssvi")):
    exps = expiries(res)
    c = res["curves"]
    fig, axes = _grid(len(exps))
    for ax, e in zip(axes, exps):
        d = c[c.expiry == e]
        q = res["quotes"][res["quotes"].expiry == e]
        ax.axvspan(q.k.min(), q.k.max(), color=GRID, alpha=0.5, lw=0, label="quoted k range")
        ax.axhline(0, color=INK_3, lw=0.8)
        for m in models:
            ax.plot(d.k, d[f"g_{m}"], color=COLORS[m], lw=1.4, label=LABELS[m],
                    ls="--" if m == "ssvi_free" else "-")
            neg = d[f"g_{m}"] < 0
            if neg.any():
                ax.fill_between(d.k, d[f"g_{m}"], 0, where=neg, color="#e34948", alpha=0.25, lw=0)
        lo = min(-0.25, np.percentile(np.concatenate([d[f"g_{m}"] for m in models]), 1))
        ax.set_ylim(lo, 1.6)
        _style(ax, "log-moneyness k", "g(k)")
        rep = res["fitted_arbitrage"]["svi"]["butterfly"][e]
        ax.set_title(f"{e}   SVI min g = {rep['min_g']:.3f}", fontsize=9, color=INK, loc="left")
    axes[0].legend(fontsize=7, frameon=False, loc="upper left")
    fig.suptitle("Gatheral's g(k): negative values are butterfly arbitrage", color=INK, x=0.01, ha="left")
    fig.tight_layout()
    return fig


def density_figure(res, model="ssvi", k_range=(-0.8, 0.4)):
    exps = expiries(res)
    c = res["curves"]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    fig.patch.set_facecolor(SURFACE)
    cols = SEQ(np.linspace(0.25, 1.0, len(exps)))
    for e, col in zip(exps, cols):
        d = c[(c.expiry == e) & c.k.between(*k_range)]
        ax.plot(d.k, d[f"density_{model}"], color=col, lw=1.4, label=e)
    ax.axhline(0, color=INK_3, lw=0.8)
    _style(ax, "log-moneyness k = ln(K/F)", "density of ln(S_T/F)")
    ax.set_title(f"Risk-neutral density implied by the {LABELS[model]} fit", fontsize=10, color=INK,
                 loc="left")
    ax.legend(fontsize=7, frameon=False, ncol=2, title="expiry", title_fontsize=7)
    fig.tight_layout()
    return fig


def surface_grid(res, model="ssvi", k_range=(-0.6, 0.3), nk=61, nT=60):
    """Implied vol on a (k, T) grid. SSVI interpolates theta linearly in T; eSSVI
    interpolates theta, psi and rho*psi linearly in T (ESSVIParams.slice_at); SVI
    interpolates total variance linearly in T at fixed k between fitted expiries."""
    Ts_e = res["forwards"].sort_values("T")["T"].values
    exps = expiries(res)
    k = np.linspace(*k_range, nk)
    T = np.linspace(Ts_e[0], Ts_e[-1], nT)
    if model in ("ssvi", "ssvi_free"):
        p = res["ssvi"] if model == "ssvi" else res["ssvi_free"]
        th = p.theta_at(T)
        W = np.array([ssvi_w(k, t, p.rho, p.eta, p.gamma) for t in th])
    elif model == "essvi":
        W = np.array([essvi_w(k, *res["essvi"].slice_at(t)) for t in T])
    else:
        We = np.array([svi_w(k, res["svi"][e]) for e in exps])
        W = np.array([[np.interp(t, Ts_e, We[:, j]) for j in range(nk)] for t in T])
    return k, T, 100 * np.sqrt(np.maximum(W, 0) / T[:, None])


def surface_figure(res, model="ssvi", elev=25, azim=-60, ax=None):
    k, T, V = surface_grid(res, model)
    KK, TT = np.meshgrid(k, T)
    if ax is None:
        fig = plt.figure(figsize=(8, 6))
        fig.patch.set_facecolor(SURFACE)
        ax = fig.add_subplot(projection="3d")
    else:
        fig = ax.figure
    ax.plot_surface(KK, TT, V, cmap=SEQ, linewidth=0, antialiased=True, alpha=0.95)
    q = res["quotes"]
    q = q[q.k.between(k[0], k[-1])]
    ax.scatter(q.k, q["T"], 100 * q.iv_mid, s=2, color=INK_2, alpha=0.5, depthshade=False)
    ax.set_xlabel("k", color=INK_2)
    ax.set_ylabel("T (years)", color=INK_2)
    ax.set_zlabel("implied vol (%)", color=INK_2)
    ax.view_init(elev=elev, azim=azim)
    ax.set_title(f"{LABELS[model]} implied volatility surface (dots: mid quotes)", color=INK, fontsize=10)
    return fig


def save_all_figures(result_dir, out_dir=None) -> list[Path]:
    from .pipeline import load_results

    res = load_results(result_dir)
    out = Path(out_dir) if out_dir else Path(result_dir) / "figures"
    out.mkdir(parents=True, exist_ok=True)
    figs = {
        "smiles.png": smiles_figure(res),
        "smiles_with_unconstrained.png": smiles_figure(res, ("svi", "ssvi", "ssvi_free")),
        "ssvi_surface.png": surface_figure(res, "ssvi"),
        "svi_surface.png": surface_figure(res, "svi"),
        "g_function.png": g_figure(res),
        "density_ssvi.png": density_figure(res, "ssvi"),
        "density_svi.png": density_figure(res, "svi"),
        "total_variance_svi.png": total_variance_figure(res, "svi"),
        "total_variance_ssvi.png": total_variance_figure(res, "ssvi"),
    }
    if res["essvi"] is not None:  # results written before eSSVI was added have none
        figs |= {
            "smiles_with_essvi.png": smiles_figure(res, ("svi", "ssvi", "essvi")),
            "essvi_surface.png": surface_figure(res, "essvi"),
            "density_essvi.png": density_figure(res, "essvi"),
            "total_variance_essvi.png": total_variance_figure(res, "essvi"),
        }
    paths = []
    for name, fig in figs.items():
        p = out / name
        fig.savefig(p, dpi=130, facecolor=fig.get_facecolor())
        plt.close(fig)
        paths.append(p)
    return paths


def rotating_gif(result_dir, path, frames=48, fps=12):
    """Rotate the surface while toggling SVI and SSVI every half turn."""
    from matplotlib.animation import FuncAnimation, PillowWriter

    from .pipeline import load_results

    res = load_results(result_dir)
    fig = plt.figure(figsize=(6.4, 4.8))
    fig.patch.set_facecolor(SURFACE)
    ax = fig.add_subplot(projection="3d")

    def draw(i):
        ax.clear()
        model = "svi" if (i // (frames // 4)) % 2 == 0 else "ssvi"
        surface_figure(res, model, elev=22, azim=-60 + 360 * i / frames, ax=ax)

    anim = FuncAnimation(fig, draw, frames=frames)
    anim.save(path, writer=PillowWriter(fps=fps), dpi=80)
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------- plotly (app)


def plotly_surface(res, models=("ssvi",)):
    import plotly.graph_objects as go

    fig = go.Figure()
    scales = {"svi": "Blues", "ssvi": "Oranges", "ssvi_free": "Teal", "essvi": "Purples"}
    for m in models:
        k, T, V = surface_grid(res, m)
        fig.add_trace(go.Surface(x=k, y=T, z=V, name=LABELS[m], colorscale=scales[m], showscale=False,
                                 opacity=0.9 if len(models) > 1 else 1.0, showlegend=True,
                                 hovertemplate="k=%{x:.3f}<br>T=%{y:.3f}y<br>vol=%{z:.2f}%<extra>"
                                               + LABELS[m] + "</extra>"))
    fig.update_layout(scene=dict(xaxis_title="log-moneyness k", yaxis_title="T (years)",
                                 zaxis_title="implied vol (%)"),
                      height=620, margin=dict(l=0, r=0, t=30, b=0), legend=dict(x=0, y=1))
    return fig


def plotly_smile(res, expiry, models=("svi", "ssvi")):
    import plotly.graph_objects as go

    q = res["quotes"][res["quotes"].expiry == expiry]
    T = q["T"].iloc[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=q.k, y=100 * q.iv_mid, mode="markers", name="mid (bars: bid-ask)",
        marker=dict(size=5, color=QUOTE),
        error_y=dict(type="data", symmetric=False, array=100 * (q.iv_ask - q.iv_mid),
                     arrayminus=100 * (q.iv_mid - q.iv_bid), color=QUOTE, thickness=1, width=0),
        customdata=np.column_stack([q.strike, q.type, 100 * q.iv_bid, 100 * q.iv_ask]),
        hovertemplate="K=%{customdata[0]:.0f} %{customdata[1]}<br>bid %{customdata[2]:.2f}% / "
                      "ask %{customdata[3]:.2f}%<extra></extra>"))
    k = np.linspace(q.k.min(), q.k.max(), 400)
    for m in models:
        fig.add_trace(go.Scatter(x=k, y=100 * np.sqrt(model_w(res, m, expiry, k) / T), mode="lines",
                                 name=LABELS[m], line=dict(color=COLORS[m], width=2,
                                                           dash="dash" if m == "ssvi_free" else "solid")))
    fig.update_layout(xaxis_title="log-moneyness k", yaxis_title="implied vol (%)", height=460,
                      hovermode="closest", margin=dict(l=10, r=10, t=30, b=10),
                      title=f"{expiry}  (T = {T:.3f} years)")
    return fig


def plotly_g(res, expiry, models=("svi", "ssvi")):
    import plotly.graph_objects as go

    d = res["curves"][res["curves"].expiry == expiry]
    q = res["quotes"][res["quotes"].expiry == expiry]
    fig = go.Figure()
    fig.add_vrect(x0=q.k.min(), x1=q.k.max(), fillcolor=GRID, opacity=0.5, line_width=0,
                  annotation_text="quoted range", annotation_position="top left")
    fig.add_hline(y=0, line_color=INK_3, line_width=1)
    for m in models:
        fig.add_trace(go.Scatter(x=d.k, y=d[f"g_{m}"], mode="lines", name=LABELS[m],
                                 line=dict(color=COLORS[m], width=2,
                                           dash="dash" if m == "ssvi_free" else "solid")))
    fig.update_layout(xaxis_title="log-moneyness k", yaxis_title="g(k)", height=360,
                      hovermode="x unified", margin=dict(l=10, r=10, t=30, b=10),
                      title="g(k) (below zero = butterfly arbitrage)")
    return fig
