-- Comparación Temporada 8 vs Temporada 9: ¿cambió el mapa "más parejo" de
-- una temporada a la otra?
-- Técnica: CASE WHEN para bucketizar por temporada dentro de una sola query,
-- GROUP BY compuesto (temporada, mapa), HAVING para descartar muestra chica.
--
-- Requiere haber corrido fetch_season_history.py para la Temporada 8 (ver
-- README, sección "Analizar una temporada ya cerrada"). Si todavía no se
-- corrió, esta query va a mostrar datos únicamente de la Temporada 9.
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

-- Este es el primer caso de la comparación, a modo de prueba de concepto --
-- el mismo patrón (CASE WHEN por finished_at, GROUP BY temporada + lo que
-- corresponda) se puede repetir para comparar hora pico de juego (sql/09),
-- desgaste por duración (sql/06), aim vs win rate (sql/03) y mapa por país
-- (sql/07) entre las dos temporadas. Se arma cada una una vez que haya
-- datos reales de Temporada 8 para no escribir hallazgos con números
-- inventados.
