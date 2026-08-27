"""
Genera dashboard.html a partir de la base SQLite -- corre local, sin internet.
Recalcula las mismas métricas que las queries de sql/ y arma el dashboard
interactivo completo (self-contained: HTML + CSS + JS + datos, sin
dependencias externas, para poder abrirlo local o servirlo con GitHub Pages).

    python build_dashboard.py
"""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "processed" / "cs2_sa.db"
OUT_PATH = Path(__file__).parent / "dashboard.html"


def build_data(cur):
    data = {}

    data["dominancia_por_pais"] = [
        {"country": r[0].upper(), "n": r[1], "pct": r[2]}
        for r in cur.execute("""
            SELECT country, COUNT(*) as n,
                   ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM players WHERE is_sa_country=1),1) as pct
            FROM players WHERE is_sa_country = 1
            GROUP BY country ORDER BY n DESC
        """).fetchall()
    ]

    data["mapas"] = [
        {"map": r[0].replace("de_", ""), "partidas": r[1], "rondas_promedio": r[2],
         "diferencia_rondas": r[3], "clasificacion": r[4]}
        for r in cur.execute("""
            SELECT map, COUNT(*), ROUND(AVG(rounds_total), 1), ROUND(AVG(round_diff), 2),
                CASE WHEN AVG(round_diff) <= 5 THEN 'Parejo' WHEN AVG(round_diff) <= 8 THEN 'Normal' ELSE 'Desbalanceado' END
            FROM match_maps WHERE round_diff IS NOT NULL
            GROUP BY map HAVING COUNT(*) >= 20
            ORDER BY 4 ASC
        """).fetchall()
    ]

    data["hs_vs_winrate"] = [
        {"rango": r[0], "winrate": r[1]}
        for r in cur.execute("""
            SELECT CASE WHEN headshots_percent < 30 THEN '< 30%' WHEN headshots_percent < 45 THEN '30-45%'
                WHEN headshots_percent < 60 THEN '45-60%' ELSE '60%+' END AS rango_hs,
                ROUND(100.0 * SUM(team_won) / COUNT(*), 1)
            FROM match_player_stats WHERE headshots_percent IS NOT NULL
            GROUP BY rango_hs ORDER BY MIN(headshots_percent)
        """).fetchall()
    ]

    data["kd_vs_winrate"] = [
        {"rango": r[0], "winrate": r[1]}
        for r in cur.execute("""
            SELECT CASE WHEN deaths = 0 THEN '2.0+' WHEN kills*1.0/deaths < 0.8 THEN '< 0.8'
                WHEN kills*1.0/deaths < 1.0 THEN '0.8-1.0' WHEN kills*1.0/deaths < 1.3 THEN '1.0-1.3' ELSE '1.3+' END AS rango_kd,
                ROUND(100.0 * SUM(team_won) / COUNT(*), 1)
            FROM match_player_stats GROUP BY rango_kd ORDER BY MIN(kills*1.0/NULLIF(deaths,0))
        """).fetchall()
    ]

    data["jugadores_revelacion"] = [
        {"nickname": r[0], "country": r[1].upper(), "elo": r[2], "mapas_jugados": r[3], "kd_real": r[4],
         "winrate_real": r[5], "percentil_elo": r[6], "percentil_kd": r[7], "diferencia": r[8]}
        for r in cur.execute("""
            WITH rendimiento_real AS (
                SELECT player_id, COUNT(*) AS mapas_jugados,
                    ROUND(AVG(kills * 1.0 / NULLIF(deaths, 0)), 2) AS kd_real,
                    ROUND(100.0 * SUM(team_won) / COUNT(*), 1) AS winrate_real
                FROM match_player_stats GROUP BY player_id HAVING COUNT(*) >= 5
            ),
            comparacion AS (
                SELECT p.nickname, p.country, p.faceit_elo, r.mapas_jugados, r.kd_real, r.winrate_real,
                    PERCENT_RANK() OVER (ORDER BY p.faceit_elo) AS percentil_elo,
                    PERCENT_RANK() OVER (ORDER BY r.kd_real) AS percentil_kd_real
                FROM players p JOIN rendimiento_real r ON p.player_id = r.player_id
                WHERE p.is_sa_country = 1
            )
            SELECT nickname, country, faceit_elo, mapas_jugados, kd_real, winrate_real,
                ROUND(percentil_elo * 100, 0), ROUND(percentil_kd_real * 100, 0),
                ROUND((percentil_kd_real - percentil_elo) * 100, 0) AS diferencia_sobre_lo_esperado
            FROM comparacion ORDER BY diferencia_sobre_lo_esperado DESC LIMIT 10
        """).fetchall()
    ]

    data["rachas"] = [
        {"nickname": r[0], "racha": r[1], "largo": r[2]}
        for r in cur.execute("""
            WITH partidas_ordenadas AS (
                SELECT mps.player_id, p.nickname, mps.match_id, m.finished_at, mps.team_won,
                    CASE WHEN mps.team_won != LAG(mps.team_won) OVER (PARTITION BY mps.player_id ORDER BY m.finished_at)
                        OR LAG(mps.team_won) OVER (PARTITION BY mps.player_id ORDER BY m.finished_at) IS NULL
                        THEN 1 ELSE 0 END AS empieza_racha_nueva
                FROM match_player_stats mps JOIN matches m ON mps.match_id = m.match_id
                JOIN players p ON mps.player_id = p.player_id WHERE p.is_sa_country = 1
            ),
            con_grupo AS (
                SELECT *, SUM(empieza_racha_nueva) OVER (PARTITION BY player_id ORDER BY finished_at) AS grupo_racha
                FROM partidas_ordenadas
            ),
            rachas AS (
                SELECT player_id, nickname, grupo_racha, team_won, COUNT(*) AS largo_racha, MAX(finished_at) AS fin
                FROM con_grupo GROUP BY player_id, grupo_racha, team_won
            )
            SELECT nickname, CASE WHEN team_won=1 THEN 'Ganando' ELSE 'Perdiendo' END, largo_racha
            FROM rachas r WHERE fin = (SELECT MAX(fin) FROM rachas r2 WHERE r2.player_id = r.player_id)
            ORDER BY (CASE WHEN team_won=1 THEN largo_racha ELSE 0 END) DESC LIMIT 10
        """).fetchall()
    ]

    data["desgaste"] = [
        {"bucket": r[0], "kd": r[1], "hs": r[2], "n": r[3]}
        for r in cur.execute("""
            SELECT CASE WHEN m.duration_minutes <= 30 THEN '<= 30 min' WHEN m.duration_minutes <= 45 THEN '30-45 min'
                WHEN m.duration_minutes <= 60 THEN '45-60 min' ELSE '60+ min' END AS bucket,
                ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2),
                ROUND(AVG(mps.headshots_percent), 1),
                COUNT(*)
            FROM match_player_stats mps JOIN matches m ON mps.match_id = m.match_id
            WHERE m.has_valid_duration = 1 GROUP BY bucket ORDER BY MIN(m.duration_minutes)
        """).fetchall()
    ]

    data["resumen"] = {
        "total_jugadores": cur.execute("SELECT COUNT(*) FROM players").fetchone()[0],
        "jugadores_sa": cur.execute("SELECT COUNT(*) FROM players WHERE is_sa_country=1").fetchone()[0],
        "total_partidas": cur.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
        "total_mapas": cur.execute("SELECT COUNT(*) FROM match_maps").fetchone()[0],
        "filas_stats": cur.execute("SELECT COUNT(*) FROM match_player_stats").fetchone()[0],
    }

    return data


TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CS2 Sudamérica — Dashboard interactivo</title>
<style>
  :root {
    color-scheme: light;
    --surface: #fcfcfb;
    --page: #f9f9f7;
    --ink-primary: #0b0b0b;
    --ink-secondary: #52514e;
    --ink-muted: #898781;
    --grid: #e1e0d9;
    --baseline: #c3c2b7;
    --border: rgba(11,11,11,0.10);
    --blue: #2a78d6;
    --orange: #eb6834;
    --seq-1: #86b6ef;
    --seq-2: #5598e7;
    --seq-3: #2a78d6;
    --seq-4: #184f95;
    --seq5-1: #86b6ef;
    --seq5-2: #5598e7;
    --seq5-3: #2a78d6;
    --seq5-4: #1c5cab;
    --seq5-5: #104281;
    --good: #0ca30c;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      color-scheme: dark;
      --surface: #1a1a19;
      --page: #0d0d0d;
      --ink-primary: #ffffff;
      --ink-secondary: #c3c2b7;
      --ink-muted: #898781;
      --grid: #2c2c2a;
      --baseline: #383835;
      --border: rgba(255,255,255,0.10);
      --blue: #3987e5;
      --orange: #d95926;
      --seq-1: #6da7ec;
      --seq-2: #3987e5;
      --seq-3: #256abf;
      --seq-4: #104281;
      --seq5-1: #6da7ec;
      --seq5-2: #3987e5;
      --seq5-3: #256abf;
      --seq5-4: #184f95;
      --seq5-5: #0d366b;
      --good: #0ca30c;
    }
  }

  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--page);
    color: var(--ink-primary);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.5;
  }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 32px 20px 80px; }

  header.hero { padding: 28px 0 20px; border-bottom: 1px solid var(--border); }
  header.hero h1 { font-size: 1.6rem; margin: 0 0 8px; }
  header.hero p { color: var(--ink-secondary); margin: 0 0 20px; max-width: 680px; font-size: 0.98rem; }
  header.hero .backlink { font-size: 0.85rem; }
  header.hero .backlink a { color: var(--blue); text-decoration: none; }
  header.hero .backlink a:hover { text-decoration: underline; }

  .stat-tiles { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }
  .stat-tile {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 18px; min-width: 130px;
  }
  .stat-tile .num { font-size: 1.5rem; font-weight: 700; }
  .stat-tile .label { font-size: 0.78rem; color: var(--ink-muted); margin-top: 2px; }

  section.card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 22px 24px 20px; margin-top: 22px;
  }
  section.card h2 { font-size: 1.05rem; margin: 0 0 4px; }
  section.card .sub { color: var(--ink-secondary); font-size: 0.88rem; margin: 0 0 16px; }
  section.card .finding { color: var(--ink-secondary); font-size: 0.88rem; margin-top: 14px; line-height: 1.55; }
  section.card .finding strong { color: var(--ink-primary); }

  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
  @media (max-width: 720px) { .grid-2 { grid-template-columns: 1fr; } }

  .chart-wrap { position: relative; }
  svg text { fill: var(--ink-secondary); font-family: inherit; }
  svg .value-label { fill: var(--ink-primary); font-weight: 600; }
  svg .axis-label { fill: var(--ink-muted); font-size: 10.5px; }
  svg .baseline { stroke: var(--baseline); stroke-width: 1; }
  svg .ref-line { stroke: var(--baseline); stroke-width: 1; stroke-dasharray: 3 3; }
  .bar { cursor: pointer; transition: opacity 0.12s; }
  .bar:hover { opacity: 0.82; }

  .tooltip {
    position: absolute; pointer-events: none; background: var(--ink-primary); color: var(--surface);
    font-size: 0.78rem; padding: 6px 10px; border-radius: 6px; white-space: nowrap;
    transform: translate(-50%, -100%); opacity: 0; transition: opacity 0.1s; z-index: 10;
    top: 0; left: 0;
  }
  .tooltip.show { opacity: 0.96; }

  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 4px; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); }
  th { color: var(--ink-muted); font-weight: 600; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.02em; cursor: pointer; user-select: none; }
  th:hover { color: var(--ink-primary); }
  th.sorted::after { content: " \25BE"; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr:hover td { background: color-mix(in srgb, var(--blue) 6%, transparent); }
  .country-tag { color: var(--ink-muted); font-size: 0.78rem; }

  .badge {
    display: inline-block; font-size: 0.72rem; padding: 2px 8px; border-radius: 999px;
    background: color-mix(in srgb, var(--good) 15%, transparent); color: var(--good); font-weight: 600;
    margin-left: 8px;
  }

  .legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 0.78rem; color: var(--ink-secondary); margin-top: 10px; }
  .legend .swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }

  footer { margin-top: 36px; padding-top: 20px; border-top: 1px solid var(--border); color: var(--ink-muted); font-size: 0.82rem; }
  footer a { color: var(--blue); text-decoration: none; }
  footer a:hover { text-decoration: underline; }
