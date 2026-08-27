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
INDEX_PATH = Path(__file__).parent / "index.html"


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
<title>CS2 Sudamérica — Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    color-scheme: light;
    --surface: #ffffff;
    --page: #f7f7f5;
    --sidebar: #ffffff;
    --ink-primary: #14161a;
    --ink-secondary: #5c6068;
    --ink-muted: #8b8f97;
    --grid: #ebebe8;
    --baseline: #d4d4d0;
    --border: #e4e4e1;
    --blue: #2a78d6;
    --blue-wash: #eaf2fc;
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
      --surface: #1c1d1f;
      --page: #131415;
      --sidebar: #18191b;
      --ink-primary: #f4f4f3;
      --ink-secondary: #b7b8bb;
      --ink-muted: #85868b;
      --grid: #2a2b2d;
      --baseline: #38393c;
      --border: #2a2b2d;
      --blue: #4c94ec;
      --blue-wash: #1c2c40;
      --orange: #e0743c;
      --seq-1: #6da7ec;
      --seq-2: #3987e5;
      --seq-3: #256abf;
      --seq-4: #104281;
      --seq5-1: #6da7ec;
      --seq5-2: #3987e5;
      --seq5-3: #256abf;
      --seq5-4: #184f95;
      --seq5-5: #0d366b;
      --good: #1ec01e;
    }
  }

  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--page);
    color: var(--ink-primary);
    font-family: 'Geist', -apple-system, "Segoe UI", system-ui, sans-serif;
    line-height: 1.5;
    font-size: 14px;
  }
  a { color: var(--blue); }
  .mono, .stat .num, .value-label, .axis-label, td.num, th.num, .nav-item .n, section.panel .tag {
    font-family: 'Geist Mono', ui-monospace, "SFMono-Regular", Menlo, monospace;
  }

  /* ---------- layout shell ---------- */
  .shell { display: flex; min-height: 100vh; }

  .sidebar {
    width: 240px; flex-shrink: 0; background: var(--sidebar);
    border-right: 1px solid var(--border);
    position: fixed; top: 0; left: 0; bottom: 0; overflow-y: auto;
    padding: 18px 12px 16px; z-index: 20;
    transition: transform 0.2s ease;
  }
  .sidebar .brand {
    display: flex; align-items: center; gap: 9px; padding: 4px 8px 16px;
  }
  .sidebar .brand .mark {
    width: 26px; height: 26px; border-radius: 7px; background: var(--blue);
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 12.5px; flex-shrink: 0;
  }
  .sidebar .brand .name { font-weight: 700; font-size: 13.5px; line-height: 1.25; }
  .sidebar .brand .name span { display: block; font-weight: 500; color: var(--ink-muted); font-size: 11px; }

  .nav-label {
    font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--ink-muted); padding: 14px 10px 6px;
  }
  nav.nav-list { display: flex; flex-direction: column; gap: 1px; }
  .nav-item {
    display: flex; align-items: center; gap: 9px; padding: 7px 10px; border-radius: 7px;
    color: var(--ink-secondary); text-decoration: none; font-size: 13px; font-weight: 500;
    cursor: pointer; border: none; background: none; width: 100%; text-align: left;
  }
  .nav-item:hover { background: var(--page); color: var(--ink-primary); }
  .nav-item.active { background: var(--blue-wash); color: var(--blue); }
  .nav-item svg { flex-shrink: 0; opacity: 0.85; }
  .nav-item .n { margin-left: auto; font-size: 10.5px; color: var(--ink-muted); background: var(--page); border-radius: 999px; padding: 1px 6px; }
  .nav-item.active .n { color: var(--blue); background: #fff; }

  .sidebar hr { border: none; border-top: 1px solid var(--border); margin: 12px 4px; }

  .sidebar .foot { padding: 14px 10px 4px; font-size: 11.5px; color: var(--ink-muted); }
  .sidebar .foot a { color: var(--ink-secondary); text-decoration: none; }
  .sidebar .foot a:hover { color: var(--blue); }

  .sidebar-toggle {
    display: none; position: fixed; top: 14px; left: 14px; z-index: 30;
    width: 36px; height: 36px; border-radius: 8px; border: 1px solid var(--border);
    background: var(--surface); color: var(--ink-primary); align-items: center; justify-content: center; cursor: pointer;
  }
  .sidebar-backdrop {
    display: none; position: fixed; inset: 0; background: rgba(15,16,18,0.4); z-index: 19;
  }

  main { flex: 1; margin-left: 240px; min-width: 0; }

  .topbar {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 20px 32px; border-bottom: 1px solid var(--border); background: var(--surface);
    position: sticky; top: 0; z-index: 10; flex-wrap: wrap;
  }
  .topbar h1 { font-size: 1.15rem; margin: 0 0 2px; }
  .topbar p { margin: 0; color: var(--ink-secondary); font-size: 12.5px; max-width: 560px; }
  .btn-primary {
    display: inline-flex; align-items: center; gap: 6px; background: var(--blue); color: #fff;
    padding: 8px 16px; border-radius: 7px; font-size: 12.5px; font-weight: 600; text-decoration: none;
    white-space: nowrap;
  }
  .btn-primary:hover { opacity: 0.92; }

  .content { max-width: 980px; padding: 24px 32px 100px; }

  .stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 24px; }
  @media (max-width: 720px) { .stat-row { grid-template-columns: repeat(2, 1fr); } }
  .stat {
    background: var(--surface); border: 1px solid var(--border); border-radius: 9px;
    padding: 13px 15px;
  }
  .stat .num { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.01em; }
  .stat .label { font-size: 11.5px; color: var(--ink-muted); margin-top: 1px; }

  section.panel {
    background: var(--surface); border: 1px solid var(--border); border-radius: 9px;
    padding: 20px 22px 18px; margin-bottom: 18px; scroll-margin-top: 84px;
  }
  section.panel .panel-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 3px; flex-wrap: wrap; }
  section.panel h2 { font-size: 0.98rem; margin: 0; }
  section.panel .tag {
    font-size: 10.5px; font-weight: 700; color: var(--ink-muted); background: var(--page);
    border-radius: 999px; padding: 1.5px 8px;
  }
  section.panel .sub { color: var(--ink-secondary); font-size: 12.5px; margin: 0 0 16px; }
  section.panel .finding {
    color: var(--ink-secondary); font-size: 12.5px; margin-top: 14px; line-height: 1.6;
    padding-top: 14px; border-top: 1px solid var(--grid);
  }
  section.panel .finding strong { color: var(--ink-primary); }

  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }

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
    font-size: 11.5px; padding: 6px 10px; border-radius: 6px; white-space: nowrap;
    transform: translate(-50%, -100%); opacity: 0; transition: opacity 0.1s; z-index: 10;
    top: 0; left: 0;
  }
  .tooltip.show { opacity: 0.97; }

  table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-top: 4px; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); }
  th { color: var(--ink-muted); font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.03em; cursor: pointer; user-select: none; }
  th:hover { color: var(--ink-primary); }
  th.sorted::after { content: " \25BE"; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr:hover td { background: var(--page); }
  .rank-badge {
    display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
    border-radius: 5px; background: var(--page); color: var(--ink-muted); font-size: 10px; font-weight: 700;
    margin-right: 6px;
  }

  ::selection { background: var(--blue-wash); }

  @media (max-width: 880px) {
    main { margin-left: 0; }
    .topbar { padding-left: 60px; }
    .content { padding-left: 16px; padding-right: 16px; }
  }
</style>
</head>
<body>

<button class="sidebar-toggle" id="sidebar-toggle" aria-label="Abrir menú">
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
</button>
<div class="sidebar-backdrop" id="sidebar-backdrop"></div>

<div class="shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand">
      <div class="mark">CS</div>
      <div class="name">CS2 Sudamérica<span>Analytics</span></div>
    </div>

    <div class="nav-label">Hallazgos</div>
    <nav class="nav-list" id="nav-list">
      <a class="nav-item" data-target="s-resumen" href="#s-resumen">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/></svg>
        Resumen
      </a>
      <a class="nav-item" data-target="s-paises" href="#s-paises">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M3 13V7M8 13V3M13 13V9" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        Dominancia por país
      </a>
      <a class="nav-item" data-target="s-aim" href="#s-aim">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="1.6" fill="currentColor"/></svg>
        Aim vs. win rate
      </a>
      <a class="nav-item" data-target="s-desgaste" href="#s-desgaste">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 4.8V8l2.4 1.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        Desgaste
      </a>
      <a class="nav-item" data-target="s-mapas" href="#s-mapas">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 4l4-1.4 4 1.4 4-1.4v9.8l-4 1.4-4-1.4-4 1.4V4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 2.6v9.8M10 4v9.8" stroke="currentColor" stroke-width="1.3"/></svg>
        Mapas
      </a>
      <a class="nav-item" data-target="s-rachas" href="#s-rachas">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M3 12c1-3 2-1 3-4s2-1 3-4 2-1 4-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Rachas activas
      </a>
      <a class="nav-item" data-target="s-revelacion" href="#s-revelacion">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M8 2l1.7 3.6 4 .5-3 2.8.8 4-3.5-1.9-3.5 1.9.8-4-3-2.8 4-.5L8 2z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>
        Jugadores revelación
      </a>
    </nav>

    <hr>
    <div class="nav-label">Proyecto</div>
    <nav class="nav-list">
      <a class="nav-item" href="https://github.com/cervetade/cs2-sudamerica-analytics" target="_blank" rel="noopener">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
        Ver en GitHub
      </a>
      <a class="nav-item" href="https://github.com/cervetade/cs2-sudamerica-analytics/blob/main/README.md" target="_blank" rel="noopener">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M4 2h6l3 3v9H4V2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 7h4M6 9.5h4M6 12h2.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
        README
      </a>
      <a class="nav-item" href="https://github.com/cervetade/cs2-sudamerica-analytics/tree/main/sql" target="_blank" rel="noopener">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><ellipse cx="8" cy="3.2" rx="5" ry="1.6" stroke="currentColor" stroke-width="1.3"/><path d="M3 3.2v9.6c0 .9 2.2 1.6 5 1.6s5-.7 5-1.6V3.2" stroke="currentColor" stroke-width="1.3"/><path d="M3 8c0 .9 2.2 1.6 5 1.6s5-.7 5-1.6" stroke="currentColor" stroke-width="1.3"/></svg>
        Queries SQL
      </a>
      <a class="nav-item" href="https://github.com/cervetade/cs2-sudamerica-analytics/blob/main/docs/ERD.md" target="_blank" rel="noopener">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><rect x="2" y="2.5" width="4.5" height="3.5" rx="0.8" stroke="currentColor" stroke-width="1.2"/><rect x="9.5" y="2.5" width="4.5" height="3.5" rx="0.8" stroke="currentColor" stroke-width="1.2"/><rect x="6" y="10" width="4.5" height="3.5" rx="0.8" stroke="currentColor" stroke-width="1.2"/><path d="M4.2 6v2a1 1 0 001 1H8m3.7-3v2a1 1 0 01-1 1H8m0 0v1" stroke="currentColor" stroke-width="1.1"/></svg>
        Modelo de datos
      </a>
    </nav>

    <div class="foot">
      Datos: <a href="https://docs.faceit.com/docs/data-api/" target="_blank" rel="noopener">FACEIT Data API v4</a><br>
      por <a href="https://github.com/cervetade" target="_blank" rel="noopener">@cervetade</a>
    </div>
  </aside>

  <main>
    <div class="topbar">
      <div>
        <h1>Dashboard</h1>
        <p>CS2 competitivo en Sudamérica — hallazgos navegables, sin correr una sola query.</p>
      </div>
      <a class="btn-primary" href="https://github.com/cervetade/cs2-sudamerica-analytics" target="_blank" rel="noopener">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
        Ver repositorio
      </a>
    </div>

    <div class="content">

      <div class="stat-row" id="s-resumen"><div class="stat-row" id="stat-row" style="grid-column:1/-1;display:contents"></div></div>

      <section class="panel" id="s-paises">
        <div class="panel-head"><h2>Dominancia por país</h2><span class="tag">01</span></div>
        <p class="sub">Jugadores sudamericanos en el top 1000 del ranking FACEIT (región SA), por país</p>
        <div class="chart-wrap" id="chart-paises"></div>
      </section>

      <section class="panel" id="s-aim">
        <div class="panel-head"><h2>¿El aim solo alcanza para ganar?</h2><span class="tag">02</span></div>
        <p class="sub">Win rate real según el rango de headshot % y de K/D — la línea punteada marca 50%, lo esperado al azar</p>
        <div class="grid-2">
          <div><div class="chart-wrap" id="chart-hs"></div></div>
          <div><div class="chart-wrap" id="chart-kd"></div></div>
        </div>
        <p class="finding">Los cuatro grupos de headshot % ganan casi lo mismo — <strong>el aim solo no explica las victorias</strong>. El K/D sí importa, y bastante: por debajo de 0.8 la win rate se hunde a 22%, arriba de 1.3 sube a 85%.</p>
      </section>

      <section class="panel" id="s-desgaste">
        <div class="panel-head"><h2>El desgaste por partidas largas es real</h2><span class="tag">03</span></div>
        <p class="sub">Rendimiento promedio según la duración real de la partida (excluye partidas de torneo sin duración registrada)</p>
        <div class="grid-2">
          <div><div class="chart-wrap" id="chart-desgaste-kd"></div></div>
          <div><div class="chart-wrap" id="chart-desgaste-hs"></div></div>
        </div>
        <p class="finding">El K/D promedio cae de <strong>1.19 a 1.01</strong> y el headshot % de <strong>55.7% a 49.2%</strong> entre partidas cortas (≤30 min) y largas (60+ min).</p>
      </section>

      <section class="panel" id="s-mapas">
        <div class="panel-head"><h2>¿Qué mapa es más parejo?</h2><span class="tag">04</span></div>
        <p class="sub">Diferencia de rondas promedio entre ganador y perdedor, por mapa (mínimo 20 partidas jugadas)</p>
        <div class="chart-wrap" id="chart-mapas"></div>
      </section>

      <section class="panel" id="s-rachas">
        <div class="panel-head"><h2>Rachas activas</h2><span class="tag">05</span></div>
        <p class="sub">Jugadores con más partidas ganadas seguidas ahora mismo — LAG() + patrón "gaps and islands"</p>
        <div class="chart-wrap" id="chart-rachas"></div>
      </section>

      <section class="panel" id="s-revelacion">
        <div class="panel-head"><h2>Jugadores "revelación"</h2><span class="tag">06</span></div>
        <p class="sub">ELO relativamente bajo para su nivel, pero rendimiento real muy por encima de lo esperado — clic en una columna para ordenar</p>
        <div id="table-revelacion"></div>
        <p class="finding">Apareció <strong>coldzera</strong> — el histórico jugador profesional brasileño — con un K/D real de 1.95, el más alto de todos los sudamericanos con muestra suficiente para el análisis.</p>
      </section>

    </div>
  </main>
</div>

<div class="tooltip" id="tooltip"></div>

<script>
const DATA = __DATA_JSON__;

/* ---------- mobile sidebar ---------- */
const sidebar = document.getElementById("sidebar");
const toggleBtn = document.getElementById("sidebar-toggle");
const backdrop = document.getElementById("sidebar-backdrop");
function openSidebar() { sidebar.classList.add("open"); backdrop.style.display = "block"; }
function closeSidebar() { sidebar.classList.remove("open"); backdrop.style.display = "none"; }
toggleBtn.addEventListener("click", () => sidebar.classList.contains("open") ? closeSidebar() : openSidebar());
backdrop.addEventListener("click", closeSidebar);

const mq = window.matchMedia("(max-width: 880px)");
function applyResponsive() {
  if (mq.matches) {
    sidebar.style.transform = sidebar.classList.contains("open") ? "translateX(0)" : "translateX(-100%)";
    toggleBtn.style.display = "flex";
  } else {
    sidebar.style.transform = "";
    toggleBtn.style.display = "none";
    backdrop.style.display = "none";
  }
}
mq.addEventListener("change", applyResponsive);
new MutationObserver(applyResponsive).observe(sidebar, { attributes: true, attributeFilter: ["class"] });
applyResponsive();

document.querySelectorAll('.nav-item[data-target]').forEach(a => {
  a.addEventListener("click", () => { if (mq.matches) closeSidebar(); });
});

/* ---------- scrollspy ---------- */
const navItems = Array.from(document.querySelectorAll('.nav-item[data-target]'));
const sections = navItems.map(a => document.getElementById(a.dataset.target)).filter(Boolean);
const spy = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    const link = navItems.find(a => a.dataset.target === entry.target.id);
    if (!link) return;
    if (entry.isIntersecting) {
      navItems.forEach(a => a.classList.remove("active"));
      link.classList.add("active");
    }
  });
}, { rootMargin: "-15% 0px -70% 0px", threshold: 0 });
sections.forEach(s => spy.observe(s));

