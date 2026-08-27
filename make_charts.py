"""
Genera los graficos de apoyo para el README a partir de la base SQLite.
Corre local, sin internet.

    python make_charts.py

Paleta y reglas de forma: skill de dataviz (un solo hue por serie, sin
doble eje, small multiples en vez de eje dual, etiquetas directas).
"""

import sqlite3
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

DB_PATH = Path(__file__).parent / "data" / "processed" / "cs2_sa.db"
OUT_DIR = Path(__file__).parent / "charts"
OUT_DIR.mkdir(exist_ok=True)

# --- paleta (dataviz skill, modo claro) ---
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
# rampa secuencial (mismo hue, mas oscuro = mas alto) para el bucket de HS%
SEQ_STEPS = ["#86b6ef", "#5598e7", "#2a78d6", "#184f95"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "text.color": INK_PRIMARY,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


def clean_axes(ax, hide_y=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(not hide_y)
    if hide_y:
        ax.get_yaxis().set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(axis="both", length=0)


def chart_dominancia_por_pais(cur):
    rows = cur.execute("""
        SELECT country, COUNT(*) as n,
               ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM players WHERE is_sa_country=1),1) as pct
        FROM players WHERE is_sa_country = 1
        GROUP BY country ORDER BY n DESC
    """).fetchall()

    countries = [r[0].upper() for r in rows]
    counts = [r[1] for r in rows]
    pcts = [r[2] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    bars = ax.bar(countries, counts, color=BLUE, width=0.62)
    clean_axes(ax)

    for bar, n, pct in zip(bars, counts, pcts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(counts) * 0.015,
                 f"{n}\n({pct}%)", ha="center", va="bottom", fontsize=8.5, color=INK_SECONDARY)

    ax.set_ylim(0, max(counts) * 1.18)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.suptitle("¿Quién domina el CS2 competitivo de Sudamérica?",
                 fontsize=13, fontweight="bold", color=INK_PRIMARY, x=0.01, ha="left", y=0.98)
    fig.text(0.01, 0.90, "Jugadores sudamericanos en el top 1000 del ranking FACEIT (región SA), por país",
              fontsize=9.5, color=INK_SECONDARY)
    fig.savefig(OUT_DIR / "01_dominancia_por_pais.png", bbox_inches="tight")
    plt.close(fig)


def chart_hs_vs_winrate(cur):
    rows = cur.execute("""
        SELECT
            CASE
                WHEN headshots_percent < 30 THEN '< 30%'
                WHEN headshots_percent < 45 THEN '30-45%'
                WHEN headshots_percent < 60 THEN '45-60%'
                ELSE '60%+'
            END AS rango_hs,
            ROUND(100.0 * SUM(team_won) / COUNT(*), 1) AS win_rate,
            MIN(headshots_percent) as minhs
        FROM match_player_stats
        WHERE headshots_percent IS NOT NULL
        GROUP BY rango_hs
        ORDER BY minhs
    """).fetchall()

    labels = [r[0] for r in rows]
    winrates = [r[1] for r in rows]

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=150)
    bars = ax.bar(labels, winrates, color=SEQ_STEPS, width=0.55)
    clean_axes(ax)

    ax.axhline(50, color=BASELINE, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(len(labels) - 0.35, 50.3, "50% (azar)", fontsize=8, color=INK_MUTED, ha="right")

    for bar, wr in zip(bars, winrates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.6,
                 f"{wr}%", ha="center", va="bottom", fontsize=9.5,
                 color=INK_PRIMARY, fontweight="bold")

    ax.set_ylim(40, 58)
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    fig.suptitle("Más headshots no es sinónimo de más victorias",
                 fontsize=13, fontweight="bold", color=INK_PRIMARY, x=0.01, ha="left", y=0.98)
    fig.text(0.01, 0.89, "Win rate real según el % de headshots del jugador en la partida",
              fontsize=9.5, color=INK_SECONDARY)
    fig.savefig(OUT_DIR / "02_headshots_vs_winrate.png", bbox_inches="tight")
    plt.close(fig)


def chart_desgaste(cur):
    rows = cur.execute("""
        SELECT
            CASE
                WHEN m.duration_minutes <= 30 THEN '<= 30 min'
                WHEN m.duration_minutes <= 45 THEN '30-45 min'
                WHEN m.duration_minutes <= 60 THEN '45-60 min'
                ELSE '60+ min'
            END AS bucket,
            ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2) AS kd,
            ROUND(AVG(mps.headshots_percent), 1) AS hs,
            MIN(m.duration_minutes) as mind
        FROM match_player_stats mps
        JOIN matches m ON mps.match_id = m.match_id
        WHERE m.has_valid_duration = 1
        GROUP BY bucket
        ORDER BY mind
    """).fetchall()

    labels = [r[0] for r in rows]
    kds = [r[1] for r in rows]
    hss = [r[2] for r in rows]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.5), dpi=150)

    bars1 = ax1.bar(labels, kds, color=BLUE, width=0.55)
    clean_axes(ax1)
    for bar, v in zip(bars1, kds):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                  f"{v}", ha="center", va="bottom", fontsize=9.5, color=INK_PRIMARY, fontweight="bold")
    ax1.set_ylim(0, max(kds) * 1.25)
    ax1.set_title("K/D promedio", fontsize=10.5, color=INK_SECONDARY, loc="left")
    ax1.tick_params(axis="x", labelsize=8.5, rotation=15)

    bars2 = ax2.bar(labels, hss, color="#eb6834", width=0.55)
    clean_axes(ax2)
    for bar, v in zip(bars2, hss):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.6,
                  f"{v}%", ha="center", va="bottom", fontsize=9.5, color=INK_PRIMARY, fontweight="bold")
    ax2.set_ylim(0, max(hss) * 1.25)
    ax2.set_title("Headshot % promedio", fontsize=10.5, color=INK_SECONDARY, loc="left")
    ax2.tick_params(axis="x", labelsize=8.5, rotation=15)

    fig.suptitle("El desgaste es real: a mayor duración de la partida, peor rendimiento",
                 fontsize=13, fontweight="bold", color=INK_PRIMARY, x=0.01, ha="left", y=1.04)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "03_desgaste_por_duracion.png", bbox_inches="tight")
    plt.close(fig)


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    print("Generando graficos...")
    chart_dominancia_por_pais(cur)
    print("  01_dominancia_por_pais.png")
    chart_hs_vs_winrate(cur)
    print("  02_headshots_vs_winrate.png")
    chart_desgaste(cur)
    print("  03_desgaste_por_duracion.png")
    conn.close()
    print(f"\nListo, guardados en {OUT_DIR}/")


if __name__ == "__main__":
    main()
