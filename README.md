# CS2 Sudamérica — Analytics

Radiografía del CS2 competitivo en Sudamérica: de dónde salen los mejores jugadores de la región, qué mapas son más parejos, si el aim solo alcanza para ganar, y si el desgaste de partidas largas se nota en los números. Todo con datos reales extraídos directamente de la API de FACEIT — no un dataset armado de Kaggle.

**[→ Ver el dashboard interactivo](./dashboard.html)** — los mismos hallazgos, pero navegables (hover para el detalle, tabla ordenable).

### Alcance por temporada

Los hallazgos que se calculan sobre **partidas** (2, 3, 4, 5, 6, 7 y 9) están recortados a la **Temporada 9** de FACEIT — desde el 5 de agosto de 2026 en adelante. Los que se calculan sobre el **ranking/ELO** (1 y 8) son una foto del estado actual, que ya incorpora el reset de temporada por sí solo.

La Data API v4 de FACEIT no expone un campo "temporada" en los endpoints de partidas o historial (sí existe para ligas y hubs), así que el recorte es una fecha fija (`SEASON_START_EPOCH` en `build_dashboard.py`, y `strftime('%s', '2026-08-05')` en cada `sql/*.sql` que lo necesita) que hay que actualizar a mano cuando arranque una temporada nueva — no se detecta solo.

## Hallazgos

### 1. Brasil concentra 7 de cada 10 jugadores top de la región

Sobre los jugadores sudamericanos que entran al top 1000 del ranking de FACEIT en la región SA, Brasil se lleva el 70%. Argentina es el único otro país con presencia real (21.6%); Colombia y Ecuador no meten a nadie en el top 1000.

![Dominancia por país](./charts/01_dominancia_por_pais.png)

### 2. El headshot % no predice quién gana

Los que ganan una partida tienen bastantes más kills que los que pierden (16.9 vs 13.8 en promedio) — hasta ahí, nada raro. Pero el % de headshots es prácticamente igual entre ganadores y perdedores (53.4% vs 54.6%), y el grupo con MÁS headshots (60%+) tiene la win rate más baja de los cuatro grupos (47.7%). El aim solo no gana partidas de CS2 en Sudamérica.

![Headshot % vs win rate](./charts/02_headshots_vs_winrate.png)

### 3. El desgaste por partidas largas es real

Comparando el rendimiento según la duración real de la partida: el K/D promedio cae de 1.18 en partidas cortas (≤30 min) a 1.01 en partidas de más de una hora, y el headshot % cae de 55.8% a 49.0%. La caída es consistente en ambas métricas — hay desgaste real, no es ruido.

![Desgaste por duración](./charts/03_desgaste_por_duracion.png)

### 4. Un nombre reconocible entre los "jugadores revelación"

Cruzando el ELO actual de cada jugador contra su rendimiento real en las partidas de la temporada, la lista la lidera **lukaazera** (AR): K/D 1.5 y un rendimiento muy por encima de lo que su ELO haría esperar. También aparece **coldzera** — el histórico jugador profesional brasileño — con el K/D real más alto de toda la lista (1.95, 100% de percentil de rendimiento), aunque esta temporada no encabeza el ranking por diferencia: su ELO ya es alto de base, así que tiene menos margen para "sorprender" contra lo esperado. Setup completo en [`sql/04_jugadores_revelacion.sql`](./sql/04_jugadores_revelacion.sql).

### 5. Rachas: 13 victorias seguidas

El jugador con la racha activa más larga del top de la región lleva 13 partidas ganadas consecutivas. Calculado con `LAG()` y el patrón "gaps and islands" — ver [`sql/05_rachas_y_momentum.sql`](./sql/05_rachas_y_momentum.sql).

### 6. `de_cache` es el mapa más parejo de la región

Entre los mapas con muestra suficiente (20+ partidas), `de_cache` tiene la menor diferencia de rondas promedio (5.04), es decir, las partidas ahí terminan más ajustadas que en el resto del pool competitivo.

### 7. El mapa "propio" de cada país no es el que se supone