/* ---------- tooltip ---------- */
const tooltip = document.getElementById("tooltip");
function showTooltip(evt, html) { tooltip.innerHTML = html; tooltip.classList.add("show"); moveTooltip(evt); }
function moveTooltip(evt) {
  const wrap = evt.currentTarget.closest(".chart-wrap");
  const x = evt.clientX - wrap.getBoundingClientRect().left;
  const y = evt.clientY - wrap.getBoundingClientRect().top;
  tooltip.style.left = (wrap.offsetLeft + x) + "px";
  tooltip.style.top = (wrap.offsetTop + y - 10) + "px";
}
function hideTooltip() { tooltip.classList.remove("show"); }

const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }

function verticalBars(containerId, items, opts) {
  opts = opts || {};
  const container = document.getElementById(containerId);
  const width = container.clientWidth || 420;
  const height = opts.height || 250;
  const padTop = 16, padBottom = 32, padSide = 8;
  const maxVal = opts.max || Math.max(...items.map(d => d.value)) * 1.2;
  const n = items.length, gap = 0.38;
  const bw = (width - padSide * 2) / n;
  const svg = el("svg", { width: "100%", height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "" });

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
  container.innerHTML = ""; container.appendChild(svg);
}

function horizontalBars(containerId, items, opts) {
  opts = opts || {};
  const container = document.getElementById(containerId);
  const width = container.clientWidth || 420;
  const rowH = opts.rowH || 30;
  const padLeft = opts.padLeft || 92, padRight = 52;
  const height = items.length * rowH + 8;
  const maxVal = opts.max || Math.max(...items.map(d => d.value)) * 1.12;
  const svg = el("svg", { width: "100%", height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "" });
  items.forEach((d, i) => {
    const y = i * rowH + 6, barH = rowH - 12;
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
  container.innerHTML = ""; container.appendChild(svg);
}

(function () {
  const r = DATA.resumen;
  const tiles = [
    { num: r.jugadores_sa.toLocaleString("es-AR"), label: "Jugadores SA en el top 1000" },
    { num: r.total_partidas.toLocaleString("es-AR"), label: "Partidas analizadas" },
    { num: r.total_mapas.toLocaleString("es-AR"), label: "Mapas jugados" },
    { num: r.filas_stats.toLocaleString("es-AR"), label: "Filas jugador/mapa" },
  ];
  const box = document.getElementById("stat-row");
  tiles.forEach(t => {
    const div = document.createElement("div");
    div.className = "stat";
    div.innerHTML = `<div class="num">${t.num}</div><div class="label">${t.label}</div>`;
    box.appendChild(div);
  });
})();

verticalBars("chart-paises", DATA.dominancia_por_pais.map(d => ({
  label: d.country, value: d.n, valueLabel: `${d.n}`, color: "var(--blue)",
  tip: `<b>${d.country}</b>: ${d.n} jugadores (${d.pct}%)`
})), { ariaLabel: "Jugadores por país" });

const seqColors = ["var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)"];
verticalBars("chart-hs", DATA.hs_vs_winrate.map((d, i) => ({
  label: d.rango, value: d.winrate, valueLabel: `${d.winrate}%`, color: seqColors[i],
  tip: `<b>HS% ${d.rango}</b>: ${d.winrate}% win rate`
})), { max: 58, refLine: 50, ariaLabel: "Win rate por rango de headshot %" });

const seq5Colors = ["var(--seq5-1)", "var(--seq5-2)", "var(--seq5-3)", "var(--seq5-4)", "var(--seq5-5)"];
const kdOrder = ["< 0.8", "0.8-1.0", "1.0-1.3", "1.3+", "2.0+"];
const kdSorted = kdOrder.map(r => DATA.kd_vs_winrate.find(d => d.rango === r)).filter(Boolean);
verticalBars("chart-kd", kdSorted.map((d, i) => ({
  label: d.rango, value: d.winrate, valueLabel: `${d.winrate}%`, color: seq5Colors[i],
  tip: `<b>K/D ${d.rango}</b>: ${d.winrate}% win rate`
})), { max: 95, refLine: 50, ariaLabel: "Win rate por rango de K/D" });

verticalBars("chart-desgaste-kd", DATA.desgaste.map(d => ({
  label: d.bucket, value: d.kd, valueLabel: d.kd, color: "var(--blue)",
  tip: `<b>${d.bucket}</b>: K/D promedio ${d.kd} (n=${d.n.toLocaleString("es-AR")})`
})), { ariaLabel: "K/D promedio por duración de partida" });
verticalBars("chart-desgaste-hs", DATA.desgaste.map(d => ({
  label: d.bucket, value: d.hs, valueLabel: `${d.hs}%`, color: "var(--orange)",
  tip: `<b>${d.bucket}</b>: HS% promedio ${d.hs}% (n=${d.n.toLocaleString("es-AR")})`
})), { ariaLabel: "Headshot % promedio por duración de partida" });

const mapasSorted = [...DATA.mapas].sort((a, b) => a.diferencia_rondas - b.diferencia_rondas);
horizontalBars("chart-mapas", mapasSorted.map((d, i) => ({
  label: `de_${d.map}` + (i === 0 ? "  ★" : ""), value: d.diferencia_rondas, valueLabel: d.diferencia_rondas, color: "var(--blue)",
  tip: `<b>de_${d.map}</b>: diferencia de ${d.diferencia_rondas} rondas en promedio (${d.partidas} partidas, ${d.clasificacion})`
})), { max: Math.max(...mapasSorted.map(d => d.diferencia_rondas)) * 1.15, ariaLabel: "Diferencia de rondas por mapa" });

horizontalBars("chart-rachas", DATA.rachas.map(d => ({
  label: d.nickname, value: d.largo, valueLabel: `${d.largo}`, color: "var(--blue)",
  tip: `<b>${d.nickname}</b>: racha de ${d.largo} partidas ganadas seguidas`
})), { ariaLabel: "Racha ganadora activa por jugador" });

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
      th.addEventListener("click", () => { if (sortKey === c.key) sortDir *= -1; else { sortKey = c.key; sortDir = -1; } render(); });
      trh.appendChild(th);
    });
    thead.appendChild(trh); table.appendChild(thead);
    const tbody = document.createElement("tbody");
    rows.forEach((r, i) => {
      const tr = document.createElement("tr");
      cols.forEach((c, ci) => {
        const td = document.createElement("td");
        if (c.num) td.classList.add("num");
        if (ci === 0) {
          td.innerHTML = `<span class="rank-badge">${i + 1}</span><b>${r.nickname}</b>`;
        } else {
          td.textContent = c.fmt ? c.fmt(r[c.key]) : r[c.key];
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    const box = document.getElementById("table-revelacion");
    box.innerHTML = ""; box.appendChild(table);
  }
  render();
})();

window.addEventListener("resize", () => { clearTimeout(window.__rz); window.__rz = setTimeout(() => location.reload(), 300); });
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
    INDEX_PATH.write_text(html, encoding="utf-8")  # copia idéntica, para servir en la raíz (Vercel, GitHub Pages)
    print(f"Listo: {OUT_PATH} (y {INDEX_PATH.name}, copia identica para hosting)")


if __name__ == "__main__":
    main()
