"""
FACEIT Data API v4 -- extractor de ranking + partidas de CS2 para Sudamerica.

COMO CORRERLO (en TU compu, en una terminal normal, no dentro de Cowork):

    1) pip install requests
    2) Windows (PowerShell):  $env:FACEIT_API_KEY="tu-api-key-aca"
       Windows (cmd):         set FACEIT_API_KEY=tu-api-key-aca
    3) python fetch_faceit_data.py

La API key NUNCA se hardcodea en este archivo -- se lee de la variable de entorno
FACEIT_API_KEY. Asi este script se puede subir a GitHub sin exponer nada.

ENFOQUE (v2): en vez de filtrar el ranking por pais (que devolvia resultados raros
-- algunos paises con 0 jugadores), ahora bajamos el TOP_N_TOTAL del ranking
general de la region SA (paginado), y de ahi:
  - a TODOS les sacamos su ficha + stats de por vida -> tabla "players" grande,
    buena para comparar paises, ELO, niveles, etc.
  - solo a los primeros DEEP_DIVE_N (los de mas nivel) les bajamos historial de
    partidas y detalle de cada partida -> mucho mas pesado, por eso se limita.

ENFOQUE (v3): para cada partida del deep dive ahora pegamos 2 llamadas en vez
de 1 (/matches/{id}/stats + /matches/{id}) para tener tambien la duracion real
(started_at/finished_at) y el marcador de cada mapa (para calcular rondas
totales y diferencia de rondas) -- esto es para analizar desgaste/duracion y
partidas parejas vs paliza. Como pega el doble de llamadas, esta fase tarda
mas o menos el doble que en la v2.

Por defecto corre en TEST_MODE (rapido, pocos datos) para validar que todo
funciona antes de ir a un volumen grande.
"""

import os
import sys
import time
import csv
import json
from pathlib import Path

import requests

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

API_KEY = os.environ.get("FACEIT_API_KEY")
if not API_KEY:
    sys.exit(
        "Falta la API key. Seteala como variable de entorno FACEIT_API_KEY antes de correr esto."
    )

BASE_URL = "https://open.faceit.com/data/v4"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

GAME_ID = "cs2"
REGION = "SA"

TEST_MODE = False  # True = corrida chica para probar rapido

if TEST_MODE:
    TOP_N_TOTAL = 40       # cuantos jugadores totales del ranking SA bajamos
    DEEP_DIVE_N = 15       # de esos, a cuantos les bajamos historial + detalle
    MATCHES_PER_PLAYER = 10
else:
    TOP_N_TOTAL = 1000     # ranking completo -> tabla grande para comparar paises
    DEEP_DIVE_N = 150      # subset con detalle de partidas (lo pesado)
    MATCHES_PER_PLAYER = 30

RANKING_PAGE_SIZE = 100  # tamaño de pagina al paginar el ranking (offset)

OUTPUT_DIR = Path(__file__).parent / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY_SECONDS = 0.6  # para no pegarle demasiado rapido a la API

# ----------------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------------


def api_get(path, params=None, max_retries=5):
    """GET contra la Data API con reintento ante rate limiting (429) y ante
    caidas de red (timeouts, conexion resetada, etc.) -- para una corrida larga
    no queremos que un hipo de internet tire abajo horas de progreso."""
    url = f"{BASE_URL}{path}"
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params or {}, timeout=20)
        except requests.exceptions.RequestException as exc:
            wait = min(2 ** attempt, 30)
            print(f"  [red] {exc.__class__.__name__}, espero {wait}s y reintento... ({path})")
            time.sleep(wait)
            continue
        if resp.status_code == 429:
            wait = min(2 ** attempt, 30)
            print(f"  [429 rate limit] esperando {wait}s y reintentando... ({path})")
            time.sleep(wait)
            continue
        if resp.status_code >= 500:
            wait = min(2 ** attempt, 30)
            print(f"  [{resp.status_code} server] esperando {wait}s y reintentando... ({path})")
            time.sleep(wait)
            continue
        if resp.status_code >= 400:
            print(f"  [ERROR {resp.status_code}] {url} params={params}")
            print(f"  body: {resp.text[:300]}")
            return None
        time.sleep(REQUEST_DELAY_SECONDS)
        return resp.json()
    print(f"  [FALLO tras {max_retries} intentos] {url}")
    return None


def get_rankings_page(limit, offset):
    return api_get(
        f"/rankings/games/{GAME_ID}/regions/{REGION}",
        params={"limit": limit, "offset": offset},
    )


