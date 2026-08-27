-- ¿El desgaste mental por partidas largas afecta el rendimiento?
-- Técnica: JOIN, CASE WHEN para bucketizar, comparación de promedios
--
-- Nota: win_rate_percent va a dar ~50% en todos los buckets casi siempre --
-- es matemático (en cada partida hay exactamente un ganador y un perdedor,
-- promediado sobre todos los jugadores siempre tiende a 50%). No es un bug,
-- la señal real de desgaste hay que buscarla en kd_promedio y
-- hs_percent_promedio, que sí pueden bajar con partidas mas largas.

SELECT
    CASE
        WHEN m.duration_minutes <= 30 THEN '<= 30 min'
        WHEN m.duration_minutes <= 45 THEN '30-45 min'
        WHEN m.duration_minutes <= 60 THEN '45-60 min'
        ELSE '60+ min'
    END AS duracion_de_la_partida,
    COUNT(*)                                      AS filas,
    ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2) AS kd_promedio,
    ROUND(AVG(mps.headshots_percent), 1)           AS hs_percent_promedio,
    ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1) AS win_rate_percent
FROM match_player_stats mps
JOIN matches m ON mps.match_id = m.match_id
WHERE m.has_valid_duration = 1   -- excluye las partidas de torneo sin duracion real (ver README)
GROUP BY duracion_de_la_partida
ORDER BY MIN(m.duration_minutes);
