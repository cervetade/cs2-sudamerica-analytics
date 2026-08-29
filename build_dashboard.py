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

# Recorte de temporada: todos los hallazgos basados en PARTIDAS (no en el
# ranking/ELO, que ya es una foto del estado actual) se limitan a partidas
# jugadas desde el inicio de la Temporada 9 de FACEIT en adelante. FACEIT no
# expone un campo "season" en los endpoints de partidas/historial de la Data
# API v4 -- por eso el corte es una fecha fija que hay que actualizar a mano
# cuando arranque una temporada nueva (no se detecta solo).
SEASON_LABEL = "Temporada 9"
SEASON_START_ISO = "2026-08-05"  # inicio Temporada 9 (soft ELO reset)
SEASON_START_EPOCH = 1785888000  # unixepoch de SEASON_START_ISO 00:00 UTC

# Temporada 8 (cerrada) -- para la sección de comparación entre temporadas.
# A diferencia de la 9, esta ventana ya no se mueve: no hace falta actualizarla.
SEASON8_LABEL = "Temporada 8"
SEASON8_FROM_ISO = "2026-04-22"
SEASON8_TO_ISO = "2026-08-04"


def season_findings(cur, where_clause, params):
    """Recalcula todos los hallazgos basados en PARTIDAS (no en el ranking/ELO,
    que es una foto del estado actual) recortados a una ventana de tiempo --
    where_clause es una condición SQL sobre m.finished_at (ej. "m.finished_at
    >= ?" o "m.finished_at BETWEEN strftime('%s', ?) AND strftime('%s', ?)"),
    y params son los parámetros que la completan. Se usa una vez para la
    Temporada 9 (en curso) y otra para la Temporada 8 (cerrada) -- ver
    llamadas más abajo -- para poder mostrar cada temporada por separado
    Y compararlas (sql/10), sin duplicar las queries dos veces a mano.
    """
    f = {}

    f["mapas"] = [
        {"map": r[0].replace("de_", ""), "partidas": r[1], "rondas_promedio": r[2],
         "diferencia_rondas": r[3], "clasificacion": r[4]}
        for r in cur.execute(f"""
            SELECT mm.map, COUNT(*), ROUND(AVG(mm.rounds_total), 1), ROUND(AVG(mm.round_diff), 2),
                CASE WHEN AVG(mm.round_diff) <= 5 THEN 'Parejo' WHEN AVG(mm.round_diff) <= 8 THEN 'Normal' ELSE 'Desbalanceado' END
            FROM match_maps mm JOIN matches m ON mm.match_id = m.match_id
            WHERE mm.round_diff IS NOT NULL AND {where_clause}
            GROUP BY mm.map HAVING COUNT(*) >= 20
            ORDER BY 4 ASC
        """, params).fetchall()
    ]

    f["hs_vs_winrate"] = [
        {"rango": r[0], "winrate": r[1]}
        for r in cur.execute(f"""
            SELECT CASE WHEN mps.headshots_percent < 30 THEN '< 30%' WHEN mps.headshots_percent < 45 THEN '30-45%'
                WHEN mps.headshots_percent < 60 THEN '45-60%' ELSE '60%+' END AS rango_hs,
                ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1)
            FROM match_player_stats mps JOIN matches m ON mps.match_id = m.match_id
            WHERE mps.headshots_percent IS NOT NULL AND {where_clause}
            GROUP BY rango_hs ORDER BY MIN(mps.headshots_percent)
        """, params).fetchall()
    ]

    f["kd_vs_winrate"] = [
        {"rango": r[0], "winrate": r[1]}
        for r in cur.execute(f"""
            SELECT CASE WHEN mps.deaths = 0 THEN '2.0+' WHEN mps.kills*1.0/mps.deaths < 0.8 THEN '< 0.8'
                WHEN mps.kills*1.0/mps.deaths < 1.0 THEN '0.8-1.0' WHEN mps.kills*1.0/mps.deaths < 1.3 THEN '1.0-1.3' ELSE '1.3+' END AS rango_kd,
                ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1)
            FROM match_player_stats mps JOIN matches m ON mps.match_id = m.match_id
            WHERE {where_clause}
            GROUP BY rango_kd ORDER BY MIN(mps.kills*1.0/NULLIF(mps.deaths,0))
        """, params).fetchall()
    ]

    f["desgaste"] = [
        {"bucket": r[0], "kd": r[1], "hs": r[2], "n": r[3]}
        for r in cur.execute(f"""
            SELECT CASE WHEN m.duration_minutes <= 30 THEN '<= 30 min' WHEN m.duration_minutes <= 45 THEN '30-45 min'
                WHEN m.duration_minutes <= 60 THEN '45-60 min' ELSE '60+ min' END AS bucket,
                ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2),
                ROUND(AVG(mps.headshots_percent), 1),
                COUNT(*)
            FROM match_player_stats mps JOIN matches m ON mps.match_id = m.match_id
            WHERE m.has_valid_duration = 1 AND {where_clause}
            GROUP BY bucket ORDER BY MIN(m.duration_minutes)
        """, params).fetchall()
    ]

    f["mapa_pais"] = [
        {"pais": r[0], "mapa": r[1].replace("de_", ""), "filas": r[2], "winrate_mapa": r[3],
         "winrate_base": r[4], "diferencia": r[5]}
        for r in cur.execute(f"""
            WITH baseline_pais AS (
                SELECT p.country, ROUND(100.0*SUM(mps.team_won)/COUNT(*), 1) AS winrate_base, COUNT(*) AS filas_base
                FROM match_player_stats mps JOIN players p ON mps.player_id = p.player_id
                JOIN matches m ON mps.match_id = m.match_id
                WHERE p.country IN ('br','ar','cl') AND {where_clause} GROUP BY p.country
            ),
            por_mapa AS (
                SELECT p.country, mps.map, COUNT(*) AS filas, ROUND(100.0*SUM(mps.team_won)/COUNT(*), 1) AS winrate_mapa
                FROM match_player_stats mps JOIN players p ON mps.player_id = p.player_id
                JOIN matches m ON mps.match_id = m.match_id
                WHERE p.country IN ('br','ar','cl') AND {where_clause} GROUP BY p.country, mps.map HAVING COUNT(*) >= 30
            )
            SELECT UPPER(pm.country), pm.map, pm.filas, pm.winrate_mapa, b.winrate_base,
                ROUND(pm.winrate_mapa - b.winrate_base, 1)
            FROM por_mapa pm JOIN baseline_pais b ON pm.country = b.country
            ORDER BY pm.country, 6 DESC
        """, params * 2).fetchall()
    ]

    f["hora_pico"] = [
        {"franja": r[0], "partidas": r[1], "pct": r[2]}
        for r in cur.execute(f"""
            SELECT
                CASE WHEN hora BETWEEN 6 AND 11 THEN 'Mañana (6-11h)'
                     WHEN hora BETWEEN 12 AND 17 THEN 'Tarde (12-17h)'
                     WHEN hora BETWEEN 18 AND 23 THEN 'Noche (18-23h)'
                     ELSE 'Madrugada (0-5h)' END AS franja,
                COUNT(*), ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM matches m WHERE {where_clause}),1)
            FROM (
                SELECT CAST(strftime('%H', datetime(finished_at - 3*3600, 'unixepoch')) AS INTEGER) AS hora
                FROM matches m WHERE finished_at IS NOT NULL AND {where_clause}
            )
            GROUP BY franja ORDER BY 2 DESC
        """, params * 2).fetchall()
    ]

    f["total_partidas"] = cur.execute(f"SELECT COUNT(*) FROM matches m WHERE {where_clause}", params).fetchone()[0]
    f["total_mapas"] = cur.execute(f"""
        SELECT COUNT(*) FROM match_maps mm JOIN matches m ON mm.match_id = m.match_id WHERE {where_clause}
    """, params).fetchone()[0]
    f["filas_stats"] = cur.execute(f"""
        SELECT COUNT(*) FROM match_player_stats mps JOIN matches m ON mps.match_id = m.match_id WHERE {where_clause}
    """, params).fetchone()[0]

    return f


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

    # --------------------------------------------------------------------
    # Hallazgos de partidas, calculados una vez por Temporada 9 (en curso) y
    # otra por Temporada 8 (cerrada) -- ver season_findings() arriba. Los que
    # dependen del ranking/ELO actual (dominancia por país, rachas, jugadores
    # revelación, ELO por país) NO se repiten por temporada porque la tabla
    # `players` es una sola foto del estado actual (no hay snapshot histórico
    # del ranking de la Temporada 8).
    # --------------------------------------------------------------------
    WHERE_T9 = "m.finished_at >= ?"
    PARAMS_T9 = (SEASON_START_EPOCH,)
    WHERE_T8 = "m.finished_at BETWEEN strftime('%s', ?) AND strftime('%s', ?)"
    PARAMS_T8 = (SEASON8_FROM_ISO, SEASON8_TO_ISO)

    t9 = season_findings(cur, WHERE_T9, PARAMS_T9)
    t8 = season_findings(cur, WHERE_T8, PARAMS_T8)

    data["mapas"] = t9["mapas"]
    data["mapas_t8"] = t8["mapas"]
    data["hs_vs_winrate"] = t9["hs_vs_winrate"]
    data["hs_vs_winrate_t8"] = t8["hs_vs_winrate"]
    data["kd_vs_winrate"] = t9["kd_vs_winrate"]
    data["kd_vs_winrate_t8"] = t8["kd_vs_winrate"]

    data["jugadores_revelacion"] = [
        {"nickname": r[0], "country": r[1].upper(), "elo": r[2], "mapas_jugados": r[3], "kd_real": r[4],
         "winrate_real": r[5], "percentil_elo": r[6], "percentil_kd": r[7], "diferencia": r[8]}
        for r in cur.execute("""
            WITH rendimiento_real AS (
                SELECT mps.player_id, COUNT(*) AS mapas_jugados,
                    ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2) AS kd_real,
                    ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1) AS winrate_real
                FROM match_player_stats mps JOIN matches m ON mps.match_id = m.match_id
                WHERE m.finished_at >= ?
                GROUP BY mps.player_id HAVING COUNT(*) >= 5
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
        """, (SEASON_START_EPOCH,)).fetchall()
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
                JOIN players p ON mps.player_id = p.player_id
                WHERE p.is_sa_country = 1 AND m.finished_at >= ?
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
        """, (SEASON_START_EPOCH,)).fetchall()
    ]

    data["desgaste"] = t9["desgaste"]
    data["desgaste_t8"] = t8["desgaste"]

    total_jugadores = cur.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    jugadores_sa = cur.execute("SELECT COUNT(*) FROM players WHERE is_sa_country=1").fetchone()[0]

    # jugadores_sa/total_jugadores son del roster ACTUAL (no hay snapshot por
    # temporada), así que se repiten igual en resumen y resumen_t8.
    data["resumen"] = {
        "total_jugadores": total_jugadores,
        "jugadores_sa": jugadores_sa,
        "total_partidas": t9["total_partidas"],
        "total_mapas": t9["total_mapas"],
        "filas_stats": t9["filas_stats"],
        "season_label": SEASON_LABEL,
        "season_start": SEASON_START_ISO,
    }

    data["resumen_t8"] = {
        "total_jugadores": total_jugadores,
        "jugadores_sa": jugadores_sa,
        "total_partidas": t8["total_partidas"],
        "total_mapas": t8["total_mapas"],
        "filas_stats": t8["filas_stats"],
        "season_label": SEASON8_LABEL,
        "season_start": SEASON8_FROM_ISO,
        "season_end": SEASON8_TO_ISO,
    }

    data["mapa_pais"] = t9["mapa_pais"]
    data["mapa_pais_t8"] = t8["mapa_pais"]

    data["elo_por_pais"] = [
        {"pais": r[0], "jugadores": r[1], "elo_promedio": r[2],
         "kd_promedio_historico": r[3], "winrate_promedio_historico": r[4]}
        for r in cur.execute("""
            SELECT UPPER(country), COUNT(*), ROUND(AVG(faceit_elo),0),
                ROUND(AVG(lifetime_kd_ratio),2), ROUND(AVG(lifetime_win_rate_percent),1)
            FROM players WHERE is_sa_country=1
            GROUP BY country HAVING COUNT(*)>=10 ORDER BY 3 DESC
        """).fetchall()
    ]

    data["hora_pico"] = t9["hora_pico"]
    data["hora_pico_t8"] = t8["hora_pico"]

    # --------------------------------------------------------------------
    # Comparación Temporada 8 (cerrada) vs Temporada 9 (en curso). Reutiliza
    # los mismos resultados de t8/t9 de arriba -- una sola fuente de verdad,
    # nada de repetir las queries. Solo se comparan métricas de PARTIDAS (no
    # ranking/ELO, ver sql/10).
    # --------------------------------------------------------------------
    DUR_BUCKETS = ["<= 30 min", "30-45 min", "45-60 min", "60+ min"]
    HORA_BUCKETS = ["Mañana (6-11h)", "Tarde (12-17h)", "Noche (18-23h)", "Madrugada (0-5h)"]

    desg_t8_map = {d["bucket"]: d for d in t8["desgaste"]}
    desg_t9_map = {d["bucket"]: d for d in t9["desgaste"]}
    hora_t8_map = {d["franja"]: d for d in t8["hora_pico"]}
    hora_t9_map = {d["franja"]: d for d in t9["hora_pico"]}

    data["temporada_comparacion"] = {
        "season8_label": SEASON8_LABEL,
        "season9_label": SEASON_LABEL,
        "partidas_t8": t8["total_partidas"],
        "partidas_t9": t9["total_partidas"],
        "desgaste": {
            "categorias": DUR_BUCKETS,
            "t8_kd": [desg_t8_map[b]["kd"] if b in desg_t8_map else None for b in DUR_BUCKETS],
            "t9_kd": [desg_t9_map[b]["kd"] if b in desg_t9_map else None for b in DUR_BUCKETS],
            "t8_hs": [desg_t8_map[b]["hs"] if b in desg_t8_map else None for b in DUR_BUCKETS],
            "t9_hs": [desg_t9_map[b]["hs"] if b in desg_t9_map else None for b in DUR_BUCKETS],
        },
        "hora_pico": {
            "categorias": HORA_BUCKETS,
            "t8_pct": [hora_t8_map[b]["pct"] if b in hora_t8_map else 0 for b in HORA_BUCKETS],
            "t9_pct": [hora_t9_map[b]["pct"] if b in hora_t9_map else 0 for b in HORA_BUCKETS],
        },
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
    --t8: #c2410c;   /* Temporada 8 (histórica) en los charts que comparan temporadas -- T9 sigue usando --blue */
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

    /* colores por país (identidad de bandera, no la rampa categórica default) */
    --c-br: #0ca34f;   /* Brasil: verde */
    --c-ar: #4fa8d8;   /* Argentina: celeste */
    --c-cl: #d1453b;   /* Chile: rojo */
    --c-uy: #8aa4c4;   /* Uruguay: celeste apagado, para no pisar a AR */
    --c-py: #c9a178;   /* Paraguay: terracota */
    --c-ve: #d9c66b;   /* Venezuela: dorado */
    --c-pe: #b98a94;   /* Perú: rojo malva apagado, para no pisar a CL */
    --c-bo: #a3b18a;   /* Bolivia: verde salvia apagado, para no pisar a BR */

    /* colores por mapa (paleta reconocible de cada mapa en CS2) */
    --m-de_mirage: #eda100;   /* amarillo arena */
    --m-de_dust2: #b08968;    /* marrón polvo árabe */
    --m-de_inferno: #d1453b;  /* rojo fuego */
    --m-de_cache: #8b2f2a;    /* rojo ladrillo soviético */
    --m-de_nuke: #3aa0c9;     /* celeste industrial */
    --m-de_anubis: #c9962c;   /* dorado/bronce egipcio */
    --m-de_ancient: #6b8f5a;  /* verde musgo de templo */

    /* diverging: mejor / peor que el propio promedio */
    --diverge-pos: #0ca30c;
    --diverge-neg: #d1453b;
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
      --t8: #cf6b34;
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

      --c-br: #22c168;
      --c-ar: #6cbfe8;
      --c-cl: #e2645a;
      --c-uy: #9db4d1;
      --c-py: #d4b28c;
      --c-ve: #e3d17e;
      --c-pe: #c79aa3;
      --c-bo: #b3c09c;

      --m-de_mirage: #f5b833;
      --m-de_dust2: #c9a281;
      --m-de_inferno: #e2645a;
      --m-de_cache: #b04840;
      --m-de_nuke: #5bc0de;
      --m-de_anubis: #e0b355;
      --m-de_ancient: #8bb377;

      --diverge-pos: #1ec01e;
      --diverge-neg: #e2645a;
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

  .tab-switch {
    display: inline-flex; gap: 3px; background: var(--page); border: 1px solid var(--border);
    padding: 3px; border-radius: 10px; margin: 18px 32px 0;
  }
  .tab-btn {
    appearance: none; border: none; background: transparent; color: var(--ink-secondary);
    font-family: inherit; font-weight: 600; font-size: 12.5px; padding: 8px 16px;
    border-radius: 8px; cursor: pointer; display: flex; align-items: center; gap: 7px;
  }
  .tab-btn .tab-btn-sub {
    font-weight: 500; font-size: 10px; color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.03em;
  }
  .tab-btn.active { background: var(--surface); color: var(--ink-primary); border: 1px solid var(--border); }
  .tab-btn.active .tab-btn-sub { color: var(--blue); }
  .tab-btn:not(.active):hover { color: var(--ink-primary); }
  .tab-hidden { display: none !important; }
  @media (max-width: 880px) { .tab-switch { margin-left: 16px; margin-right: 16px; } }

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
  .season-badge {
    display: inline-flex; align-items: center; font-family: 'Geist Mono', ui-monospace, monospace;
    font-size: 10.5px; font-weight: 600; color: var(--blue); background: color-mix(in srgb, var(--blue) 12%, transparent);
    border-radius: 999px; padding: 2px 9px; margin-left: 8px; vertical-align: middle;
  }
  section.panel .sub { color: var(--ink-secondary); font-size: 12.5px; margin: 0 0 16px; }
  section.panel .finding {
    color: var(--ink-secondary); font-size: 12.5px; margin-top: 14px; line-height: 1.6;
    padding-top: 14px; border-top: 1px solid var(--grid);
  }
  section.panel .finding strong { color: var(--ink-primary); }

  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 640px) { .grid-2 { grid-template-columns: 1fr; } }

  .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  @media (max-width: 820px) { .grid-3 { grid-template-columns: 1fr; } }
  .grid-3 h3 { font-size: 12px; font-weight: 700; color: var(--ink-secondary); margin: 0 0 8px; text-align: center; }

  .chart-wrap { position: relative; }
  .chart-legend { display: flex; gap: 16px; flex-wrap: wrap; margin: 0 0 10px; }
  .chart-legend .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink-secondary); }
  .chart-legend .legend-dot { width: 9px; height: 9px; border-radius: 3px; flex-shrink: 0; }
  svg text { fill: var(--ink-secondary); font-family: inherit; }
  svg .value-label { fill: var(--ink-primary); font-weight: 600; }
  svg .axis-label { fill: var(--ink-muted); font-size: 10.5px; }
  svg .baseline { stroke: var(--baseline); stroke-width: 1; }
  svg .ref-line { stroke: var(--baseline); stroke-width: 1; stroke-dasharray: 3 3; }
  .bar { cursor: pointer; transition: opacity 0.12s, height 0.55s cubic-bezier(.22,.9,.3,1), y 0.55s cubic-bezier(.22,.9,.3,1), width 0.55s cubic-bezier(.22,.9,.3,1); }
  .bar:hover { opacity: 0.82; }
  svg .value-label { opacity: 0; transition: opacity 0.35s ease 0.4s; }
  svg .value-label.show { opacity: 1; }

  /* ---------- aparición de secciones al hacer scroll ---------- */
  .reveal { opacity: 0; transform: translateY(14px); transition: opacity 0.6s ease, transform 0.6s ease; }
  .reveal.show { opacity: 1; transform: translateY(0); }
  @media (prefers-reduced-motion: reduce) {
    .reveal { opacity: 1; transform: none; transition: none; }
    .bar { transition: opacity 0.12s; }
    svg .value-label { opacity: 1; transition: none; }
  }

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

    <div class="nav-label" id="nav-label-t8">Hallazgos — Temporada 8</div>
    <nav class="nav-list" id="nav-list-t8" data-tab="t8">
      <a class="nav-item" data-target="s-resumen-t8" href="#s-resumen-t8">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/></svg>
        Resumen
      </a>
      <a class="nav-item" data-target="s-mapas-t8" href="#s-mapas-t8">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 4l4-1.4 4 1.4 4-1.4v9.8l-4 1.4-4-1.4-4 1.4V4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 2.6v9.8M10 4v9.8" stroke="currentColor" stroke-width="1.3"/></svg>
        Mapas
      </a>
      <a class="nav-item" data-target="s-aim-t8" href="#s-aim-t8">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="1.6" fill="currentColor"/></svg>
        Aim vs. win rate
      </a>
      <a class="nav-item" data-target="s-desgaste-t8" href="#s-desgaste-t8">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 4.8V8l2.4 1.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        Desgaste
      </a>
      <a class="nav-item" data-target="s-mapapais-t8" href="#s-mapapais-t8">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 4l4-1.4 4 1.4 4-1.4v9.8l-4 1.4-4-1.4-4 1.4V4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 2.6v9.8M10 4v9.8" stroke="currentColor" stroke-width="1.3"/></svg>
        Mapa por país
      </a>
      <a class="nav-item" data-target="s-hora-t8" href="#s-hora-t8">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 5v3.3l2.3 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        Hora pico de juego
      </a>
    </nav>

    <div class="nav-label tab-hidden" id="nav-label-t9">Hallazgos — Temporada 9</div>
    <nav class="nav-list tab-hidden" id="nav-list-t9" data-tab="t9">
      <a class="nav-item" data-target="s-resumen-t9" href="#s-resumen-t9">
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
      <a class="nav-item" data-target="s-mapapais" href="#s-mapapais">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 4l4-1.4 4 1.4 4-1.4v9.8l-4 1.4-4-1.4-4 1.4V4z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M6 2.6v9.8M10 4v9.8" stroke="currentColor" stroke-width="1.3"/></svg>
        Mapa por país
      </a>
      <a class="nav-item" data-target="s-elo" href="#s-elo">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M8 1.6L3 4v4.4c0 3 2.1 5.4 5 6 2.9-.6 5-3 5-6V4L8 1.6z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
        ELO por país
      </a>
      <a class="nav-item" data-target="s-hora" href="#s-hora">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M8 5v3.3l2.3 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        Hora pico de juego
      </a>
      <a class="nav-item" data-target="s-temporada8" href="#s-temporada8">
        <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M2 13.5V8.5M6 13.5V4M10 13.5V6.5M14 13.5V2.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        Temporada 8 vs. 9
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
        <h1>Dashboard <span class="season-badge" id="season-badge">Temporada 8</span></h1>
        <p id="header-sub">CS2 competitivo en Sudamérica — hallazgos navegables, sin correr una sola query. Temporada 8 completa y cerrada (22 abr – 4 ago 2026): la muestra más grande y estable para sacar conclusiones.</p>
      </div>
      <a class="btn-primary" href="https://github.com/cervetade/cs2-sudamerica-analytics" target="_blank" rel="noopener">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>
        Ver repositorio
      </a>
    </div>

    <div class="tab-switch" role="tablist" id="tab-switch">
      <button class="tab-btn active" data-tab="t8" role="tab" aria-selected="true">Temporada 8<span class="tab-btn-sub">cerrada</span></button>
      <button class="tab-btn" data-tab="t9" role="tab" aria-selected="false">Temporada 9<span class="tab-btn-sub">en curso</span></button>
    </div>

    <div class="content">

      <div class="tab-panel" data-tab="t8" id="tab-panel-t8">

      <div class="stat-row" id="s-resumen-t8"><div class="stat-row" id="stat-row-t8" style="grid-column:1/-1;display:contents"></div></div>

      <section class="panel reveal" id="s-mapas-t8">
        <div class="panel-head"><h2>¿Qué mapa es más parejo?</h2><span class="tag">01</span></div>
        <p class="sub">Diferencia de rondas promedio entre ganador y perdedor, por mapa (mínimo 20 partidas jugadas) — Temporada 8 completa</p>
        <div class="chart-wrap" id="chart-mapas-t8"></div>
      </section>

      <section class="panel reveal" id="s-aim-t8">
        <div class="panel-head"><h2>¿El aim solo alcanza para ganar?</h2><span class="tag">02</span></div>
        <p class="sub">Win rate real según el rango de headshot % y de K/D — la línea punteada marca 50%, lo esperado al azar (Temporada 8 completa)</p>
        <div class="grid-2">
          <div><div class="chart-wrap" id="chart-hs-t8"></div></div>
          <div><div class="chart-wrap" id="chart-kd-t8"></div></div>
        </div>
        <p class="finding" id="finding-aim-t8"></p>
      </section>

      <section class="panel reveal" id="s-desgaste-t8">
        <div class="panel-head"><h2>El desgaste por partidas largas es real</h2><span class="tag">03</span></div>
        <p class="sub">Rendimiento promedio según la duración real de la partida (excluye partidas de torneo sin duración registrada) — Temporada 8 completa</p>
        <div class="grid-2">
          <div><div class="chart-wrap" id="chart-desgaste-kd-t8"></div></div>
          <div><div class="chart-wrap" id="chart-desgaste-hs-t8"></div></div>
        </div>
        <p class="finding" id="finding-desgaste-t8"></p>
      </section>

      <section class="panel reveal" id="s-mapapais-t8">
        <div class="panel-head"><h2>El mapa "propio" de cada país</h2><span class="tag">04</span></div>
        <p class="sub">Cuánto se desvía cada país de su propio promedio en cada mapa, sobre la Temporada 8 completa. Verde = mejor que su costumbre, rojo = peor.</p>
        <div class="grid-3">
          <div><h3>Argentina</h3><div class="chart-wrap" id="chart-mapapais-ar-t8"></div></div>
          <div><h3>Brasil</h3><div class="chart-wrap" id="chart-mapapais-br-t8"></div></div>
          <div><h3>Chile</h3><div class="chart-wrap" id="chart-mapapais-cl-t8"></div></div>
        </div>
        <p class="finding">Chile domina de_nuke muy por encima de su propio promedio; Brasil es el más parejo de los tres. Ver la sección "Temporada 8 vs. 9" para el detalle completo y qué tan sólido es cada patrón.</p>
      </section>

      <section class="panel reveal" id="s-hora-t8">
        <div class="panel-head"><h2>¿A qué hora se juega más CS2 en Sudamérica?</h2><span class="tag">05</span></div>
        <p class="sub">Partidas por franja horaria, aproximado a UTC-3 (horario más común de la región) — Temporada 8 completa</p>
        <div class="chart-wrap" id="chart-hora-t8"></div>
        <p class="finding" id="finding-hora-t8"></p>
      </section>

      </div>

      <div class="tab-panel tab-hidden" data-tab="t9" id="tab-panel-t9">

      <div class="stat-row" id="s-resumen-t9"><div class="stat-row" id="stat-row-t9" style="grid-column:1/-1;display:contents"></div></div>

      <section class="panel reveal" id="s-paises">
        <div class="panel-head"><h2>Dominancia por país</h2><span class="tag">01</span></div>
        <p class="sub">Jugadores sudamericanos en el top 1000 del ranking FACEIT (región SA), por país</p>
        <div class="chart-wrap" id="chart-paises"></div>
      </section>

      <section class="panel reveal" id="s-aim">
        <div class="panel-head"><h2>¿El aim solo alcanza para ganar?</h2><span class="tag">02</span></div>
        <p class="sub">Win rate real según el rango de headshot % y de K/D — la línea punteada marca 50%, lo esperado al azar</p>
        <div class="grid-2">
          <div><div class="chart-wrap" id="chart-hs"></div></div>
          <div><div class="chart-wrap" id="chart-kd"></div></div>
        </div>
        <p class="finding">Los cuatro grupos de headshot % ganan casi lo mismo — <strong>el aim solo no explica las victorias</strong>. El K/D sí importa, y bastante: por debajo de 0.8 la win rate se hunde a 22.5%, arriba de 1.3 sube a 84.6%.</p>
      </section>

      <section class="panel reveal" id="s-desgaste">
        <div class="panel-head"><h2>El desgaste por partidas largas es real</h2><span class="tag">03</span></div>
        <p class="sub">Rendimiento promedio según la duración real de la partida (excluye partidas de torneo sin duración registrada)</p>
        <div class="grid-2">
          <div><div class="chart-wrap" id="chart-desgaste-kd"></div></div>
          <div><div class="chart-wrap" id="chart-desgaste-hs"></div></div>
        </div>
        <p class="finding">El K/D promedio cae de <strong>1.18 a 1.01</strong> y el headshot % de <strong>55.8% a 49.0%</strong> entre partidas cortas (≤30 min) y largas (60+ min).</p>
      </section>

      <section class="panel reveal" id="s-mapas">
        <div class="panel-head"><h2>¿Qué mapa es más parejo?</h2><span class="tag">04</span></div>
        <p class="sub">Diferencia de rondas promedio entre ganador y perdedor, por mapa (mínimo 20 partidas jugadas)</p>
        <div class="chart-wrap" id="chart-mapas"></div>
      </section>

      <section class="panel reveal" id="s-rachas">
        <div class="panel-head"><h2>Rachas activas</h2><span class="tag">05</span></div>
        <p class="sub">Jugadores con más partidas ganadas seguidas ahora mismo — LAG() + patrón "gaps and islands"</p>
        <div class="chart-wrap" id="chart-rachas"></div>
      </section>

      <section class="panel reveal" id="s-revelacion">
        <div class="panel-head"><h2>Jugadores "revelación"</h2><span class="tag">06</span></div>
        <p class="sub">ELO relativamente bajo para su nivel, pero rendimiento real muy por encima de lo esperado — clic en una columna para ordenar</p>
        <div id="table-revelacion"></div>
        <p class="finding">La lidera <strong>lukaazera</strong> (AR), con K/D 1.5 y un rendimiento muy por encima de lo que su ELO haría esperar. También aparece <strong>coldzera</strong> — el histórico jugador profesional brasileño — con el K/D real más alto de la lista (1.95), aunque esta temporada no lidera el ranking: su ELO ya es alto de base, así que tiene menos margen para "sorprender".</p>
      </section>

      <section class="panel reveal" id="s-mapapais">
        <div class="panel-head"><h2>El mapa "propio" de cada país</h2><span class="tag">07</span></div>
        <p class="sub">Cuánto se desvía cada país de su propio promedio en cada mapa (no win rate cruda — cada país arranca de un nivel distinto). Verde = mejor que su costumbre, rojo = peor.</p>
        <div class="grid-3">
          <div><h3>Argentina</h3><div class="chart-wrap" id="chart-mapapais-ar"></div></div>
          <div><h3>Brasil</h3><div class="chart-wrap" id="chart-mapapais-br"></div></div>
          <div><h3>Chile</h3><div class="chart-wrap" id="chart-mapapais-cl"></div></div>
        </div>
        <p class="finding">La intuición decía Argentina-nuke, pero los números dicen otra cosa: <strong>Chile domina de_nuke</strong> muy por encima de su propio promedio (63.9% vs. 54% base, sobre 36 partidas). El mapa fuerte de Argentina es de_cache; el débil, de_anubis. Brasil es el más parejo de los tres — su mayor desvío esta temporada es de apenas -3.3 puntos, en de_inferno.</p>
      </section>

      <section class="panel reveal" id="s-elo">
        <div class="panel-head"><h2>ELO promedio por país</h2><span class="tag">08</span></div>
        <p class="sub">¿Brasil domina solo en cantidad de jugadores, o también en nivel? (países con menos de 10 jugadores en la muestra, excluidos)</p>
        <div class="chart-wrap" id="chart-elo"></div>
        <p class="finding">Brasil no solo tiene 3x más jugadores que Argentina en el top 1000 — también tiene el ELO promedio más alto (2689 vs. 2661). La diferencia es chica, pero va en la misma dirección: acá cantidad y calidad van juntas.</p>
      </section>

      <section class="panel reveal" id="s-hora">
        <div class="panel-head"><h2>¿A qué hora se juega más CS2 en Sudamérica?</h2><span class="tag">09</span></div>
        <p class="sub">Partidas por franja horaria, aproximado a UTC-3 (horario más común de la región)</p>
        <div class="chart-wrap" id="chart-hora"></div>
        <p class="finding">Casi la mitad de las partidas (45.0%) se juegan entre las 18h y las 23h. Sumando la madrugada (27.7%), el bloque noche + trasnoche se lleva más del 72% del total — entre las 6 y las 11 de la mañana el volumen cae a un 1.6%.</p>
      </section>

      <section class="panel reveal" id="s-temporada8">
        <div class="panel-head"><h2>¿Esto es casualidad de esta temporada, o se repite?</h2><span class="tag">10</span></div>
        <p class="sub">Los hallazgos de arriba están recortados a la Temporada 9, que recién lleva unas semanas. Acá se comparan contra la Temporada 8 completa y ya cerrada (22 abr – 4 ago 2026) para ver cuáles se sostienen con otra tanda de partidas y otros jugadores.</p>
        <div class="grid-2">
          <div>
            <div id="legend-desgaste"></div>
            <div class="chart-wrap" id="chart-t89-kd"></div>
          </div>
          <div>
            <div id="legend-desgaste-hs"></div>
            <div class="chart-wrap" id="chart-t89-hs"></div>
          </div>
        </div>
        <p class="finding">El desgaste por partidas largas (hallazgo 03) se repite casi calcado: el K/D promedio cae de <strong>1.20 a 1.01</strong> en la Temporada 8 y de <strong>1.18 a 1.01</strong> en la 9 — mismo tramo final, con jugadores y partidas totalmente distintos.</p>

        <div style="margin-top:22px">
          <div id="legend-hora"></div>
          <div class="chart-wrap" id="chart-t89-hora"></div>
        </div>
        <p class="finding">Los horarios pico (hallazgo 09) también se sostienen: la franja noche (18-23h) se lleva 47.4% de las partidas en la Temporada 8 y 45.2% en la 9 — la forma general de "se juega de noche" no es un capricho de esta temporada.</p>

        <p class="finding">Sobre el mapa propio de cada país (hallazgo 07): <strong>Chile repite a de_nuke</strong> como su mapa fuerte en las dos temporadas (+6.2 puntos sobre su propio promedio en la 8, sobre 107 partidas; +9.9 en la 9). Brasil sigue siendo el más parejo entre mapas en ambas (nunca se desvía más de ±1.7 puntos en la 8, ±3.3 en la 9). Argentina es el caso honesto que no se repite: su mapa fuerte cambió de de_inferno (+4.3, Temporada 8) a de_cache (+8.6, Temporada 9) — no hay una identidad de mapa sólida ahí todavía, así que no se fuerza esa historia.</p>
      </section>

      </div>

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

/* ---------- tab switch: Temporada 8 (cerrada) / Temporada 9 (en curso) ---------- */
const HEADER_TEXT = {
  t8: "CS2 competitivo en Sudamérica — hallazgos navegables, sin correr una sola query. Temporada 8 completa y cerrada (22 abr – 4 ago 2026): la muestra más grande y estable para sacar conclusiones.",
  t9: "CS2 competitivo en Sudamérica — hallazgos navegables, sin correr una sola query. Partidas desde el inicio de la Temporada 9 de FACEIT (5 ago 2026); ranking/ELO reflejan el estado actual.",
};
const seasonBadge = document.getElementById("season-badge");
const headerSub = document.getElementById("header-sub");
const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));
const navGroups = {
  t8: [document.getElementById("nav-label-t8"), document.getElementById("nav-list-t8")],
  t9: [document.getElementById("nav-label-t9"), document.getElementById("nav-list-t9")],
};

function setActiveTab(tab) {
  tabButtons.forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  tabPanels.forEach(p => p.classList.toggle("tab-hidden", p.dataset.tab !== tab));
  Object.entries(navGroups).forEach(([k, els]) => els.forEach(el => el && el.classList.toggle("tab-hidden", k !== tab)));
  seasonBadge.textContent = tab === "t8" ? "Temporada 8" : "Temporada 9";
  headerSub.textContent = HEADER_TEXT[tab];
  // Los paneles recién visibles pueden no haber disparado todavía el
  // revealObserver (algunos navegadores no vuelven a chequear la
  // intersección solo por un cambio de display) -- se fuerza un re-chequeo
  // manual de lo que ya está en viewport apenas se cambia de pestaña.
  requestAnimationFrame(() => {
    document.querySelectorAll(`.tab-panel[data-tab="${tab}"] .reveal`).forEach(elm => {
      if (elm.classList.contains("show")) return;
      const rect = elm.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.92 && rect.bottom > 0) {
        elm.classList.add("show");
        revealObserver.unobserve(elm);
        if (elm.__pendingBarAnims) { elm.__pendingBarAnims.forEach(run => run()); elm.__pendingBarAnims = null; }
      }
    });
  });
  if (mq.matches) closeSidebar();
}
tabButtons.forEach(b => b.addEventListener("click", () => setActiveTab(b.dataset.tab)));
setActiveTab("t8");

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

/* ---------- animación de entrada: barras "creciendo" + labels apareciendo ---------- */
/* Los rects arrancan en tamaño 0 (pegados a la base). En vez de animarlos ya
   mismo (que pasaría fuera de pantalla para todo lo que está más abajo del
   fold), se encolan en el panel ".reveal" que los contiene y se disparan
   recién cuando ESE panel entra en pantalla (ver revealObserver, al final
   del script) -- así el gráfico "carga" cuando el usuario llega a verlo, no
   antes. Si por lo que sea no hay un ".reveal" contenedor, se anima ya. */
function playEntrance(containerEl, bars, labels) {
  const run = () => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        bars.forEach(b => { for (const k in b.final) b.rect.setAttribute(k, b.final[k]); });
        (labels || []).forEach(l => l && l.classList.add("show"));
      });
    });
  };
  const panel = containerEl && containerEl.closest(".reveal");
  if (!panel || panel.classList.contains("show")) { run(); return; }
  (panel.__pendingBarAnims || (panel.__pendingBarAnims = [])).push(run);
}

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
  container.innerHTML = ""; container.appendChild(svg);
  const baseline = height - padBottom;

  if (opts.refLine !== undefined) {
    const y = baseline - (opts.refLine / maxVal) * (height - padTop - padBottom);
    svg.appendChild(el("line", { x1: padSide, x2: width - padSide, y1: y, y2: y, class: "ref-line" }));
  }
  const bars = [], labels = [];
  items.forEach((d, i) => {
    const x = padSide + i * bw + bw * gap / 2;
    const barW = bw * (1 - gap);
    const barH = Math.max(2, (d.value / maxVal) * (height - padTop - padBottom));
    const y = baseline - barH;
    const rect = el("rect", { x, y: baseline, width: barW, height: 0, rx: 3, fill: d.color || "var(--blue)", class: "bar" });
    rect.addEventListener("mouseenter", (e) => showTooltip(e, d.tip || `<b>${d.label}</b>: ${d.value}`));
    rect.addEventListener("mousemove", moveTooltip);
    rect.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(rect);
    bars.push({ rect, final: { y, height: barH } });
    const vlabel = el("text", { x: x + barW / 2, y: y - 6, "text-anchor": "middle", class: "value-label", "font-size": "12" });
    vlabel.textContent = d.valueLabel !== undefined ? d.valueLabel : d.value;
    svg.appendChild(vlabel);
    labels.push(vlabel);
    const llabel = el("text", { x: x + barW / 2, y: height - padBottom + 16, "text-anchor": "middle", class: "axis-label" });
    llabel.textContent = d.label;
    svg.appendChild(llabel);
  });
  svg.appendChild(el("line", { x1: padSide, x2: width - padSide, y1: baseline, y2: baseline, class: "baseline" }));
  playEntrance(container, bars, labels);
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
  container.innerHTML = ""; container.appendChild(svg);
  const bars = [], labels = [];
  items.forEach((d, i) => {
    const y = i * rowH + 6, barH = rowH - 12;
    const barW = Math.max(2, (d.value / maxVal) * (width - padLeft - padRight));
    const label = el("text", { x: padLeft - 8, y: y + barH / 2 + 4, "text-anchor": "end", "font-size": "12" });
    label.textContent = d.label;
    svg.appendChild(label);
    const rect = el("rect", { x: padLeft, y, width: 0, height: barH, rx: 3, fill: d.color || "var(--blue)", class: "bar" });
    rect.addEventListener("mouseenter", (e) => showTooltip(e, d.tip || `<b>${d.label}</b>: ${d.value}`));
    rect.addEventListener("mousemove", moveTooltip);
    rect.addEventListener("mouseleave", hideTooltip);
    svg.appendChild(rect);
    bars.push({ rect, final: { width: barW } });
    const vlabel = el("text", { x: padLeft + barW + 8, y: y + barH / 2 + 4, class: "value-label", "font-size": "12" });
    vlabel.textContent = d.valueLabel !== undefined ? d.valueLabel : d.value;
    svg.appendChild(vlabel);
    labels.push(vlabel);
  });
  playEntrance(container, bars, labels);
}

function renderLegend(containerId, series) {
  const container = document.getElementById(containerId);
  container.innerHTML = "";
  const row = document.createElement("div");
  row.className = "chart-legend";
  series.forEach(s => {
    const item = document.createElement("span");
    item.className = "legend-item";
    item.innerHTML = `<span class="legend-dot" style="background:${s.color}"></span>${s.name}`;
    row.appendChild(item);
  });
  container.appendChild(row);
}

function groupedBars(containerId, categories, series, opts) {
  // Barras agrupadas: N categorías en el eje X, cada una con una barra por
  // serie (acá, Temporada 8 vs Temporada 9). Requiere leyenda (>=2 series,
  // ver dataviz: "legend siempre presente para 2+ series").
  opts = opts || {};
  const container = document.getElementById(containerId);
  const width = container.clientWidth || 420;
  const height = opts.height || 250;
  const padTop = 20, padBottom = 32, padSide = 8;
  const allVals = series.flatMap(s => s.values).filter(v => v !== null && v !== undefined);
  const maxVal = opts.max || Math.max(...allVals) * 1.2;
  const n = categories.length;
  const groupGap = 0.22; // fraccion del ancho del grupo que queda como aire entre grupos
  const barGap = 2;      // "surface gap" entre barras de un mismo grupo (ver marks-and-anatomy)
  const groupW = (width - padSide * 2) / n;
  const innerW = groupW * (1 - groupGap);
  const nSeries = series.length;
  const rawBarW = (innerW - barGap * (nSeries - 1)) / nSeries;
  const barW = Math.min(24, rawBarW); // <=24px de espesor, nunca llena todo el slot
  const totalBarsW = barW * nSeries + barGap * (nSeries - 1);
  const svg = el("svg", { width: "100%", height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "" });
  container.innerHTML = ""; container.appendChild(svg); // ya en el DOM: getComputedTextLength() abajo lo necesita

  const bars = [], labels = [];
  const baseline = height - padBottom;
  categories.forEach((cat, i) => {
    const groupX = padSide + i * groupW;
    const startX = groupX + (groupW - totalBarsW) / 2;
    let topY = baseline;
    const labelParts = [];
    series.forEach((s, si) => {
      const val = s.values[i];
      if (val === null || val === undefined) return;
      const barH = Math.max(2, (val / maxVal) * (height - padTop - padBottom));
      const x = startX + si * (barW + barGap);
      const y = baseline - barH;
      topY = Math.min(topY, y);
      const rect = el("rect", { x, y: baseline, width: barW, height: 0, rx: 3, fill: s.color, class: "bar" });
      const tip = s.tip ? s.tip(cat, val) : `<b>${s.name}</b> — ${cat}: ${val}`;
      rect.addEventListener("mouseenter", (e) => showTooltip(e, tip));
      rect.addEventListener("mousemove", moveTooltip);
      rect.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(rect);
      bars.push({ rect, final: { y, height: barH } });
      labelParts.push({ val, fmt: s.valueLabel ? s.valueLabel(val) : `${val}`, shortFmt: s.shortValueLabel ? s.shortValueLabel(val) : null });
    });
    // Un solo label combinado por grupo (no uno por barra) -- con valores tan
    // parecidos entre temporadas, dos textos pegados se pisan y se vuelven
    // ilegibles (ver dataviz: "label selectivamente, nunca un numero en cada
    // punto"). Si ni la version corta entra en el ancho del grupo, se saca el
    // label del todo -- el tooltip y la leyenda ya cubren el dato (ver
    // dataviz: "un label que no entra no se corta, se mide antes").
    if (labelParts.length) {
      const availableW = groupW - 4;
      const tryRender = (parts) => parts.map(p => p.text).join(" · ");
      const glabel = el("text", { x: groupX + groupW / 2, y: topY - 6, "text-anchor": "middle", class: "value-label", "font-size": "10.5" });
      glabel.textContent = tryRender(labelParts.map(p => ({ text: p.fmt })));
      svg.appendChild(glabel);
      if (glabel.getComputedTextLength() > availableW) {
        if (labelParts.some(p => p.shortFmt !== null)) {
          glabel.textContent = tryRender(labelParts.map(p => ({ text: p.shortFmt !== null ? p.shortFmt : p.fmt })));
        }
        if (glabel.getComputedTextLength() > availableW) glabel.remove();
        else labels.push(glabel);
      } else {
        labels.push(glabel);
      }
    }
    const llabel = el("text", { x: groupX + groupW / 2, y: height - padBottom + 16, "text-anchor": "middle", class: "axis-label" });
    llabel.textContent = cat;
    svg.appendChild(llabel);
  });
  svg.appendChild(el("line", { x1: padSide, x2: width - padSide, y1: baseline, y2: baseline, class: "baseline" }));
  playEntrance(container, bars, labels);
}

function renderResumen(boxId, r) {
  const tiles = [
    { num: r.jugadores_sa.toLocaleString("es-AR"), label: "Jugadores SA en el top 1000" },
    { num: r.total_partidas.toLocaleString("es-AR"), label: "Partidas analizadas" },
    { num: r.total_mapas.toLocaleString("es-AR"), label: "Mapas jugados" },
    { num: r.filas_stats.toLocaleString("es-AR"), label: "Filas jugador/mapa" },
  ];
  const box = document.getElementById(boxId);
  tiles.forEach((t, i) => {
    const div = document.createElement("div");
    div.className = "stat reveal";
    div.style.transitionDelay = `${i * 0.06}s`;
    div.innerHTML = `<div class="num">${t.num}</div><div class="label">${t.label}</div>`;
    box.appendChild(div);
  });
}
renderResumen("stat-row-t8", DATA.resumen_t8);
renderResumen("stat-row-t9", DATA.resumen);

const countryColors = { BR: "var(--c-br)", AR: "var(--c-ar)", CL: "var(--c-cl)", UY: "var(--c-uy)", PY: "var(--c-py)", VE: "var(--c-ve)", PE: "var(--c-pe)", BO: "var(--c-bo)" };

/* ==================== TEMPORADA 8 (cerrada) ==================== */

const mapasT8Sorted = [...DATA.mapas_t8].sort((a, b) => a.diferencia_rondas - b.diferencia_rondas);
horizontalBars("chart-mapas-t8", mapasT8Sorted.map((d, i) => ({
  label: `de_${d.map}` + (i === 0 ? "  ★" : ""), value: d.diferencia_rondas, valueLabel: d.diferencia_rondas,
  color: `var(--m-de_${d.map}, var(--blue))`,
  tip: `<b>de_${d.map}</b>: diferencia de ${d.diferencia_rondas} rondas en promedio (${d.partidas} partidas, ${d.clasificacion})`
})), { max: Math.max(...mapasT8Sorted.map(d => d.diferencia_rondas)) * 1.15, ariaLabel: "Diferencia de rondas por mapa, Temporada 8" });

const seqColorsT8 = ["var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)"];
verticalBars("chart-hs-t8", DATA.hs_vs_winrate_t8.map((d, i) => ({
  label: d.rango, value: d.winrate, valueLabel: `${d.winrate}%`, color: seqColorsT8[i],
  tip: `<b>HS% ${d.rango}</b>: ${d.winrate}% win rate`
})), { max: 58, refLine: 50, ariaLabel: "Win rate por rango de headshot %, Temporada 8" });

const seq5ColorsT8 = ["var(--seq5-1)", "var(--seq5-2)", "var(--seq5-3)", "var(--seq5-4)", "var(--seq5-5)"];
const kdOrderT8 = ["< 0.8", "0.8-1.0", "1.0-1.3", "1.3+", "2.0+"];
const kdSortedT8 = kdOrderT8.map(r => DATA.kd_vs_winrate_t8.find(d => d.rango === r)).filter(Boolean);
verticalBars("chart-kd-t8", kdSortedT8.map((d, i) => ({
  label: d.rango, value: d.winrate, valueLabel: `${d.winrate}%`, color: seq5ColorsT8[i],
  tip: `<b>K/D ${d.rango}</b>: ${d.winrate}% win rate`
})), { max: 95, refLine: 50, ariaLabel: "Win rate por rango de K/D, Temporada 8" });

(function () {
  // "2.0+" queda afuera a propósito -- muy pocas filas (K/D so'lo con 0
  // muertes en toda la partida), el 50% que da no es un dato robusto (le
  // pasa lo mismo en las dos temporadas, ver kd_vs_winrate vs. _t8). El
  // mismo criterio que ya se usaba en el hallazgo original de la Temporada 9.
  const hs = DATA.hs_vs_winrate_t8;
  const kdLow = DATA.kd_vs_winrate_t8.find(d => d.rango === "< 0.8");
  const kdHigh = DATA.kd_vs_winrate_t8.find(d => d.rango === "1.3+");
  const hsSpread = (Math.max(...hs.map(d => d.winrate)) - Math.min(...hs.map(d => d.winrate))).toFixed(1);
  document.getElementById("finding-aim-t8").innerHTML =
    `Los grupos de headshot % ganan parecido (spread de apenas ${hsSpread} puntos) — <strong>el aim solo no explica las victorias</strong>. El K/D sí importa: por debajo de ${kdLow.rango} la win rate cae a ${kdLow.winrate}%, arriba de ${kdHigh.rango} sube a ${kdHigh.winrate}%.`;
})();

verticalBars("chart-desgaste-kd-t8", DATA.desgaste_t8.map(d => ({
  label: d.bucket, value: d.kd, valueLabel: d.kd, color: "var(--blue)",
  tip: `<b>${d.bucket}</b>: K/D promedio ${d.kd} (n=${d.n.toLocaleString("es-AR")})`
})), { ariaLabel: "K/D promedio por duración de partida, Temporada 8" });
verticalBars("chart-desgaste-hs-t8", DATA.desgaste_t8.map(d => ({
  label: d.bucket, value: d.hs, valueLabel: `${d.hs}%`, color: "var(--orange)",
  tip: `<b>${d.bucket}</b>: HS% promedio ${d.hs}% (n=${d.n.toLocaleString("es-AR")})`
})), { ariaLabel: "Headshot % promedio por duración de partida, Temporada 8" });

(function () {
  const d = DATA.desgaste_t8, first = d[0], last = d[d.length - 1];
  document.getElementById("finding-desgaste-t8").innerHTML =
    `El K/D promedio cae de <strong>${first.kd} a ${last.kd}</strong> y el headshot % de <strong>${first.hs}% a ${last.hs}%</strong> entre partidas cortas (${first.bucket}) y largas (${last.bucket}), sobre ${d.reduce((a, x) => a + x.n, 0).toLocaleString("es-AR")} filas jugador/partida.`;
})();

(function () {
  const byCountry = { AR: [], BR: [], CL: [] };
  DATA.mapa_pais_t8.forEach(d => { if (byCountry[d.pais]) byCountry[d.pais].push(d); });
  Object.keys(byCountry).forEach(pais => {
    const rows = [...byCountry[pais]].sort((a, b) => b.diferencia - a.diferencia);
    horizontalBars(`chart-mapapais-${pais.toLowerCase()}-t8`, rows.map(d => ({
      label: `de_${d.mapa}`,
      value: Math.abs(d.diferencia),
      valueLabel: (d.diferencia > 0 ? "+" : "") + d.diferencia,
      color: d.diferencia >= 0 ? "var(--diverge-pos)" : "var(--diverge-neg)",
      tip: `<b>de_${d.mapa}</b>: ${d.winrate_mapa}% win rate (promedio de ${pais}: ${d.winrate_base}%) — ${d.filas} filas`
    })), { rowH: 26, padLeft: 84, max: 8, ariaLabel: `Desviación por mapa, ${pais}, Temporada 8` });
  });
})();

(function () {
  const order = ["Madrugada (0-5h)", "Mañana (6-11h)", "Tarde (12-17h)", "Noche (18-23h)"];
  const rows = order.map(f => DATA.hora_pico_t8.find(d => d.franja === f)).filter(Boolean);
  verticalBars("chart-hora-t8", rows.map(d => ({
    label: d.franja.replace(/\s*\(.*\)/, ""), value: d.pct, valueLabel: `${d.pct}%`, color: "var(--blue)",
    tip: `<b>${d.franja}</b>: ${d.partidas.toLocaleString("es-AR")} partidas (${d.pct}%)`
  })), { ariaLabel: "Partidas por franja horaria, Temporada 8" });
  const noche = rows.find(d => d.franja.startsWith("Noche"));
  const madrugada = rows.find(d => d.franja.startsWith("Madrugada"));
  const nocheYMadrugada = (noche.pct + madrugada.pct).toFixed(1);
  document.getElementById("finding-hora-t8").innerHTML =
    `Casi la mitad de las partidas (${noche.pct}%) se juegan entre las 18h y las 23h. Sumando la madrugada (${madrugada.pct}%), el bloque noche + trasnoche se lleva ${nocheYMadrugada}% del total, sobre ${DATA.resumen_t8.total_partidas.toLocaleString("es-AR")} partidas de la temporada completa.`;
})();

/* ==================== TEMPORADA 9 (en curso) ==================== */
verticalBars("chart-paises", DATA.dominancia_por_pais.map(d => ({
  label: d.country, value: d.n, valueLabel: `${d.n}`, color: countryColors[d.country] || "var(--blue)",
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
  label: `de_${d.map}` + (i === 0 ? "  ★" : ""), value: d.diferencia_rondas, valueLabel: d.diferencia_rondas,
  color: `var(--m-de_${d.map}, var(--blue))`,
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

/* --- 07: mapa "propio" de cada país (diverging vs. el propio promedio) --- */
(function () {
  const byCountry = { AR: [], BR: [], CL: [] };
  DATA.mapa_pais.forEach(d => { if (byCountry[d.pais]) byCountry[d.pais].push(d); });
  Object.keys(byCountry).forEach(pais => {
    const rows = [...byCountry[pais]].sort((a, b) => b.diferencia - a.diferencia);
    horizontalBars(`chart-mapapais-${pais.toLowerCase()}`, rows.map(d => ({
      label: `de_${d.mapa}`,
      value: Math.abs(d.diferencia),
      valueLabel: (d.diferencia > 0 ? "+" : "") + d.diferencia,
      color: d.diferencia >= 0 ? "var(--diverge-pos)" : "var(--diverge-neg)",
      tip: `<b>de_${d.mapa}</b>: ${d.winrate_mapa}% win rate (promedio de ${pais}: ${d.winrate_base}%) — ${d.filas} filas`
    })), { rowH: 26, padLeft: 84, max: 8, ariaLabel: `Desviación por mapa, ${pais}` });
  });
})();

/* --- 08: ELO promedio por país --- */
verticalBars("chart-elo", DATA.elo_por_pais.map(d => ({
  label: d.pais, value: d.elo_promedio, valueLabel: Math.round(d.elo_promedio), color: countryColors[d.pais] || "var(--blue)",
  tip: `<b>${d.pais}</b>: ELO promedio ${Math.round(d.elo_promedio)} · K/D histórico ${d.kd_promedio_historico} · ${d.jugadores} jugadores`
})), { max: Math.max(...DATA.elo_por_pais.map(d => d.elo_promedio)) * 1.05, ariaLabel: "ELO promedio por país" });

/* --- 09: hora pico de juego --- */
(function () {
  const order = ["Madrugada (0-5h)", "Mañana (6-11h)", "Tarde (12-17h)", "Noche (18-23h)"];
  const rows = order.map(f => DATA.hora_pico.find(d => d.franja === f)).filter(Boolean);
  verticalBars("chart-hora", rows.map(d => ({
    label: d.franja.replace(/\s*\(.*\)/, ""), value: d.pct, valueLabel: `${d.pct}%`, color: "var(--blue)",
    tip: `<b>${d.franja}</b>: ${d.partidas.toLocaleString("es-AR")} partidas (${d.pct}%)`
  })), { ariaLabel: "Partidas por franja horaria" });
})();

/* --- 10: Temporada 8 vs Temporada 9 --- */
(function () {
  const tc = DATA.temporada_comparacion;
  if (!tc) return;
  const t8Name = `${tc.season8_label} (${tc.partidas_t8.toLocaleString("es-AR")} partidas)`;
  const t9Name = `${tc.season9_label} (${tc.partidas_t9.toLocaleString("es-AR")} partidas, en curso)`;
  const seriesFor = (metricKey, suffix, tipLabel) => [
    { name: t8Name, color: "var(--t8)", values: tc.desgaste[`t8_${metricKey}`],
      valueLabel: v => `${v}${suffix}`, shortValueLabel: v => `${v}`,
      tip: (cat, v) => `<b>${tc.season8_label}</b> — ${cat}: ${tipLabel} ${v}${suffix}` },
    { name: t9Name, color: "var(--blue)", values: tc.desgaste[`t9_${metricKey}`],
      valueLabel: v => `${v}${suffix}`, tip: (cat, v) => `<b>${tc.season9_label}</b> — ${cat}: ${tipLabel} ${v}${suffix}` },
  ];

  renderLegend("legend-desgaste", [
    { name: tc.season8_label, color: "var(--t8)" }, { name: tc.season9_label, color: "var(--blue)" },
  ]);
  groupedBars("chart-t89-kd", tc.desgaste.categorias, seriesFor("kd", "", "K/D promedio"),
    { ariaLabel: "K/D promedio por duración de partida, Temporada 8 vs 9" });

  renderLegend("legend-desgaste-hs", [
    { name: tc.season8_label, color: "var(--t8)" }, { name: tc.season9_label, color: "var(--blue)" },
  ]);
  groupedBars("chart-t89-hs", tc.desgaste.categorias, seriesFor("hs", "%", "HS% promedio"),
    { ariaLabel: "Headshot % promedio por duración de partida, Temporada 8 vs 9" });

  renderLegend("legend-hora", [
    { name: tc.season8_label, color: "var(--t8)" }, { name: tc.season9_label, color: "var(--blue)" },
  ]);
  groupedBars("chart-t89-hora", tc.hora_pico.categorias.map(c => c.replace(/\s*\(.*\)/, "")), [
    { name: t8Name, color: "var(--t8)", values: tc.hora_pico.t8_pct,
      valueLabel: v => `${v}%`, shortValueLabel: v => `${v}`, tip: (cat, v) => `<b>${tc.season8_label}</b> — ${cat}: ${v}% de las partidas` },
    { name: t9Name, color: "var(--blue)", values: tc.hora_pico.t9_pct,
      valueLabel: v => `${v}%`, tip: (cat, v) => `<b>${tc.season9_label}</b> — ${cat}: ${v}% de las partidas` },
  ], { ariaLabel: "Partidas por franja horaria, Temporada 8 vs 9" });
})();

/* ---------- aparición de secciones y stat tiles al hacer scroll ---------- */
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    entry.target.classList.add("show");
    revealObserver.unobserve(entry.target);
    // dispara las barras que estaban esperando a que este panel se viera (ver playEntrance)
    if (entry.target.__pendingBarAnims) {
      entry.target.__pendingBarAnims.forEach(run => run());
      entry.target.__pendingBarAnims = null;
    }
  });
}, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
document.querySelectorAll(".reveal").forEach(elm => revealObserver.observe(elm));

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
