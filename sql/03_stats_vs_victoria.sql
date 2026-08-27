-- ¿Las stats "de vidriera" (kills, headshot %) realmente predicen quién gana?
-- Técnica: CASE WHEN, subqueries, comparación de promedios entre grupos
--
-- Recortado a la Temporada 9 de FACEIT (desde el 5 de agosto de 2026 en
-- adelante) -- ver nota de "Alcance por temporada" en el README.

-- 3a. Promedio de kills/deaths/assists/HS% separando ganadores de
--     perdedores -- si la diferencia es chica, kills solo no explica todo.
SELECT
    CASE WHEN mps.team_won = 1 THEN 'Ganador' ELSE 'Perdedor' END AS resultado,
    COUNT(*)                                AS filas,
    ROUND(AVG(mps.kills), 2)                AS kills_promedio,
    ROUND(AVG(mps.deaths), 2)               AS deaths_promedio,
    ROUND(AVG(mps.assists), 2)              AS assists_promedio,
    ROUND(AVG(mps.headshots_percent), 1)    AS hs_percent_promedio,
    ROUND(AVG(mps.mvps), 2)                 AS mvps_promedio
FROM match_player_stats mps
JOIN matches m ON mps.match_id = m.match_id
WHERE m.finished_at >= strftime('%s', '2026-08-05')
GROUP BY mps.team_won;

-- 3b. Bucketizando por HS%: a medida que sube el HS%, ¿sube el win rate?
--     (si la curva es plana, el aim solo no gana partidas en este dataset)
SELECT
    CASE
        WHEN mps.headshots_percent < 30 THEN '< 30%'
        WHEN mps.headshots_percent < 45 THEN '30-45%'
        WHEN mps.headshots_percent < 60 THEN '45-60%'
        ELSE '60%+'
    END AS rango_hs,
    COUNT(*) AS filas,
    ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1) AS win_rate_percent
FROM match_player_stats mps
JOIN matches m ON mps.match_id = m.match_id
WHERE mps.headshots_percent IS NOT NULL AND m.finished_at >= strftime('%s', '2026-08-05')
GROUP BY rango_hs
ORDER BY MIN(mps.headshots_percent);

-- 3c. Lo mismo pero con K/D en vez de HS% -- ¿el que más fragea es el
--     que más gana, o hay techo?
SELECT
    CASE
        WHEN mps.deaths = 0 THEN '2.0+'
        WHEN mps.kills * 1.0 / mps.deaths < 0.8 THEN '< 0.8'
        WHEN mps.kills * 1.0 / mps.deaths < 1.0 THEN '0.8-1.0'
        WHEN mps.kills * 1.0 / mps.deaths < 1.3 THEN '1.0-1.3'
        ELSE '1.3+'
    END AS rango_kd,
    COUNT(*) AS filas,
    ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1) AS win_rate_percent
FROM match_player_stats mps
JOIN matches m ON mps.match_id = m.match_id
WHERE m.finished_at >= strftime('%s', '2026-08-05')
GROUP BY rango_kd
ORDER BY MIN(mps.kills * 1.0 / NULLIF(mps.deaths, 0));

-- Resultado (Temporada 9): los ganadores promedian 16.9 kills contra 13.8
-- de los perdedores -- ahí sí hay diferencia. Pero el HS% promedio es casi
-- igual (53.4% ganadores vs. 54.6% perdedores), y el grupo con MÁS
-- headshots (60%+) tiene la win rate más baja de los cuatro grupos (47.7%,
-- contra 52.0% del grupo 45-60%). El aim solo no explica las victorias.
