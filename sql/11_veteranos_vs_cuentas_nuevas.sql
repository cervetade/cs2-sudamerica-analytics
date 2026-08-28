-- ¿Las cuentas "veteranas" de FACEIT rinden distinto que las nuevas?
-- Técnica: funciones de fecha (julianday) para calcular antigüedad de
-- cuenta, CASE WHEN para bucketizar, LEFT JOIN con rendimiento real de la
-- temporada actual.
--
-- Ojo, esto NO es edad de la persona -- la Data API v4 de FACEIT no expone
-- eso en ningún endpoint (se investigó explícitamente). `activated_at` es
-- cuándo se creó la CUENTA de FACEIT, que es un proxy de antigüedad en la
-- plataforma, no de experiencia real con el juego: alguien pudo jugar CS
-- años antes de crear su cuenta FACEIT, o crearla y no usarla por un
-- tiempo largo. Se lee así en el hallazgo, no como "edad".
--
-- Requiere haber corrido fetch_faceit_data.py con el fetch de activated_at
-- (agregado en este mismo cambio) -- si tu players.csv es de antes, esta
-- columna va a estar vacía para todos y la query no va a tener filas.

WITH antiguedad AS (
    SELECT
        player_id,
        nickname,
        country,
        faceit_elo,
        activated_at,
        CASE
            WHEN activated_at IS NULL THEN NULL
            ELSE ROUND((julianday('now') - julianday(activated_at)) / 365.25, 1)
        END AS anios_de_cuenta
    FROM players
    WHERE is_sa_country = 1
),
bucketizado AS (
    SELECT *,
        CASE
            WHEN anios_de_cuenta IS NULL THEN NULL
            WHEN anios_de_cuenta < 1 THEN '< 1 año'
            WHEN anios_de_cuenta < 3 THEN '1-3 años'
            WHEN anios_de_cuenta < 5 THEN '3-5 años'
            ELSE '5+ años'
        END AS antiguedad_bucket
    FROM antiguedad
),
rendimiento_real AS (
    -- K/D real en la temporada actual (mismo patrón que sql/04) -- requiere
    -- al menos 5 mapas jugados para que el promedio no sea ruido.
    SELECT mps.player_id, COUNT(*) AS mapas_jugados,
        ROUND(AVG(mps.kills * 1.0 / NULLIF(mps.deaths, 0)), 2) AS kd_real
    FROM match_player_stats mps
    JOIN matches m ON mps.match_id = m.match_id
    WHERE m.finished_at >= strftime('%s', '2026-08-05')
    GROUP BY mps.player_id
    HAVING COUNT(*) >= 5
)
SELECT
    b.antiguedad_bucket,
    COUNT(*) AS jugadores,
    ROUND(AVG(b.faceit_elo), 0) AS elo_promedio,
    ROUND(AVG(r.kd_real), 2) AS kd_real_promedio,
    SUM(CASE WHEN r.player_id IS NOT NULL THEN 1 ELSE 0 END) AS con_muestra_de_rendimiento
FROM bucketizado b
LEFT JOIN rendimiento_real r ON b.player_id = r.player_id
WHERE b.antiguedad_bucket IS NOT NULL
GROUP BY b.antiguedad_bucket
ORDER BY MIN(b.anios_de_cuenta);

-- Pendiente: correr fetch_faceit_data.py (ya trae activated_at) y
-- build_database.py para poblar la columna, después completar acá el
-- resultado real -- no se escribe un hallazgo con números todavía.