En vez de comparar win rate cruda entre países (cada uno arranca de un nivel promedio distinto), se midió cuánto se desvía cada país de *su propio* promedio en cada mapa. La intuición decía Argentina-`de_nuke`, pero los datos dicen otra cosa: **Chile domina `de_nuke`** muy por encima de su costumbre (63.9% de win rate ahí vs. 54% de base, sobre 36 partidas). El mapa fuerte de Argentina es `de_cache` (+8.6 puntos sobre su propio promedio); el débil, `de_anubis` (-6.4). Brasil es el más parejo de los tres — su mayor desvío esta temporada es de apenas -3.3 puntos, en `de_inferno`. Setup en [`sql/07_dominancia_por_mapa_y_pais.sql`](./sql/07_dominancia_por_mapa_y_pais.sql).

### 8. Brasil no solo tiene más jugadores — también el ELO promedio más alto

628 jugadores con ELO promedio 2689. Argentina, con casi un tercio de esa cantidad (194), promedia 2661 — bastante cerca. Acá cantidad y calidad van en la misma dirección, no es solo volumen. Ver [`sql/08_elo_promedio_por_pais.sql`](./sql/08_elo_promedio_por_pais.sql).

### 9. Sudamérica juega de noche, fuerte

Agrupando las partidas por franja horaria (aprox. UTC-3): el 45.0% se juega entre las 18h y las 23h, y sumando la madrugada (0-5h, 27.7%) el bloque noche + trasnoche se lleva más del 72% del total. Entre las 6 y las 11 de la mañana el volumen se cae a un 1.6% — casi nadie juega competitivo a esa hora. Ver [`sql/09_hora_pico_de_juego.sql`](./sql/09_hora_pico_de_juego.sql).

### 10. ¿Casualidad de esta temporada, o patrón real? Comparación contra la Temporada 8

Los hallazgos 2 a 9 están recortados a la Temporada 9, que al momento de escribir esto lleva solo unas semanas. Para no quedarse con una sola tanda de datos, se hizo un backfill completo de la Temporada 8 (cerrada, 22 abr – 4 ago 2026, 9.494 partidas) y se compararon las métricas que sí son comparables entre temporadas (partidas — no ranking/ELO, que es una foto del estado actual):

- **El desgaste por partidas largas (hallazgo 3) se repite casi calcado**: el K/D promedio cae de 1.20 a 1.01 en la Temporada 8, y de 1.18 a 1.01 en la 9 — mismo tramo final, con jugadores y partidas totalmente distintos.
- **Los horarios pico (hallazgo 9) también se sostienen**: la franja noche (18-23h) se lleva 47.4% de las partidas en la Temporada 8 y 45.2% en la 9.
- **Chile repite a `de_nuke`** como su mapa fuerte en las dos temporadas (+6.2 puntos sobre su propio promedio en la 8, sobre 107 partidas; +9.9 en la 9). Brasil sigue siendo el más parejo entre mapas en ambas.
- **Lo que no se repite, honestamente**: el mapa fuerte de Argentina cambió de `de_inferno` (+4.3, Temporada 8) a `de_cache` (+8.6, Temporada 9) — no hay ahí una identidad de mapa sólida todavía, así que no se fuerza esa historia.

Ver [`sql/10_comparacion_temporadas.sql`](./sql/10_comparacion_temporadas.sql) y la sección "Analizar una temporada ya cerrada" más abajo para cómo se bajaron estos datos.

## Cómo se armó

