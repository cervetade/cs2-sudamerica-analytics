-- Racha actual de cada jugador y forma reciente vs su historial.
-- Técnica: LAG(), promedio móvil con ventana, patrón "gaps and islands"
-- (agrupar resultados consecutivos iguales para calcular la racha).
--
-- Recortado a la Temporada 9 de FACEIT (desde el 5 de agosto de 2026 en
-- adelante) -- ver nota de "Alcance por temporada" en el README. Nota
-- aparte: se ordena por matches.finished_at -- como es a nivel de partida
-- (no de mapa), los mapas de una misma partida BO3 comparten fecha; para
-- una racha 100% precisa dentro de un BO3 haría falta el orden real del
-- mapa, que la API no expone. Para el resto (la gran mayoria, BO1) es exacto.

WITH partidas_ordenadas AS (
    SELECT
        mps.player_id,
        p.nickname,
        mps.match_id,
        m.finished_at,
        mps.team_won,
        mps.kills,
        mps.deaths,
        -- marca un "1" cada vez que el resultado cambia respecto a la
        -- partida anterior del mismo jugador (o es la primera partida)
        CASE
            WHEN mps.team_won != LAG(mps.team_won) OVER (
                PARTITION BY mps.player_id ORDER BY m.finished_at
            ) OR LAG(mps.team_won) OVER (
                PARTITION BY mps.player_id ORDER BY m.finished_at
            ) IS NULL
            THEN 1 ELSE 0
        END AS empieza_racha_nueva
    FROM match_player_stats mps
    JOIN matches m ON mps.match_id = m.match_id
    JOIN players p ON mps.player_id = p.player_id
    WHERE p.is_sa_country = 1 AND m.finished_at >= strftime('%s', '2026-08-05')
),
con_grupo_de_racha AS (
    SELECT
        *,
        SUM(empieza_racha_nueva) OVER (
            PARTITION BY player_id ORDER BY finished_at
        ) AS grupo_racha
    FROM partidas_ordenadas
),
rachas AS (
    SELECT
        player_id,
        nickname,
        grupo_racha,
        team_won,
        COUNT(*)         AS largo_racha,
        MAX(finished_at) AS fin_de_la_racha
    FROM con_grupo_de_racha
    GROUP BY player_id, grupo_racha, team_won
)
-- La racha ACTUAL de cada jugador es la ultima (mayor fin_de_la_racha).
SELECT
    nickname,
    CASE WHEN team_won = 1 THEN 'Ganando' ELSE 'Perdiendo' END AS racha_actual,
    largo_racha
FROM rachas r
WHERE fin_de_la_racha = (
    SELECT MAX(fin_de_la_racha) FROM rachas r2 WHERE r2.player_id = r.player_id
)
ORDER BY (CASE WHEN team_won = 1 THEN largo_racha ELSE 0 END) DESC
LIMIT 15;


-- Bonus: promedio móvil de K/D (ventana de 5 mapas) para ver la tendencia
-- reciente de un jugador puntual -- cambiar el nickname para probar con otro.
SELECT
    m.finished_at,
    mps.kills,
    mps.deaths,
    ROUND(
        AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)) OVER (
            ORDER BY m.finished_at ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
        ), 2
    ) AS kd_promedio_movil_5
FROM match_player_stats mps
JOIN matches m ON mps.match_id = m.match_id
JOIN players p ON mps.player_id = p.player_id
WHERE p.nickname = 'VINI' AND m.finished_at >= strftime('%s', '2026-08-05')  -- tiene la racha ganadora mas larga del top -- buen caso para mostrar
ORDER BY m.finished_at;

-- Resultado (Temporada 9): VINI sigue con la racha activa más larga del
-- top de la región, 13 partidas ganadas seguidas -- coincide con el
-- resultado histórico porque sus 13 victorias ya caen enteras dentro de
-- esta temporada.