</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <h1>CS2 Sudamérica — Dashboard interactivo</h1>
    <p>Los mismos hallazgos del README, pero navegables: pasá el mouse sobre las barras para ver el detalle exacto y ordená la tabla de jugadores por la columna que quieras. Datos extraídos directo de la <a href="https://docs.faceit.com/docs/data-api/" style="color:var(--blue)">API de FACEIT</a>, sin datasets prearmados.</p>
    <div class="stat-tiles" id="stat-tiles"></div>
    <div class="backlink" style="margin-top:16px;"><a href="./README.md">&larr; Volver al README</a></div>
  </header>

  <section class="card">
    <h2>1. Brasil concentra la mayoría de los jugadores top de la región</h2>
    <p class="sub">Jugadores sudamericanos en el top 1000 del ranking FACEIT (región SA), por país</p>
    <div class="chart-wrap" id="chart-paises"></div>
  </section>

  <section class="card">
    <h2>2. ¿El aim solo alcanza para ganar?</h2>
    <p class="sub">Win rate real según el rango de headshot % y de K/D del jugador en la partida — la línea punteada marca el 50%, lo esperado si el resultado fuera puro azar</p>
    <div class="grid-2">
      <div>
        <div class="chart-wrap" id="chart-hs"></div>
      </div>
      <div>
        <div class="chart-wrap" id="chart-kd"></div>
      </div>
    </div>
    <p class="finding">Los cuatro grupos de headshot % ganan casi lo mismo — <strong>el aim solo no explica las victorias</strong>. El K/D sí importa, y bastante: por debajo de 0.8 la win rate se hunde a 22%, arriba de 1.3 sube a 85%. No es la precisión, es la eficiencia neta de kills contra muertes.</p>
  </section>

  <section class="card">
    <h2>3. El desgaste por partidas largas es real</h2>
    <p class="sub">Rendimiento promedio según la duración real de la partida (excluye partidas de torneo sin duración registrada)</p>
    <div class="grid-2">
      <div>
        <div class="chart-wrap" id="chart-desgaste-kd"></div>
      </div>
      <div>
        <div class="chart-wrap" id="chart-desgaste-hs"></div>
      </div>
    </div>
    <p class="finding">El K/D promedio cae de <strong>1.19 a 1.01</strong> y el headshot % de <strong>55.7% a 49.2%</strong> entre partidas cortas (≤30 min) y largas (60+ min). La caída es consistente en ambas métricas — hay desgaste real, no es ruido.</p>
  </section>

  <section class="card">
    <h2>4. ¿Qué mapa es más parejo?</h2>
    <p class="sub">Diferencia de rondas promedio entre ganador y perdedor, por mapa (mínimo 20 partidas jugadas)</p>
    <div class="chart-wrap" id="chart-mapas"></div>
  </section>

  <section class="card">
    <h2>5. Rachas activas</h2>
    <p class="sub">Los jugadores con más partidas ganadas seguidas ahora mismo, calculado con LAG() y "gaps and islands"</p>
    <div class="chart-wrap" id="chart-rachas"></div>
  </section>

  <section class="card">
    <h2>6. Jugadores "revelación"</h2>
    <p class="sub">ELO relativamente bajo para su nivel, pero rendimiento real muy por encima de lo esperado (clic en una columna para ordenar)</p>
    <div id="table-revelacion"></div>
    <p class="finding">Apareció <strong>coldzera</strong> — el histórico jugador profesional brasileño — con un K/D real de 1.95 y 100% de percentil de rendimiento en la muestra, pese a no tener el ELO más alto del grupo.</p>
  </section>

  <footer>
    Parte del proyecto <a href="https://github.com/cervetade/cs2-sudamerica-analytics">cs2-sudamerica-analytics</a> — datos propios extraídos de la API de FACEIT, procesados con Python + SQLite + SQL. Ver el <a href="./README.md">README</a> para la historia completa y el <a href="./sql/">SQL</a> de cada hallazgo.
  </footer>

