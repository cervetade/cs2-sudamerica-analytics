-- ¿En qué mapa juega mejor/peor o más parejo la región?
-- Técnica: GROUP BY, HAVING, CASE WHEN

-- 2a. Diferencia de rondas promedio por mapa -- cuanto más chica, más
--     pareja es la partida en promedio. Se filtra con HAVING para no
--     mostrar mapas con muestra chica (poco jugados = no representativo).
SELECT
    map,
    COUNT(*)                     AS partidas_jugadas,
    ROUND(AVG(rounds_total), 1)  AS rondas_promedio,
    ROUND(AVG(round_diff), 2)    AS diferencia_de_rondas_promedio,
    CASE
        WHEN AVG(round_diff) <= 5 THEN 'Parejo'
        WHEN AVG(round_diff) <= 8 THEN 'Normal'
        ELSE 'Desbalanceado'
    END AS clasificacion
FROM match_maps
WHERE round_diff IS NOT NULL
GROUP BY map
HAVING COUNT(*) >= 20
ORDER BY diferencia_de_rondas_promedio ASC;

-- 2b. Tasa de "overtime" (partidas que llegan a marcadores altos tipo
--     16-14, 19-17) por mapa -- otra forma de medir qué tan parejo es.
SELECT
    map,
    COUNT(*) AS partidas,
    SUM(CASE WHEN rounds_total > 24 THEN 1 ELSE 0 END) AS partidas_con_prorroga,
    ROUND(100.0 * SUM(CASE WHEN rounds_total > 24 THEN 1 ELSE 0 END) / COUNT(*), 1) AS porcentaje_prorroga
FROM match_maps
WHERE rounds_total IS NOT NULL
GROUP BY map
HAVING COUNT(*) >= 20
ORDER BY porcentaje_prorroga DESC;