Los datos se extrajeron con [`fetch_faceit_data.py`](./fetch_faceit_data.py) contra la [Data API v4 de FACEIT](https://docs.faceit.com/docs/data-api/), con una API key propia gratuita del [Developer Portal](https://developers.faceit.com/). El pipeline:

1. Baja el ranking completo (top 1000) de la región **SA** de CS2, paginado.
2. Para esos 1000, suma sus stats de por vida (partidas, win rate, K/D, HS%) y cuándo se creó su cuenta de FACEIT (`activated_at`).
3. Para el top 300 (los de mayor nivel), baja el historial de sus últimas 30 partidas.
4. Para cada partida única de ese grupo, baja el detalle por jugador/mapa y la duración real de la partida.

La API key nunca se hardcodea — se lee de la variable de entorno `FACEIT_API_KEY`.

### Aclaración sobre "antigüedad de cuenta"

La Data API v4 de FACEIT no expone la edad de los jugadores en ningún endpoint (se investigó explícitamente). Lo más cercano que existe es `activated_at` — cuándo se creó la cuenta de FACEIT, no la edad de la persona ni de cuánto juega CS2 en general. Se usa como proxy de antigüedad en la plataforma en [`sql/11_veteranos_vs_cuentas_nuevas.sql`](./sql/11_veteranos_vs_cuentas_nuevas.sql), con esa distinción siempre aclarada.

### Aclaración sobre "Sudamérica"

La región **SA** de FACEIT es la cola de *servidores*, no una garantía de nacionalidad — aparece gente de otras partes del mundo que juega ahí. Para el análisis regional se filtra por los países sudamericanos reales (`is_sa_country = 1` en la tabla `players`); el resto queda como dato de contexto.

### Notas de calidad de datos

- 8 partidas de torneos/ligas organizadas (no de la cola pública) no tienen duración real registrada por la API — quedan marcadas con `has_valid_duration = 0` y excluidas del análisis de desgaste.
- El detalle de partidas se bajó solo para el top 300 jugadores (no los 1000), para mantener la corrida del pipeline en un tiempo razonable. Chile, por ejemplo, solo mete ~12 de sus 47 jugadores dentro de ese top 300 — por eso sus muestras por mapa (hallazgo 7) son más chicas que las de Argentina o Brasil.

### Modelo de datos

Diagrama entidad-relación de las 5 tablas y cómo se conectan: [`docs/ERD.md`](./docs/ERD.md).

## Estructura del repo

```
cs2-sudamerica-analytics/
├── fetch_faceit_data.py       # extractor: FACEIT API -> CSVs crudos
├── build_database.py          # limpieza + carga a SQLite
├── fetch_season_history.py    # backfill de una temporada ya cerrada (ver abajo)
├── make_charts.py             # genera los gráficos de este README
├── dashboard.html             # dashboard interactivo (ver online o abrir local)
├── docs/
│   └── ERD.md                 # diagrama entidad-relación de la base
├── data/
│   ├── raw/                   # CSVs crudos (salida del extractor)
│   └── processed/cs2_sa.db    # base SQLite lista para consultar
├── sql/                       # una query por hallazgo, comentada
├── charts/                    # gráficos del README
└── .github/workflows/
    ├── refresh.yml             # actualización automática semanal (ver abajo)
    └── season-backfill.yml     # backfill manual de una temporada cerrada (ver abajo)
```

## Cómo correrlo

```bash
pip install -r requirements.txt

# 1. Extraer datos (necesita tu propia API key de FACEIT)
export FACEIT_API_KEY="tu-key-aca"
python fetch_faceit_data.py

# 2. Limpiar y cargar a SQLite
python build_database.py

# 3. Regenerar los gráficos
python make_charts.py

# 4. Regenerar el dashboard interactivo
python build_dashboard.py

# 5. Explorar las queries
sqlite3 data/processed/cs2_sa.db < sql/01_dominancia_por_pais.sql
```

`dashboard.html` (e `index.html`, copia idéntica) es autocontenido — HTML + CSS + JS + datos en un solo archivo, sin dependencias externas.

### Desplegarlo en vivo (Vercel)

1. Entrá a [vercel.com](https://vercel.com) y logueate con GitHub.
2. "Add New..." → "Project" → elegí `cs2-sudamerica-analytics`.
3. Framework preset: **Other** (es HTML estático, no necesita build command).
4. "Deploy". Vercel sirve `index.html` en la raíz del dominio que te da (`cs2-sudamerica-analytics.vercel.app` o el que elijas).

Cada vez que actualices el dashboard (`python build_dashboard.py`) y hagas push a `main`, Vercel lo redespliega solo.

### Se mantiene actualizado solo (GitHub Actions)

El proyecto corre su propio pipeline una vez por semana sin intervención manual, vía [`.github/workflows/refresh.yml`](./.github/workflows/refresh.yml):

1. Cada domingo (o manualmente desde la pestaña "Actions" del repo), un runner de GitHub instala las dependencias y corre `fetch_faceit_data.py` → `build_database.py` → `build_dashboard.py` en secuencia.
2. Si algo cambió (nuevos datos de la temporada), commitea `data/processed/cs2_sa.db`, `dashboard.html` e `index.html` de vuelta a `main` con un usuario bot.
3. Ese push dispara el redeploy automático de Vercel — el dashboard queda al día sin que nadie tenga que tocar nada.

Para activarlo en tu propio fork: `Settings → Secrets and variables → Actions → New repository secret`, nombre `FACEIT_API_KEY`, valor tu API key. El workflow ya está armado para leerla desde ahí — nunca queda expuesta en el código ni en los logs. También podés dispararlo a mano desde la pestaña "Actions" ("Run workflow") si no querés esperar al domingo.

### Analizar una temporada ya cerrada

`fetch_faceit_data.py` baja "las últimas N partidas" de cada jugador — perfecto para una temporada en curso, pero inútil para una que ya terminó (si un jugador jugó mucho desde entonces, sus últimas partidas ya no llegan hasta esa temporada vieja). Para eso existe [`fetch_season_history.py`](./fetch_season_history.py): usa los parámetros `from`/`to` del endpoint de historial de FACEIT para traer **todas** las partidas de un jugador dentro de una ventana de fechas fija, sin importar cuánto jugó después.

```bash
export FACEIT_API_KEY="tu-key-aca"
python fetch_season_history.py --season 8 --from 2026-04-22 --to 2026-08-04
python build_database.py
```

Guarda todo en los mismos CSVs de `data/raw/` — no hace falta tocar `build_database.py`, ni crear tablas nuevas: las partidas de temporadas distintas ya se distinguen solas por `finished_at`. Tiene un tope de 60 partidas por jugador dentro de la ventana (`MAX_MATCHES_PER_PLAYER`, ajustable) — de sobra para una muestra sólida a lo largo de una temporada, sin arriesgar corridas de muchísimas horas.

Es resumible **de verdad**: corriendo dentro de GitHub Actions, el script commitea y pushea `data/raw/*.csv` solo cada pocos minutos (no espera a un paso del workflow para guardar nada). Si el job se corta por el límite de 6h de GitHub, lo bajado hasta ese momento ya quedó en GitHub — volver a disparar el mismo workflow con los mismos parámetros retoma justo donde quedó, sin repetir nada. (La primera versión no hacía esto — el commit vivía en un paso aparte que nunca llegaba a correr si el job se cancelaba por timeout, así que la primera corrida real se comió las 5h30 completas y no pusheó nada. Ya está corregido.)

Para no tener que dejarlo corriendo en tu compu, hay un workflow manual — [`.github/workflows/season-backfill.yml`](./.github/workflows/season-backfill.yml) — que lo corre en GitHub Actions: pestaña "Actions" → "Backfill de temporada cerrada" → "Run workflow", completás temporada/fecha inicio/fecha fin, y listo (reusa el mismo secreto `FACEIT_API_KEY`). A diferencia del refresh semanal, este nunca se dispara solo — una temporada cerrada no cambia más, así que no tiene sentido correrlo seguido. Si una corrida no alcanza a terminar en un solo disparo, simplemente volvé a apretar "Run workflow" con los mismos datos las veces que haga falta.

Con los datos de una temporada cerrada ya en la base, [`sql/10_comparacion_temporadas.sql`](./sql/10_comparacion_temporadas.sql) arranca la comparación entre temporadas (el ranking/ELO no es comparable así, porque `players` es una sola foto del estado actual — ver el comentario en ese archivo).

## Stack

Python (extracción y limpieza) · SQLite · SQL (análisis) · Matplotlib (gráficos) · JavaScript/SVG vanilla (dashboard interactivo) · [FACEIT Data API v4](https://docs.faceit.com/docs/data-api/)
