-- ¿Las stats "de vidriera" (kills, headshot %) realmente predicen quién gana?
-- Técnica: CASE WHEN, subqueries, comparación de promedios entre grupos

-- 3a. Promedio de kills/deaths/assists/HS% separando ganadores de
--     perdedores -- si la diferencia es chica, kills solo no explica todo.
SELECT
    CASE WHEN team_won = 1 THEN 'Ganador' ELSE 'Perdedor' END AS resultado,
    COUNT(*)                            AS filas,
    ROUND(AVG(kills), 2)                AS kills_promedio,
    ROUND(AVG(deaths), 2)               AS deaths_promedio,
    ROUND(AVG(assists), 2)              AS assists_promedio,
    ROUND(AVG(headshots_percent), 1)    AS hs_percent_promedio,
    ROUND(AVG(mvps), 2)                 AS mvps_promedio
FROM match_player_stats
GROUP BY team_won;

-- 3b. Bucketizando por HS%: a medida que sube el HS%, ¿sube el win rate?
--     (si la curva es plana, el aim solo no gana partidas en este dataset)
SELECT
    CASE
        WHEN headshots_percent < 30 THEN '< 30%'
        WHEN headshots_percent < 45 THEN '30-45%'
        WHEN headshots_percent < 60 THEN '45-60%'
        ELSE '60%+'
    END AS rango_hs,
    COUNT(*) AS filas,
    ROUND(100.0 * SUM(team_won) / COUNT(*), 1) AS win_rate_percent
FROM match_player_stats
WHERE headshots_percent IS NOT NULL
GROUP BY rango_hs
ORDER BY MIN(headshots_percent);

-- 3c. Lo mismo pero con K/D en vez de HS% -- ¿el que más fragea es el
--     que más gana, o hay techo?
SELECT
    CASE
        WHEN deaths = 0 THEN '2.0+'
        WHEN kills * 1.0 / deaths < 0.8 THEN '< 0.8'
        WHEN kills * 1.0 / deaths < 1.0 THEN '0.8-1.0'
        WHEN kills * 1.0 / deaths < 1.3 THEN '1.0-1.3'
        ELSE '1.3+'
    END AS rango_kd,
    COUNT(*) AS filas,
    ROUND(100.0 * SUM(team_won) / COUNT(*), 1) AS win_rate_percent
FROM match_player_stats
GROUP BY rango_kd
ORDER BY MIN(kills * 1.0 / NULLIF(deaths, 0));