</div>

<div class="tooltip" id="tooltip"></div>

<script>
const DATA = __DATA_JSON__;

const tooltip = document.getElementById("tooltip");
function showTooltip(evt, html) {
  tooltip.innerHTML = html;
  tooltip.classList.add("show");
  moveTooltip(evt);
}
function moveTooltip(evt) {
  const wrap = evt.currentTarget.closest(".chart-wrap");
  const rect = wrap.getBoundingClientRect();
  tooltip.style.left = (evt.clientX - rect.left + wrap.offsetLeft + wrap.getBoundingClientRect().left - rect.left) + "px";
  // position relative to viewport using fixed-like math via wrap container
  const x = evt.clientX - rect.left;
  const y = evt.clientY - rect.top;
  tooltip.style.left = (wrap.offsetLeft + x) + "px";
  tooltip.style.top = (wrap.offsetTop + y - 10) + "px";
}
function hideTooltip() {
  tooltip.classList.remove("show");
}

const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}

/**
 * Generic vertical bar chart with direct labels + hover tooltip.
 * items: [{label, value, color, tip}]
 */
function verticalBars(containerId, items, opts) {
  opts = opts || {};
  const container = document.getElementById(containerId);
  const width = container.clientWidth || 480;
  const height = opts.height || 260;
  const padTop = 16, padBottom = 34, padSide = 10;
  const maxVal = opts.max || Math.max(...items.map(d => d.value)) * 1.2;
  const n = items.length;
  const gap = 0.38;
  const bw = (width - padSide * 2) / n;

  const svg = el("svg", { width: "100%", height: height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "" });

  if (opts.refLine !== undefined) {
    const y = height - padBottom - (opts.refLine / maxVal) * (height - padTop - padBottom);
    svg.appendChild(el("line", { x1: padSide, x2: width - padSide, y1: y, y2: y, class: "ref-line" }));
  }

  items.forEach((d, i) => {
    const x = padSide + i * bw + bw * gap / 2;
    const barW = bw * (1 - gap);
    const barH = Math.max(2, (d.value / maxVal) * (height - padTop - padBottom));
    const y = height - padBottom - barH;

    const rect = el("rect", { x, y, width: barW, height: barH, rx: 3, fill: d.color || "var(--blue)", class: "bar" });
    rect.addEventListener("mouseenter", (e) => showTooltip(e, d.tip || `<b>${d.label}</b>: ${d.value}`));
    rect.addEventListener("mousemove", moveTooltip);
    rect.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(rect);

    const vlabel = el("text", { x: x + barW / 2, y: y - 6, "text-anchor": "middle", class: "value-label", "font-size": "12" });
    vlabel.textContent = d.valueLabel !== undefined ? d.valueLabel : d.value;
    svg.appendChild(vlabel);

    const llabel = el("text", { x: x + barW / 2, y: height - padBottom + 16, "text-anchor": "middle", class: "axis-label" });
    llabel.textContent = d.label;
    svg.appendChild(llabel);
  });

  svg.appendChild(el("line", { x1: padSide, x2: width - padSide, y1: height - padBottom, y2: height - padBottom, class: "baseline" }));
  container.innerHTML = "";
  container.appendChild(svg);
}

