"""
Limpia los CSVs crudos de data/raw/ y arma una base SQLite prolija en
data/processed/cs2_sa.db, lista para las queries de analisis.

Corre local, no necesita internet ni la API key -- solo lee lo que ya bajamos.

    python build_database.py
"""

import csv
import sqlite3
from pathlib import Path

RAW_DIR = Path(__file__).parent / "data" / "raw"
DB_PATH = Path(__file__).parent / "data" / "processed" / "cs2_sa.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Paises reales de Sudamerica (ISO 3166-1 alpha-2, en minuscula como los
# devuelve la API). Todo lo que no esta en esta lista queda marcado como
# is_sa_country = 0 -- gente que juega en los servidores de la region SA
# pero no es de Sudamerica (ver nota en el README).
SA_COUNTRIES = {"ar", "br", "cl", "uy", "py", "pe", "co", "ec", "bo", "ve"}


def read_csv(name):
    path = RAW_DIR / name
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(v):
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def to_float(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_round_diff(score_str):
    if not score_str:
        return None
    for sep in ("/", "-", ":"):
        if sep in score_str:
            parts = [p.strip() for p in score_str.split(sep)]
            try:
                nums = [int(p) for p in parts]
                return abs(nums[0] - nums[1])
            except (ValueError, IndexError):
                return None
    return None


def main():
    print("Leyendo CSVs crudos...")
    players = read_csv("players.csv")
    matches = read_csv("matches.csv")
    match_maps = read_csv("match_maps.csv")
    match_player_stats = read_csv("match_player_stats.csv")
    match_history = read_csv("match_history.csv")

    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    cur.executescript(
        """
        CREATE TABLE players (
            player_id TEXT PRIMARY KEY,
            nickname TEXT,
            country TEXT,
            is_sa_country INTEGER,
            position INTEGER,
            faceit_elo INTEGER,
            game_skill_level INTEGER,
            lifetime_matches INTEGER,
            lifetime_win_rate_percent REAL,
            lifetime_kd_ratio REAL,
            lifetime_headshots_percent REAL,
            activated_at TEXT
        );

        CREATE TABLE matches (
            match_id TEXT PRIMARY KEY,
            competition_name TEXT,
            best_of INTEGER,
            started_at INTEGER,
            finished_at INTEGER,
            duration_minutes REAL,
            has_valid_duration INTEGER
        );

        CREATE TABLE match_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id TEXT REFERENCES matches(match_id),
            map TEXT,
            score TEXT,
            rounds_total INTEGER,
            round_diff INTEGER,
            winning_team_id TEXT
        );

        CREATE TABLE match_player_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id TEXT REFERENCES matches(match_id),
            map TEXT,
            team_id TEXT,
            player_id TEXT REFERENCES players(player_id),
            nickname TEXT,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            headshots_percent REAL,
            mvps INTEGER,
            winning_team_id TEXT,
            team_won INTEGER
        );

        CREATE TABLE match_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id TEXT REFERENCES players(player_id),
            match_id TEXT REFERENCES matches(match_id),
            competition_name TEXT,
            game_mode TEXT,
            finished_at INTEGER
        );

        CREATE INDEX idx_mps_match ON match_player_stats(match_id);
        CREATE INDEX idx_mps_player ON match_player_stats(player_id);
        CREATE INDEX idx_maps_match ON match_maps(match_id);
        CREATE INDEX idx_hist_player ON match_history(player_id);
        CREATE INDEX idx_hist_match ON match_history(match_id);
        """
    )

    # ------------------------------------------------------------------
    # Carga + limpieza
    # ------------------------------------------------------------------
    print(f"Cargando {len(players)} jugadores...")
    for p in players:
        country = (p["country"] or "").lower()
        cur.execute(
            """INSERT INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                p["player_id"],
                p["nickname"],
                country,
                1 if country in SA_COUNTRIES else 0,
                to_int(p["position"]),
                to_int(p["faceit_elo"]),
                to_int(p["game_skill_level"]),
                to_int(p["lifetime_matches"]),
                to_float(p["lifetime_win_rate_percent"]),
                to_float(p["lifetime_kd_ratio"]),
                to_float(p["lifetime_headshots_percent"]),
                # activated_at es columna nueva -- players.csv de corridas
                # viejas (antes de este cambio) no la va a tener; con .get()
                # no rompe, solo queda NULL para esas filas.
                p.get("activated_at") or None,
            ),
        )

    print(f"Cargando {len(matches)} partidas...")
    for m in matches:
        dur = to_float(m["duration_minutes"])
        cur.execute(
            """INSERT INTO matches VALUES (?,?,?,?,?,?,?)""",
            (
                m["match_id"],
                m["competition_name"],
                to_int(m["best_of"]),
                to_int(m["started_at"]),
                to_int(m["finished_at"]),
                dur,
                1 if dur is not None and dur > 0 else 0,
            ),
        )

    print(f"Cargando {len(match_maps)} mapas...")
    for mm in match_maps:
        cur.execute(
            """INSERT INTO match_maps (match_id, map, score, rounds_total, round_diff, winning_team_id)
               VALUES (?,?,?,?,?,?)""",
            (
                mm["match_id"],
                mm["map"],
                mm["score"],
                to_int(mm["rounds_total"]),
                parse_round_diff(mm["score"]),
                mm["winning_team_id"],
            ),
        )

    print(f"Cargando {len(match_player_stats)} filas de stats por jugador/mapa...")
    for ps in match_player_stats:
        cur.execute(
            """INSERT INTO match_player_stats
               (match_id, map, team_id, player_id, nickname, kills, deaths, assists,
                headshots_percent, mvps, winning_team_id, team_won)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                ps["match_id"],
                ps["map"],
                ps["team_id"],
                ps["player_id"],
                ps["nickname"],
                to_int(ps["kills"]),
                to_int(ps["deaths"]),
                to_int(ps["assists"]),
                to_float(ps["headshots_percent"]),
                to_int(ps["mvps"]),
                ps["winning_team_id"],
                to_int(ps["team_won"]),
            ),
        )

    print(f"Cargando {len(match_history)} filas de historial...")
    for h in match_history:
        cur.execute(
            """INSERT INTO match_history (player_id, match_id, competition_name, game_mode, finished_at)
               VALUES (?,?,?,?,?)""",
            (
                h["player_id"],
                h["match_id"],
                h["competition_name"],
                h["game_mode"],
                to_int(h["finished_at"]),
            ),
        )

    conn.commit()

    # ------------------------------------------------------------------
    # Verificacion rapida
    # ------------------------------------------------------------------
    print("\n== Verificacion ==")
    for table in ["players", "matches", "match_maps", "match_player_stats", "match_history"]:
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} filas")

    sa_count = cur.execute("SELECT COUNT(*) FROM players WHERE is_sa_country = 1").fetchone()[0]
    print(f"  players con is_sa_country=1: {sa_count}")

    valid_dur = cur.execute("SELECT COUNT(*) FROM matches WHERE has_valid_duration = 1").fetchone()[0]
    print(f"  matches con duracion valida: {valid_dur}")

    conn.close()
    print(f"\nListo: {DB_PATH}")


if __name__ == "__main__":
    main()
