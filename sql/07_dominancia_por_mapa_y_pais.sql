-- ¿En qué mapa juega mejor cada país, respecto a SU PROPIO promedio?
-- Técnica: CTEs encadenadas, JOIN entre agregados, HAVING para descartar
-- muestra chica.
--
-- Recortado a la Temporada 9 de FACEIT (desde el 5 de agosto de 2026 en
-- adelante) -- ver nota de "Alcance por temporada" en el README.
--
-- Ojo: no comparamos win rate cruda entre países -- cada uno arranca de un
-- nivel promedio distinto (ver sql/08), así que "Brasil gana más en mapa X"
-- no dice nada por sí solo. La pregunta real es: en ese mapa, ¿un país
-- rinde mejor o peor que de costumbre? Por eso restamos el promedio propio
-- de cada país (su "baseline") al win rate de cada mapa.

WITH baseline_pais AS (
    -- win rate promedio de cada país, across todos los mapas, esta temporada
    SELECT p.country,
        ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1) AS winrate_base,
        COUNT(*) AS filas_base
    FROM match_player_stats mps
    JOIN players p ON mps.player_id = p.player_id
    JOIN matches m ON mps.match_id = m.match_id
    WHERE p.country IN ('br', 'ar', 'cl')   -- los únicos 3 con muestra decente por mapa
      AND m.finished_at >= strftime('%s', '2026-08-05')
    GROUP BY p.country
),
por_mapa AS (
    SELECT p.country, mps.map, COUNT(*) AS filas,
        ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1) AS winrate_mapa
    FROM match_player_stats mps
    JOIN players p ON mps.player_id = p.player_id
    JOIN matches m ON mps.match_id = m.match_id
    WHERE p.country IN ('br', 'ar', 'cl')
      AND m.finished_at >= strftime('%s', '2026-08-05')
    GROUP BY p.country, mps.map
    HAVING COUNT(*) >= 30    -- descarta combinaciones país/mapa con poca muestra
)
SELECT
    UPPER(pm.country)              AS pais,
    pm.map                         AS mapa,
    pm.filas,
    pm.winrate_mapa,
    b.winrate_base                 AS winrate_promedio_del_pais,
    ROUND(pm.winrate_mapa - b.winrate_base, 1) AS diferencia_vs_su_propio_promedio
FROM por_mapa pm
JOIN baseline_pais b ON pm.country = b.country
ORDER BY pm.country, diferencia_vs_su_propio_promedio DESC;

-- Resultado (Temporada 9): Chile domina de_nuke todavía más marcado que en
-- el histórico completo -- 63.9% vs 54.0% base, +9.9 puntos (36 partidas).
-- El mapa fuerte de Argentina pasó a ser de_cache con +8.6 (227 partidas);
-- el débil sigue siendo de_anubis (-6.4). Brasil sigue siendo el más
-- parejo de los tres: su mayor desvío esta temporada es -3.3 puntos, en
-- de_inferno.