/**
 * Generic horizontal bar chart, sorted top to bottom as given.
 */
function horizontalBars(containerId, items, opts) {
  opts = opts || {};
  const container = document.getElementById(containerId);
  const width = container.clientWidth || 480;
  const rowH = opts.rowH || 30;
  const padLeft = opts.padLeft || 92;
  const padRight = 56;
  const height = items.length * rowH + 10;
  const maxVal = opts.max || Math.max(...items.map(d => d.value)) * 1.12;

  const svg = el("svg", { width: "100%", height: height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "" });

  items.forEach((d, i) => {
    const y = i * rowH + 6;
    const barH = rowH - 12;
    const barW = Math.max(2, (d.value / maxVal) * (width - padLeft - padRight));

    const label = el("text", { x: padLeft - 8, y: y + barH / 2 + 4, "text-anchor": "end", "font-size": "12" });
    label.textContent = d.label;
    svg.appendChild(label);

    const rect = el("rect", { x: padLeft, y, width: barW, height: barH, rx: 3, fill: d.color || "var(--blue)", class: "bar" });
    rect.addEventListener("mouseenter", (e) => showTooltip(e, d.tip || `<b>${d.label}</b>: ${d.value}`));
    rect.addEventListener("mousemove", moveTooltip);
    rect.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(rect);

    const vlabel = el("text", { x: padLeft + barW + 8, y: y + barH / 2 + 4, class: "value-label", "font-size": "12" });
    vlabel.textContent = d.valueLabel !== undefined ? d.valueLabel : d.value;
    svg.appendChild(vlabel);
  });

  container.innerHTML = "";
  container.appendChild(svg);
}

