-- Jugadores "revelación": ELO relativamente bajo, pero rendimiento real
-- (en las partidas que sí bajamos) por encima de lo esperado para su nivel.
-- Técnica: CTE, funciones de ventana (PERCENT_RANK, NTILE)
--
-- Recortado a la Temporada 9 de FACEIT (desde el 5 de agosto de 2026 en
-- adelante) -- ver nota de "Alcance por temporada" en el README.

WITH rendimiento_real AS (
    -- Promedio real de K/D y win rate de cada jugador en las partidas
    -- que tenemos detalladas (no su stat de "por vida" declarado por FACEIT),
    -- jugadas dentro de la temporada actual.
    SELECT
        mps.player_id,
        COUNT(*)                                            AS mapas_jugados,
        ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2)  AS kd_real,
        ROUND(100.0 * SUM(mps.team_won) / COUNT(*), 1)          AS winrate_real
    FROM match_player_stats mps
    JOIN matches m ON mps.match_id = m.match_id
    WHERE m.finished_at >= strftime('%s', '2026-08-05')
    GROUP BY mps.player_id
    HAVING COUNT(*) >= 5   -- que tenga muestra minima, si no el promedio no dice nada
),
comparacion AS (
    SELECT
        p.nickname,
        p.country,
        p.faceit_elo,
        r.mapas_jugados,
        r.kd_real,
        r.winrate_real,
        -- percentil de ELO dentro de los jugadores sudamericanos (0 = mas bajo, 1 = mas alto)
        PERCENT_RANK() OVER (ORDER BY p.faceit_elo)  AS percentil_elo,
        -- percentil de rendimiento real
        PERCENT_RANK() OVER (ORDER BY r.kd_real)     AS percentil_kd_real
    FROM players p
    JOIN rendimiento_real r ON p.player_id = r.player_id
    WHERE p.is_sa_country = 1
)
SELECT
    nickname,
    country,
    faceit_elo,
    mapas_jugados,
    kd_real,
    winrate_real,
    ROUND(percentil_elo * 100, 0)      AS percentil_elo_pct,
    ROUND(percentil_kd_real * 100, 0)  AS percentil_kd_real_pct,
    ROUND((percentil_kd_real - percentil_elo) * 100, 0) AS diferencia_sobre_lo_esperado
FROM comparacion
ORDER BY diferencia_sobre_lo_esperado DESC
LIMIT 15;

-- Resultado (Temporada 9): la lista la lidera lukaazera (AR), con un K/D de
-- 1.5 en sus 5 partidas de la temporada y un percentil de rendimiento muy
-- por encima de su ELO (diferencia +85). coldzera sigue apareciendo en la
-- lista (puesto 6, K/D real 1.95 -- el más alto de todos, 100% de percentil
-- de rendimiento), aunque esta temporada no encabeza el ranking por
-- diferencia: su ELO ya es alto de base, así que el "salto sobre lo
-- esperado" es menor que el de jugadores que arrancan de un ELO más bajo.
