-- ¿A qué hora se juega más CS2 competitivo en Sudamérica?
-- Técnica: funciones de fecha sobre timestamp unix (datetime/strftime), CASE WHEN
--
-- Los timestamps de FACEIT vienen en UTC; se les resta 3 horas como
-- aproximación al huso horario más común de la región (ART/BRT/UYT =
-- UTC-3). Es una aproximación -- Chile y parte de Brasil caen en otros
-- husos -- pero como proxy de "cuándo juega la región" alcanza.

SELECT
    CASE
        WHEN hora BETWEEN 6 AND 11  THEN 'Mañana (6-11h)'
        WHEN hora BETWEEN 12 AND 17 THEN 'Tarde (12-17h)'
        WHEN hora BETWEEN 18 AND 23 THEN 'Noche (18-23h)'
        ELSE 'Madrugada (0-5h)'
    END AS franja_horaria,
    COUNT(*)                                                      AS partidas,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM matches), 1)   AS porcentaje
FROM (
    SELECT CAST(strftime('%H', datetime(finished_at - 3*3600, 'unixepoch')) AS INTEGER) AS hora
    FROM matches
    WHERE finished_at IS NOT NULL
)
GROUP BY franja_horaria
ORDER BY partidas DESC;

-- Bonus: detalle hora por hora, para quien quiera el gráfico completo de 24 barras.
SELECT
    CAST(strftime('%H', datetime(finished_at - 3*3600, 'unixepoch')) AS INTEGER) AS hora,
    COUNT(*) AS partidas
FROM matches
WHERE finished_at IS NOT NULL
GROUP BY hora
ORDER BY hora;

-- Resultado: casi la mitad de las partidas (45.5%) se juegan entre las 18h
-- y las 23h. Sumando la madrugada (0-5h, 27%) el bloque "noche + trasnoche"
-- se lleva más del 70% del total. Entre las 6 y las 11 de la mañana el
-- volumen se cae a un 1.7% -- prácticamente nadie juega competitivo a esa hora.