// --- Stat tiles ---
(function () {
  const r = DATA.resumen;
  const tiles = [
    { num: r.jugadores_sa.toLocaleString("es-AR"), label: "Jugadores SA en el top 1000" },
    { num: r.total_partidas.toLocaleString("es-AR"), label: "Partidas analizadas" },
    { num: r.total_mapas.toLocaleString("es-AR"), label: "Mapas jugados" },
    { num: r.filas_stats.toLocaleString("es-AR"), label: "Filas de stats jugador/mapa" },
  ];
  const box = document.getElementById("stat-tiles");
  tiles.forEach(t => {
    const div = document.createElement("div");
    div.className = "stat-tile";
    div.innerHTML = `<div class="num">${t.num}</div><div class="label">${t.label}</div>`;
    box.appendChild(div);
  });
})();

// --- 1. Dominancia por pais ---
verticalBars("chart-paises", DATA.dominancia_por_pais.map(d => ({
  label: d.country, value: d.n, valueLabel: `${d.n}`, color: "var(--blue)",
  tip: `<b>${d.country}</b>: ${d.n} jugadores (${d.pct}%)`
})), { ariaLabel: "Jugadores por país" });

// --- 2. HS% vs winrate (secuencial, 4 pasos) ---
const seqColors = ["var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)"];
verticalBars("chart-hs", DATA.hs_vs_winrate.map((d, i) => ({
  label: d.rango, value: d.winrate, valueLabel: `${d.winrate}%`, color: seqColors[i],
  tip: `<b>HS% ${d.rango}</b>: ${d.winrate}% win rate`
})), { max: 58, refLine: 50, refLineLabel: "50% (azar)", ariaLabel: "Win rate por rango de headshot %" });

// --- 2b. K/D vs winrate (secuencial, 5 pasos) ---
const seq5Colors = ["var(--seq5-1)", "var(--seq5-2)", "var(--seq5-3)", "var(--seq5-4)", "var(--seq5-5)"];
const kdOrder = ["< 0.8", "0.8-1.0", "1.0-1.3", "1.3+", "2.0+"];
const kdSorted = kdOrder.map(r => DATA.kd_vs_winrate.find(d => d.rango === r)).filter(Boolean);
verticalBars("chart-kd", kdSorted.map((d, i) => ({
  label: d.rango, value: d.winrate, valueLabel: `${d.winrate}%`, color: seq5Colors[i],
  tip: `<b>K/D ${d.rango}</b>: ${d.winrate}% win rate`
})), { max: 95, refLine: 50, refLineLabel: "50% (azar)", ariaLabel: "Win rate por rango de K/D" });

