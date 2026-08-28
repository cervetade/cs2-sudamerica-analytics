"""
Backfill de una temporada YA CERRADA de FACEIT, usando el rango de fechas
(from/to) del endpoint /players/{id}/history -- a diferencia de
fetch_faceit_data.py (que baja "las ultimas N partidas" de la temporada en
curso), esto trae TODAS las partidas de un jugador dentro de una ventana de
fechas fija, sin importar cuanto jugo despues. Es lo que permite analizar
una temporada cerrada con la muestra completa, no solo un recorte reciente.

Pensado para correr UNA SOLA VEZ por temporada cerrada -- no forma parte del
refresh semanal (.github/workflows/refresh.yml): una temporada cerrada no
cambia mas, asi que no tiene sentido re-bajarla cada semana. Para eso existe
el workflow separado ".github/workflows/season-backfill.yml" (manual, sin
cron).

Reutiliza el mismo top N de jugadores que ya esta en data/raw/players.csv
(no vuelve a pedir el ranking completo), y evita re-bajar el detalle de
partidas que ya esten en data/raw/matches.csv -- por ejemplo, las que el
pipeline de la temporada en curso ya haya bajado si la fecha coincide.

Guarda todo en los MISMOS CSVs de data/raw/ (matches.csv, match_maps.csv,
match_player_stats.csv, match_history.csv) -- build_database.py NO necesita
ningun cambio: simplemente va a cargar mas filas la proxima vez que corra.
Como las tablas de partidas ya se distinguen por finished_at (no hay un
"season_id" en el modelo), las queries de temporada 8 son solo un WHERE
finished_at BETWEEN ... AND ... -- igual que ya se hizo para temporada 9.

COMO CORRERLO (en tu compu, o via el workflow de GitHub Actions
"Backfill de temporada cerrada"):

    export FACEIT_API_KEY="tu-key-aca"
    python fetch_season_history.py --season 8 --from 2026-04-22 --to 2026-08-04

Si se corta a mitad de camino, corre de nuevo el mismo comando: los
match_id que ya estan en matches.csv no se vuelven a pedir.
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
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

# Cuantos de los jugadores del ranking (data/raw/players.csv, ya ordenado
# por posicion) usamos como "spine" para bajar historial. No hace falta
# volver a pedir el ranking -- ya lo tenemos.
DEEP_DIVE_N = 300

# Techo de partidas por jugador dentro de la ventana de la temporada, para
# acotar el tiempo total de la corrida (el endpoint permite pedir mucho mas
# via paginacion, pero un techo generoso alcanza para "toda la temporada de
# un jugador activo" sin arriesgar corridas de muchisimas horas). Subilo si
# despues de una corrida ves que algun jugador lo esta tocando seguido.
MAX_MATCHES_PER_PLAYER = 150

HISTORY_PAGE_SIZE = 100  # maximo permitido por la API para /history
REQUEST_DELAY_SECONDS = 0.6

RAW_DIR = Path(__file__).parent / "data" / "raw"
CHECKPOINT_EVERY = 200

# ----------------------------------------------------------------------------
# HELPERS (mismo patron de reintento que fetch_faceit_data.py)
# ----------------------------------------------------------------------------


def api_get(path, params=None, max_retries=5):
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


def get_player_history_page(player_id, ts_from, ts_to, offset):
    return api_get(
        f"/players/{player_id}/history",
        params={"game": GAME_ID, "from": ts_from, "to": ts_to, "offset": offset, "limit": HISTORY_PAGE_SIZE},
    )


def get_match_stats(match_id):
    return api_get(f"/matches/{match_id}/stats")


def get_match_details(match_id):
    return api_get(f"/matches/{match_id}")


def date_to_epoch(date_str):
    """'2026-04-22' -> unixepoch de esa fecha 00:00 UTC."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def read_csv_rows(name):
    path = RAW_DIR / name
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fieldnames):
    path = RAW_DIR / name
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  guardado: {path} ({len(rows)} filas)")


