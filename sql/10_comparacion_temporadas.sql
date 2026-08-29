-- Comparación Temporada 8 vs Temporada 9: ¿cambió el mapa "más parejo" de
-- una temporada a la otra?
-- Técnica: CASE WHEN para bucketizar por temporada dentro de una sola query,
-- GROUP BY compuesto (temporada, mapa), HAVING para descartar muestra chica.
--
-- Requiere haber corrido fetch_season_history.py para la Temporada 8 (ver
-- README, sección "Analizar una temporada ya cerrada"). Si todavía no se
-- corrió, esta query va a mostrar datos únicamente de la Temporada 9.
-- (Ya se corrió: la Temporada 8 completa -- 22 abr a 4 ago 2026, 9.494
-- partidas -- está en la base desde el backfill.)
--
-- Nota importante: esto compara métricas que salen de PARTIDAS (mapas,
-- horarios, desgaste, aim vs win rate) -- el ranking/ELO (hallazgos 1 y 8)
-- NO es comparable entre temporadas con el modelo de datos actual, porque
-- la tabla `players` es una sola foto del estado ACTUAL, no una versión
-- guardada por temporada. Para comparar ELO habría que haber bajado el
-- ranking completo mientras la Temporada 8 todavía estaba activa -- algo
-- que no se hizo en su momento.

SELECT
    CASE
        WHEN m.finished_at BETWEEN strftime('%s', '2026-04-22') AND strftime('%s', '2026-08-04') THEN 'Temporada 8'
        WHEN m.finished_at >= strftime('%s', '2026-08-05') THEN 'Temporada 9'
    END AS temporada,
    mm.map AS mapa,
    COUNT(*) AS partidas,
    ROUND(AVG(mm.round_diff), 2) AS diferencia_rondas_promedio
FROM match_maps mm
JOIN matches m ON mm.match_id = m.match_id
WHERE mm.round_diff IS NOT NULL
GROUP BY temporada, mapa
HAVING temporada IS NOT NULL AND COUNT(*) >= 20
ORDER BY temporada, diferencia_rondas_promedio ASC;

-- Resultado: el mapa "más parejo" cambia de de_mirage (Temporada 8, diff.
-- 5.11) a de_cache (Temporada 9, diff. 5.04) -- pero las diferencias son
-- chicas: todos los mapas rondan entre 5.0 y 5.9 rondas de diferencia
-- promedio en las dos temporadas, ningún mapa se destaca como mucho más
-- aplastante que otro. No es un hallazgo fuerte, a diferencia de los dos
-- de abajo.

-- ------------------------------------------------------------------------
-- Desgaste por duración de partida (mismo patrón que sql/06), Temporada 8
-- vs Temporada 9.
-- ------------------------------------------------------------------------
SELECT
    CASE
        WHEN m.finished_at BETWEEN strftime('%s', '2026-04-22') AND strftime('%s', '2026-08-04') THEN 'Temporada 8'
        WHEN m.finished_at >= strftime('%s', '2026-08-05') THEN 'Temporada 9'
    END AS temporada,
    CASE
        WHEN m.duration_minutes <= 30 THEN '<= 30 min'
        WHEN m.duration_minutes <= 45 THEN '30-45 min'
        WHEN m.duration_minutes <= 60 THEN '45-60 min'
        ELSE '60+ min'
    END AS duracion_de_la_partida,
    ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2) AS kd_promedio,
    ROUND(AVG(mps.headshots_percent), 1) AS hs_percent_promedio
FROM match_player_stats mps
JOIN matches m ON mps.match_id = m.match_id
WHERE m.has_valid_duration = 1
GROUP BY temporada, duracion_de_la_partida
HAVING temporada IS NOT NULL
ORDER BY temporada, MIN(m.duration_minutes);

-- Resultado: se repite casi calcado. El K/D promedio cae de 1.20 (<=30 min)
-- a 1.01 (60+ min) en la Temporada 8, y de 1.18 a 1.01 en la 9 -- mismo
-- tramo final, con jugadores y partidas totalmente distintos. El HS%
-- promedio hace lo mismo: 54.8% -> 49.4% (T8) y 55.8% -> 49.0% (T9).

-- ------------------------------------------------------------------------
-- Hora pico de juego (mismo patrón que sql/09), Temporada 8 vs Temporada 9.
-- ------------------------------------------------------------------------
SELECT
    CASE
        WHEN finished_at BETWEEN strftime('%s', '2026-04-22') AND strftime('%s', '2026-08-04') THEN 'Temporada 8'
        WHEN finished_at >= strftime('%s', '2026-08-05') THEN 'Temporada 9'
    END AS temporada,
    CASE
        WHEN hora BETWEEN 6 AND 11  THEN 'Mañana (6-11h)'
        WHEN hora BETWEEN 12 AND 17 THEN 'Tarde (12-17h)'
        WHEN hora BETWEEN 18 AND 23 THEN 'Noche (18-23h)'
        ELSE 'Madrugada (0-5h)'
    END AS franja_horaria,
    COUNT(*) AS partidas
FROM (
    -- ojo: el filtro de fecha va ACÁ, dentro de la subquery sobre matches
    -- directamente -- nada de volver a hacer JOIN con matches por
    -- finished_at para "recuperar" la fecha: finished_at no es única (dos
    -- partidas pueden cerrar en el mismo segundo), así que ese join infla
    -- filas. Mismo patrón que sql/09, solo agregando el CASE de temporada.
    SELECT finished_at, CAST(strftime('%H', datetime(finished_at - 3*3600, 'unixepoch')) AS INTEGER) AS hora
    FROM matches WHERE finished_at IS NOT NULL
)
GROUP BY temporada, franja_horaria
HAVING temporada IS NOT NULL
ORDER BY temporada, partidas DESC;

-- Resultado: también se sostiene. La franja noche (18-23h) se lleva 47.4%
-- de las partidas en la Temporada 8 y 45.2% en la 9 (porcentajes calculados
-- sobre el total de cada temporada) -- la forma general de "se juega de
-- noche" no es un capricho de esta temporada puntual.

-- Sobre el mapa "propio" de cada país (sql/07) -- no repetido acá como
-- query porque ya está en sql/07 con el mismo patrón, cambiando el rango de
-- finished_at -- Chile repite a de_nuke como su mapa fuerte en las dos
-- temporadas (+6.2 en la 8 sobre 107 partidas, +9.9 en la 9), Brasil sigue
-- siendo el más parejo en ambas, y el mapa fuerte de Argentina SÍ cambia
-- (de_inferno en la 8, de_cache en la 9) -- ese último no se fuerza como
-- hallazgo porque no hay ahí un patrón sólido todavía.