// --- 3. Desgaste ---
verticalBars("chart-desgaste-kd", DATA.desgaste.map(d => ({
  label: d.bucket, value: d.kd, valueLabel: d.kd, color: "var(--blue)",
  tip: `<b>${d.bucket}</b>: K/D promedio ${d.kd} (n=${d.n.toLocaleString("es-AR")})`
})), { ariaLabel: "K/D promedio por duración de partida" });
verticalBars("chart-desgaste-hs", DATA.desgaste.map(d => ({
  label: d.bucket, value: d.hs, valueLabel: `${d.hs}%`, color: "var(--orange)",
  tip: `<b>${d.bucket}</b>: HS% promedio ${d.hs}% (n=${d.n.toLocaleString("es-AR")})`
})), { ariaLabel: "Headshot % promedio por duración de partida" });

// --- 4. Mapas ---
const mapasSorted = [...DATA.mapas].sort((a, b) => a.diferencia_rondas - b.diferencia_rondas);
horizontalBars("chart-mapas", mapasSorted.map((d, i) => ({
  label: `de_${d.map}` + (i === 0 ? "  ★" : ""), value: d.diferencia_rondas, valueLabel: d.diferencia_rondas,
  color: "var(--blue)",
  tip: `<b>de_${d.map}</b>: diferencia de ${d.diferencia_rondas} rondas en promedio (${d.partidas} partidas, ${d.clasificacion})`
})), { max: Math.max(...mapasSorted.map(d => d.diferencia_rondas)) * 1.15, ariaLabel: "Diferencia de rondas por mapa" });

// --- 5. Rachas ---
horizontalBars("chart-rachas", DATA.rachas.map(d => ({
  label: d.nickname, value: d.largo, valueLabel: `${d.largo}`, color: "var(--blue)",
  tip: `<b>${d.nickname}</b>: racha de ${d.largo} partidas ganadas seguidas`
})), { ariaLabel: "Racha ganadora activa por jugador" });

// --- 6. Tabla jugadores revelacion (sortable) ---
(function () {
  const cols = [
    { key: "nickname", label: "Nick" },
    { key: "country", label: "País" },
    { key: "elo", label: "ELO", num: true },
    { key: "mapas_jugados", label: "Mapas", num: true },
    { key: "kd_real", label: "K/D real", num: true },
    { key: "winrate_real", label: "Win %", num: true, fmt: v => v + "%" },
    { key: "diferencia", label: "Sobre lo esperado", num: true, fmt: v => (v > 0 ? "+" : "") + v + " pts" },
  ];
  let rows = [...DATA.jugadores_revelacion];
  let sortKey = "diferencia", sortDir = -1;

  function render() {
    rows.sort((a, b) => (a[sortKey] - b[sortKey]) * sortDir || 0);
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const trh = document.createElement("tr");
    cols.forEach(c => {
      const th = document.createElement("th");
      th.textContent = c.label;
      if (c.num) th.classList.add("num");
      if (c.key === sortKey) th.classList.add("sorted");
      th.addEventListener("click", () => {
        if (sortKey === c.key) sortDir *= -1; else { sortKey = c.key; sortDir = -1; }
        render();
      });
      trh.appendChild(th);
    });
    thead.appendChild(trh);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    rows.forEach(r => {
      const tr = document.createElement("tr");
      cols.forEach(c => {
        const td = document.createElement("td");
        if (c.num) td.classList.add("num");
        let v = r[c.key];
        if (c.key === "nickname") { tr.style.fontWeight = "600"; }
        td.textContent = c.fmt ? c.fmt(v) : v;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    const box = document.getElementById("table-revelacion");
    box.innerHTML = "";
    box.appendChild(table);
  }
  render();
})();

window.addEventListener("resize", () => {
  // simple debounce-free re-render on resize for responsiveness
  clearTimeout(window.__rz);
  window.__rz = setTimeout(() => location.reload(), 300);
});
</script>
</body>
</html>
"""


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    data = build_data(cur)
    conn.close()

    json_str = json.dumps(data, ensure_ascii=False).replace("</script>", "<\\/script>")
    html = TEMPLATE.replace("__DATA_JSON__", json_str)

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Listo: {OUT_PATH}")


if __name__ == "__main__":
    main()
