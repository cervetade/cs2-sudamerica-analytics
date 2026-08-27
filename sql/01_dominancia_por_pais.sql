-- ¿Quién domina el CS2 competitivo de Sudamérica?
-- Técnica: GROUP BY, funciones de agregación, RANK()

-- 1a. Cuántos jugadores tiene cada país en el top 1000 de la región,
--     y qué ELO/nivel promedio manejan.
SELECT
    country,
    COUNT(*)                          AS jugadores_en_top_1000,
    ROUND(AVG(faceit_elo), 0)         AS elo_promedio,
    ROUND(AVG(game_skill_level), 1)   AS nivel_promedio,
    ROUND(AVG(lifetime_kd_ratio), 2)  AS kd_de_por_vida_promedio,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM players WHERE is_sa_country = 1), 1) AS porcentaje_del_top
FROM players
WHERE is_sa_country = 1
GROUP BY country
ORDER BY jugadores_en_top_1000 DESC;

-- 1b. "Profundidad" de cada país: no solo cuántos entran al top 1000,
--     sino cuántos son de ELITE real (ELO > 2800, un umbral alto).
SELECT
    country,
    COUNT(*) AS jugadores_elite,
    ROUND(AVG(faceit_elo), 0) AS elo_promedio_elite
FROM players
WHERE is_sa_country = 1 AND faceit_elo > 2800
GROUP BY country
ORDER BY jugadores_elite DESC;

-- 1c. Ranking de países por ELO promedio, con RANK() para desempatar
--     prolijo (dos países con el mismo promedio comparten posición).
SELECT
    country,
    ROUND(AVG(faceit_elo), 0) AS elo_promedio,
    RANK() OVER (ORDER BY AVG(faceit_elo) DESC) AS ranking_pais
FROM players
WHERE is_sa_country = 1
GROUP BY country;