def get_full_rankings(total_n, page_size=RANKING_PAGE_SIZE):
    """Pagina el ranking general de la region (sin filtrar por pais) hasta
    juntar total_n items o hasta que la API deje de devolver mas."""
    items = []
    offset = 0
    while len(items) < total_n:
        remaining = total_n - len(items)
        limit = min(page_size, remaining)
        data = get_rankings_page(limit, offset)
        if not data:
            break
        page_items = data.get("items", [])
        if not page_items:
            break
        items.extend(page_items)
        offset += len(page_items)
        print(f"  ranking: {len(items)}/{total_n} bajados...")
        if len(page_items) < limit:
            break  # ya no hay mas paginas
    return items


def get_player_stats(player_id):
    return api_get(f"/players/{player_id}/stats/{GAME_ID}")


def get_player_history(player_id, limit):
    return api_get(
        f"/players/{player_id}/history",
        params={"game": GAME_ID, "limit": limit},
    )


def get_match_stats(match_id):
    return api_get(f"/matches/{match_id}/stats")


def get_match_details(match_id):
    """Detalle general de la partida (no las stats por jugador) -- de aca
    sacamos started_at / finished_at para calcular la duracion real."""
    return api_get(f"/matches/{match_id}")


def write_csv(filename, rows):
    if not rows:
        print(f"  (sin filas para {filename}, no se escribe)")
        return
    path = OUTPUT_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  guardado: {path} ({len(rows)} filas)")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------


