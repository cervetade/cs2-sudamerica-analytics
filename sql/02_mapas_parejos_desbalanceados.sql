-- ¿En qué mapa juega mejor/peor o más parejo la región?
-- Técnica: GROUP BY, HAVING, CASE WHEN
--
-- Recortado a la Temporada 9 de FACEIT (desde el 5 de agosto de 2026 en
-- adelante) -- ver nota de "Alcance por temporada" en el README.

-- 2a. Diferencia de rondas promedio por mapa -- cuanto más chica, más
--     pareja es la partida en promedio. Se filtra con HAVING para no
--     mostrar mapas con muestra chica (poco jugados = no representativo).
SELECT
    mm.map,
    COUNT(*)                        AS partidas_jugadas,
    ROUND(AVG(mm.rounds_total), 1)  AS rondas_promedio,
    ROUND(AVG(mm.round_diff), 2)    AS diferencia_de_rondas_promedio,
    CASE
        WHEN AVG(mm.round_diff) <= 5 THEN 'Parejo'
        WHEN AVG(mm.round_diff) <= 8 THEN 'Normal'
        ELSE 'Desbalanceado'
    END AS clasificacion
FROM match_maps mm
JOIN matches m ON mm.match_id = m.match_id
WHERE mm.round_diff IS NOT NULL AND m.finished_at >= strftime('%s', '2026-08-05')
GROUP BY mm.map
HAVING COUNT(*) >= 20
ORDER BY diferencia_de_rondas_promedio ASC;

-- 2b. Tasa de "overtime" (partidas que llegan a marcadores altos tipo
--     16-14, 19-17) por mapa -- otra forma de medir qué tan parejo es.
SELECT
    mm.map,
    COUNT(*) AS partidas,
    SUM(CASE WHEN mm.rounds_total > 24 THEN 1 ELSE 0 END) AS partidas_con_prorroga,
    ROUND(100.0 * SUM(CASE WHEN mm.rounds_total > 24 THEN 1 ELSE 0 END) / COUNT(*), 1) AS porcentaje_prorroga
FROM match_maps mm
JOIN matches m ON mm.match_id = m.match_id
WHERE mm.rounds_total IS NOT NULL AND m.finished_at >= strftime('%s', '2026-08-05')
GROUP BY mm.map
HAVING COUNT(*) >= 20
ORDER BY porcentaje_prorroga DESC;

-- Resultado (Temporada 9): de_cache sigue siendo el mapa más parejo de la
-- región (diferencia de rondas promedio 5.04, sobre 132 partidas), seguido
-- muy de cerca por de_anubis (5.07). de_inferno es el menos parejo (5.43),
-- aunque con la muestra más chica del pool (56 partidas).
