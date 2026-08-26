# CS2 Sudamérica — Analytics

Análisis de datos del competitivo de Counter-Strike 2 en Sudamérica, usando datos reales extraídos de la API de FACEIT (no un dataset pre-armado de Kaggle). El objetivo es responder preguntas concretas sobre el nivel competitivo de la región con SQL, y contarlo como una historia con datos, no solo como una colección de queries.

## Cómo se armó

Los datos se extrajeron con [`fetch_faceit_data.py`](./fetch_faceit_data.py) contra la [Data API v4 de FACEIT](https://docs.faceit.com/docs/data-api/), pidiendo una API key propia (gratuita) desde el [Developer Portal](https://developers.faceit.com/). El script:

1. Baja el ranking completo (top 1000) de la región **SA** de CS2, paginado.
2. Para esos 1000, suma sus stats de por vida (partidas, win rate, K/D, HS%).
3. Para el top 150 (los de mayor nivel), baja el historial de sus últimas 30 partidas.
4. Para cada partida única de ese grupo, baja el detalle por jugador/mapa (kills, deaths, assists, HS%, MVPs, quién ganó) y la duración real de la partida.

La API key nunca se hardcodea — se lee de la variable de entorno `FACEIT_API_KEY`.

### Aclaración importante sobre "Sudamérica"

La región **SA** de FACEIT es la cola de *servidores*, no una garantía de nacionalidad — aparece gente de otras partes del mundo que juega ahí. Para el análisis regional se filtra por los países sudamericanos reales (AR, BR, CL, UY, PY, PE, CO, EC, BO, VE); el resto queda como dato de contexto, no como parte de la historia principal.

## Datos actuales (`data/raw/`)

| Archivo | Filas | Contenido |
|---|---|---|
| `players.csv` | 1000 | Ranking, país, ELO, nivel, stats de por vida |
| `match_history.csv` | 4500 | Qué partidas jugó cada uno de los top 150 |
| `match_player_stats.csv` | ~24.300 | Detalle por jugador/mapa: kills, deaths, assists, HS%, MVPs, resultado |
| `matches.csv` | 2402 | Duración real de cada partida (minutos) |
| `match_maps.csv` | 2430 | Marcador y rondas totales por mapa |

Todo validado: sin nulos, `team_won` balanceado, duraciones y marcadores coherentes con partidas reales de CS2.

## Hallazgo ya visible

Filtrando por países sudamericanos reales, la distribución del top 1000 de la región está muy concentrada: Brasil ~63%, Argentina ~19%, Chile ~5%, Uruguay ~2%, y Colombia/Ecuador sin ningún jugador en el top 1000.

## Roadmap

- [x] Conseguir API key y armar el extractor
- [x] Validar los datos crudos (jugadores, partidas, duración, marcador)
- [ ] Limpiar `players.csv`: separar países sudamericanos reales del resto
- [ ] Revisar partidas con duración 0 (posible dato corrupto/forfeit)
- [ ] Consolidar todo en una base SQLite (`data/processed/cs2_sa.db`)
- [ ] Diseñar el schema (ERD simple) y las relaciones entre tablas
- [ ] Escribir las queries SQL organizadas por hallazgo, en `/sql`:
  - ¿Quién domina Sudamérica por país? (ranking, ELO promedio, profundidad)
  - ¿Qué mapa es más parejo o más desbalanceado?
  - ¿Las stats "de vidriera" (kills, HS%) predicen la victoria?
  - Jugadores "revelación": ELO bajo, rendimiento por encima de lo esperado
  - Racha actual y forma reciente (`LAG()`, promedio móvil)
  - Desgaste: partidas de más de 1 hora vs caída de rendimiento
- [ ] 2-3 gráficos de apoyo para los hallazgos más visuales
- [ ] Reescribir este README como la nota final, con los hallazgos arriba de todo
- [ ] (Opcional) Push a un repo público de GitHub

## Stack

Python (extracción) · SQLite (almacenamiento) · SQL (análisis) · FACEIT Data API v4
