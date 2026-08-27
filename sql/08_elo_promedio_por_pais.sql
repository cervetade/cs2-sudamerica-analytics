-- ¿Brasil domina solo en cantidad de jugadores, o también en nivel promedio?
-- Técnica: GROUP BY, AVG, HAVING para descartar países con muestra chica.

SELECT
    UPPER(country)                                 AS pais,
    COUNT(*)                                       AS jugadores,
    ROUND(AVG(faceit_elo), 0)                      AS elo_promedio,
    ROUND(AVG(lifetime_kd_ratio), 2)                AS kd_promedio_historico,
    ROUND(AVG(lifetime_win_rate_percent), 1)        AS winrate_promedio_historico
FROM players
WHERE is_sa_country = 1
GROUP BY country
HAVING COUNT(*) >= 10   -- con menos de 10 jugadores el promedio no dice mucho
ORDER BY elo_promedio DESC;

-- Resultado: Brasil no solo tiene 3x más jugadores que Argentina en el top
-- 1000 (ver sql/01) -- también tiene el ELO promedio más alto (2689 vs
-- 2661). La diferencia es chica (28 puntos), pero está en la misma
-- dirección: cantidad y calidad van juntas acá, no es solo volumen.