def parse_rounds_total(score_str):
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


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season", required=True, help='Numero/label de la temporada, solo para los logs (ej. "8")')
    parser.add_argument("--from", dest="from_date", required=True, help="Inicio de la temporada, YYYY-MM-DD (UTC)")
    parser.add_argument("--to", dest="to_date", required=True, help="Fin de la temporada, YYYY-MM-DD (UTC)")
    args = parser.parse_args()

    ts_from = date_to_epoch(args.from_date)
    ts_to = date_to_epoch(args.to_date)
    print(f"== Backfill Temporada {args.season}: {args.from_date} -> {args.to_date} (UTC) ==")

    players = read_csv_rows("players.csv")
    if not players:
        sys.exit("No encontre data/raw/players.csv -- corre primero fetch_faceit_data.py (aunque sea una vez) para tener el ranking base.")
    players.sort(key=lambda p: int(p["position"] or 999999))
    deep_dive_players = players[:DEEP_DIVE_N]
    print(f"Usando el top {len(deep_dive_players)} de data/raw/players.csv como spine (ya bajado antes, no se vuelve a pedir el ranking).")

    # Lo que ya tenemos, para no re-pedir nada.
    existing_matches = read_csv_rows("matches.csv")
    existing_match_ids = {m["match_id"] for m in existing_matches}
    existing_maps = read_csv_rows("match_maps.csv")
    existing_stats = read_csv_rows("match_player_stats.csv")
    existing_history = read_csv_rows("match_history.csv")
    existing_history_keys = {(h["player_id"], h["match_id"]) for h in existing_history}
    print(f"Ya en data/raw/: {len(existing_matches)} partidas, {len(existing_history)} filas de historial.")

    # Cuantas filas de historial ya tiene cada jugador DENTRO de esta ventana
    # de fechas (match_history.csv tambien puede tener filas del pipeline de
    # la temporada en curso -- esas quedan afuera del rango y no cuentan
    # aca). Sirve para que MAX_MATCHES_PER_PLAYER sea un tope total real, no
    # "tope por corrida" -- si se re-corre el script dos veces no se termina
    # bajando el doble por jugador.
    already_have_by_player = {}
    for h in existing_history:
        finished = h.get("finished_at")
        try:
            finished = int(finished)
        except (TypeError, ValueError):
            continue
        if ts_from <= finished <= ts_to:
            already_have_by_player[h["player_id"]] = already_have_by_player.get(h["player_id"], 0) + 1

    # --------------------------------------------------------------------
    # Paso 1: historial de cada jugador, paginando por fecha con from/to.
    # --------------------------------------------------------------------
    print(f"\n== Paso 1: historial por jugador, ventana {args.from_date} a {args.to_date} ==")
    new_history_rows = []
    match_ids_to_fetch = set()

    for i, p in enumerate(deep_dive_players, 1):
        pid = p["player_id"]
        offset = 0
        player_matches = already_have_by_player.get(pid, 0)
        while player_matches < MAX_MATCHES_PER_PLAYER:
            page = get_player_history_page(pid, ts_from, ts_to, offset)
            if not page:
                break
            items = page.get("items", [])
            if not items:
                break
            for m in items:
                if player_matches >= MAX_MATCHES_PER_PLAYER:
                    break  # respeta el tope aunque la pagina traiga mas
                match_id = m.get("match_id")
                if not match_id:
                    continue
                key = (pid, match_id)
                if key in existing_history_keys:
                    continue
                existing_history_keys.add(key)
                new_history_rows.append(
                    {
                        "player_id": pid,
                        "match_id": match_id,
                        "competition_name": m.get("competition_name"),
                        "game_mode": m.get("game_mode"),
                        "finished_at": m.get("finished_at"),
                    }
                )
                if match_id not in existing_match_ids:
                    match_ids_to_fetch.add(match_id)
                player_matches += 1
            if len(items) < HISTORY_PAGE_SIZE or offset + HISTORY_PAGE_SIZE >= 1000:
                break  # ultima pagina, o llegamos al techo que permite la API (offset <= 1000)
            offset += HISTORY_PAGE_SIZE
        if i % 25 == 0 or i == len(deep_dive_players):
            print(f"  [{i}/{len(deep_dive_players)}] {p['nickname']} ({p['country']}) -- {player_matches} partidas en la ventana")

    print(f"\nHistorial nuevo: {len(new_history_rows)} filas. Partidas unicas nuevas a bajar detalle: {len(match_ids_to_fetch)}")

    # --------------------------------------------------------------------
    # Paso 2: detalle de cada partida nueva (igual que fetch_faceit_data.py).
    # --------------------------------------------------------------------
    print("\n== Paso 2: detalle de cada partida nueva (stats + duracion real) ==")
    new_matches_rows = []
    new_maps_rows = []
    new_stats_rows = []
    match_ids_sorted = sorted(match_ids_to_fetch)

    def save_progress():
        write_csv("matches.csv", existing_matches + new_matches_rows,
                   ["match_id", "competition_name", "best_of", "started_at", "finished_at", "duration_minutes"])
        write_csv("match_maps.csv", existing_maps + new_maps_rows,
                   ["match_id", "map", "score", "rounds_total", "winning_team_id"])
        write_csv("match_player_stats.csv", existing_stats + new_stats_rows,
                   ["match_id", "map", "team_id", "player_id", "nickname", "kills", "deaths", "assists",
                    "headshots_percent", "mvps", "winning_team_id", "team_won"])
        write_csv("match_history.csv", existing_history + new_history_rows,
                   ["player_id", "match_id", "competition_name", "game_mode", "finished_at"])

    try:
        for i, match_id in enumerate(match_ids_sorted, 1):
            print(f"  [{i}/{len(match_ids_sorted)}] {match_id}")
            stats = get_match_stats(match_id)
            details = get_match_details(match_id)

            if details:
                started_at = details.get("started_at")
                finished_at = details.get("finished_at")
                duration_minutes = None
                if started_at and finished_at:
                    duration_minutes = round((finished_at - started_at) / 60, 1)
                new_matches_rows.append(
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

                new_maps_rows.append(
                    {
                        "match_id": match_id,
                        "map": map_name,
                        "score": score_str,
                        "rounds_total": parse_rounds_total(score_str),
                        "winning_team_id": winning_team_id,
                    }
                )

                for team in round_data.get("teams", []):
                    team_id = team.get("team_id")
                    for player in team.get("players", []):
                        ps = player.get("player_stats", {})
                        new_stats_rows.append(
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
                save_progress()
    except KeyboardInterrupt:
        print("\n[interrumpido manualmente] guardando lo que se llego a bajar...")
    except Exception as exc:
        print(f"\n[error inesperado: {exc}] guardando lo que se llego a bajar...")

    save_progress()
    print(f"\nListo. Temporada {args.season} backfileada -- corre build_database.py para recargar la base con estos datos.")


if __name__ == "__main__":
    main()