def main():
    match_ids_to_fetch = set()
    history_rows = []

    print(f"== Paso 1: ranking completo de la region {REGION} (top {TOP_N_TOTAL}) ==")
    raw_items = get_full_rankings(TOP_N_TOTAL)
    players_rows = []
    for item in raw_items:
        pid = item.get("player_id")
        if not pid:
            continue
        players_rows.append(
            {
                "player_id": pid,
                "nickname": item.get("nickname"),
                "country": item.get("country"),
                "position": item.get("position"),
                "faceit_elo": item.get("faceit_elo"),
                "game_skill_level": item.get("game_skill_level"),
            }
        )

    print(f"\nTotal jugadores en el ranking: {len(players_rows)}")
    from collections import Counter

    print("Distribucion por pais:", dict(Counter(p["country"] for p in players_rows)))

    print(f"\n== Paso 1.5: stats de por vida de cada jugador (los {len(players_rows)}) ==")
    for i, p in enumerate(players_rows, 1):
        if i % 50 == 0 or i == len(players_rows):
            print(f"  [{i}/{len(players_rows)}]")
        stats = get_player_stats(p["player_id"])
        lifetime = (stats or {}).get("lifetime", {})
        p["lifetime_matches"] = lifetime.get("Matches")
        p["lifetime_win_rate_percent"] = lifetime.get("Win Rate %")
        p["lifetime_kd_ratio"] = lifetime.get("Average K/D Ratio")
        p["lifetime_headshots_percent"] = lifetime.get("Average Headshots %")

    write_csv("players.csv", players_rows)

    # Subset "deep dive": solo a los mejores rankeados les bajamos partidas.
    # players_rows ya viene ordenado por posicion (el ranking lo devuelve asi).
    deep_dive_players = players_rows[:DEEP_DIVE_N]
    print(
        f"\n== Paso 2: historial de partidas -- solo el top {len(deep_dive_players)} "
        f"(ultimas {MATCHES_PER_PLAYER} c/u) =="
    )
    for i, p in enumerate(deep_dive_players, 1):
        pid = p["player_id"]
        print(f"  [{i}/{len(deep_dive_players)}] {p['nickname']} ({p['country']})")
        hist = get_player_history(pid, MATCHES_PER_PLAYER)
        if not hist:
            continue
        for m in hist.get("items", []):
            match_id = m.get("match_id")
            if not match_id:
                continue
            match_ids_to_fetch.add(match_id)
            history_rows.append(
                {
                    "player_id": pid,
                    "match_id": match_id,
                    "competition_name": m.get("competition_name"),
                    "game_mode": m.get("game_mode"),
                    "finished_at": m.get("finished_at"),
                }
            )

    print(f"\nTotal partidas unicas a bajar detalle: {len(match_ids_to_fetch)}")
    write_csv("match_history.csv", history_rows)

    print("\n== Paso 3: detalle de cada partida (stats + duracion real) ==")
    print("(esta es la fase larga -- si se corta, lo ya bajado queda guardado igual)")
    print(
        "(ahora pega 2 llamadas por partida en vez de 1 -- stats + detalle -- "
        "va a tardar mas o menos el doble que antes)"
    )
    match_player_stats_rows = []
    matches_rows = []
    match_maps_rows = []
    match_ids_sorted = sorted(match_ids_to_fetch)
    CHECKPOINT_EVERY = 200
    debug_printed = False  # para loguear el shape crudo de la primera partida

    def parse_rounds_total(score_str):
        """'13 / 9' o '13-9' -> 22 (total de rondas). Devuelve None si no se puede."""
        if not score_str:
            return None
        for sep in ("/", "-", ":"):
            if sep in score_str:
                parts = [p.strip() for p in score_str.split(sep)]
                try:
                    return sum(int(p) for p in parts)
                except ValueError:
                    return None
        return None

    try:
        for i, match_id in enumerate(match_ids_sorted, 1):
            print(f"  [{i}/{len(match_ids_sorted)}] {match_id}")

            stats = get_match_stats(match_id)
            details = get_match_details(match_id)

            if not debug_printed:
                # Diagnostico de una sola vez: si algun nombre de campo no es el
                # que supusimos, esto lo muestra ya en la consola de la primera
                # partida, para poder corregirlo sin esperar a que termine todo.
                print("  [debug] keys de /matches/{id}:", list((details or {}).keys()))
                if stats and stats.get("rounds"):
                    print(
                        "  [debug] keys de round_stats:",
                        list(stats["rounds"][0].get("round_stats", {}).keys()),
                    )
                debug_printed = True

            if details:
                started_at = details.get("started_at")
                finished_at = details.get("finished_at")
                duration_minutes = None
                if started_at and finished_at:
                    duration_minutes = round((finished_at - started_at) / 60, 1)
                matches_rows.append(
                    {
                        "match_id": match_id,
                        "competition_name": details.get("competition_name"),
                        "best_of": details.get("best_of"),
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "duration_minutes": duration_minutes,
                    }
                )

            if not stats:
                continue
            for round_data in stats.get("rounds", []):
                round_stats = round_data.get("round_stats", {})
                map_name = round_stats.get("Map")
                winning_team_id = round_stats.get("Winner")
                score_str = round_stats.get("Score")
                rounds_total = parse_rounds_total(score_str)

                match_maps_rows.append(
                    {
                        "match_id": match_id,
                        "map": map_name,
                        "score": score_str,
                        "rounds_total": rounds_total,
                        "winning_team_id": winning_team_id,
                    }
                )

                for team in round_data.get("teams", []):
                    team_id = team.get("team_id")
                    for player in team.get("players", []):
                        ps = player.get("player_stats", {})
                        match_player_stats_rows.append(
                            {
                                "match_id": match_id,
                                "map": map_name,
                                "team_id": team_id,
                                "player_id": player.get("player_id"),
                                "nickname": player.get("nickname"),
                                "kills": ps.get("Kills"),
                                "deaths": ps.get("Deaths"),
                                "assists": ps.get("Assists"),
                                "headshots_percent": ps.get("Headshots %"),
                                "mvps": ps.get("MVPs"),
                                "winning_team_id": winning_team_id,
                                "team_won": int(team_id == winning_team_id),
                            }
                        )
            if i % CHECKPOINT_EVERY == 0:
                print(f"  -- checkpoint: guardando progreso parcial ({i} partidas procesadas) --")
                write_csv("match_player_stats.csv", match_player_stats_rows)
                write_csv("matches.csv", matches_rows)
                write_csv("match_maps.csv", match_maps_rows)
    except KeyboardInterrupt:
        print("\n[interrumpido manualmente] guardando lo que se llegó a bajar...")
    except Exception as exc:
        print(f"\n[error inesperado: {exc}] guardando lo que se llegó a bajar...")

    write_csv("match_player_stats.csv", match_player_stats_rows)
    write_csv("matches.csv", matches_rows)
    write_csv("match_maps.csv", match_maps_rows)

    print("\nListo. Revisa la carpeta data/raw/ junto a este script.")
    print("Archivos generados: players.csv, match_history.csv, match_player_stats.csv,")
    print("matches.csv (duracion real) y match_maps.csv (marcador/rondas por mapa).")
    print(
        "Si algo se cortó antes de terminar todas las partidas, podés volver a correr "
        "el script -- los match_id ya vistos no se vuelven a pedir en la misma corrida, "
        "pero si querés completar los que faltaron avisame y te dejo una version que "
        "retoma desde donde quedó."
    )


if __name__ == "__main__":
    main()