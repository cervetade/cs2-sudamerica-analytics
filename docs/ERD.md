# Modelo de datos — `cs2_sa.db`

Diagrama entidad-relación de la base SQLite armada en [`build_database.py`](../build_database.py) a partir de los CSVs crudos que baja [`fetch_faceit_data.py`](../fetch_faceit_data.py). GitHub renderiza el diagrama automáticamente (es Mermaid, no una imagen).

```mermaid
erDiagram
    PLAYERS ||--o{ MATCH_PLAYER_STATS : "jugó"
    PLAYERS ||--o{ MATCH_HISTORY : "registra"
    MATCHES ||--o{ MATCH_MAPS : "contiene"
    MATCHES ||--o{ MATCH_PLAYER_STATS : "tiene stats de"
    MATCHES ||--o{ MATCH_HISTORY : "aparece en"

    PLAYERS {
        text player_id PK
        text nickname
        text country "ISO alpha-2, minuscula"
        int is_sa_country "derivado: country en SA_COUNTRIES"
        int position "posicion en el ranking SA"
        int faceit_elo
        int game_skill_level
        int lifetime_matches
        real lifetime_win_rate_percent
        real lifetime_kd_ratio
        real lifetime_headshots_percent
    }

    MATCHES {
        text match_id PK
        text competition_name
        int best_of
        int started_at "unix timestamp"
        int finished_at "unix timestamp"
        real duration_minutes "finished_at - started_at"
        int has_valid_duration "derivado: 0 en partidas de torneo sin timestamps"
    }

    MATCH_MAPS {
        int id PK
        text match_id FK
        text map
        text score "ej. 16-14"
        int rounds_total
        int round_diff "derivado: |rondas_ganador - rondas_perdedor|"
        text winning_team_id
    }

    MATCH_PLAYER_STATS {
        int id PK
        text match_id FK
        text player_id FK
        text map
        text team_id
        int kills
        int deaths
        int assists
        real headshots_percent
        int mvps
        text winning_team_id
        int team_won "derivado: team_id == winning_team_id"
    }

    MATCH_HISTORY {
        int id PK
        text player_id FK
        text match_id FK
        text competition_name
        text game_mode
        int finished_at
    }
```

## Notas del modelo

- **`players`** son los 1000 jugadores del top del ranking SA. `is_sa_country` distingue jugadores realmente sudamericanos de gente que juega en los servidores SA pero es de otra región (ver aclaración en el [README](../README.md)).
- **`matches`** y **`match_maps`** están a nivel partida y a nivel mapa por separado porque una partida BO3 tiene hasta 3 mapas — `match_maps` es 1:N respecto a `matches`.
- **`match_player_stats`** es la tabla más granular (24.301 filas): una fila por jugador y por mapa. Acá vive casi todo el análisis de rendimiento.
- **`match_history`** solo registra qué partidas jugó cada jugador (útil para reconstruir el orden temporal); el detalle de cada partida vive en las otras tres tablas.
- El detalle completo (`match_maps`, `match_player_stats`) solo se bajó para el **top 150** jugadores por posición en el ranking, no para los 1000 — así el pipeline corre en un tiempo razonable contra los rate limits de la API. `players` y `match_history` sí cubren, cada una, su alcance completo (1000 y top 150 respectivamente).
