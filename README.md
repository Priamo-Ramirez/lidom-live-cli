# LIDOM Live CLI

<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/a/a6/Major_League_Baseball_logo.svg" alt="MLB" height="64" />
  &nbsp;&nbsp;&nbsp;
  <img src="https://lidom.com/especiales/countdown-2627/Logo-Lidom.svg" alt="LIDOM" height="64" />
</p>

<p align="center">
  <a href="https://github.com/Priamo-Ramirez/lidom-live-cli/actions/workflows/ci.yml">
    <img src="https://github.com/Priamo-Ramirez/lidom-live-cli/actions/workflows/ci.yml/badge.svg" alt="CI" />
  </a>
  <img src="https://img.shields.io/github/v/release/Priamo-Ramirez/lidom-live-cli?display_name=tag" alt="Release" />
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License" />
  <img src="https://img.shields.io/badge/API-MLB%20Stats-1f4f99.svg" alt="MLB Stats API" />
</p>

CLI en Python para consultar resultados en vivo de la Liga Dominicana de Béisbol (LIDOM) usando MLB Stats API.

## Tabla de contenido

- [Características](#características)
- [Identificadores de API](#identificadores-de-api)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Uso](#uso)
- [Salida esperada](#salida-esperada)
- [Desarrollo](#desarrollo)
- [CI](#ci)
- [Comunidad](#comunidad)
- [Licencia](#licencia)

## Características

- Consulta de resultados por fecha.
- Consulta de resultados por rangos recientes (`yesterday`, `last-week`, `last-month`).
- Consulta de juegos programados por día, semana o mes.
- Modo de actualización continua para seguimiento en vivo.
- Turno actual (at-bat) en vivo por `gamePk`.
- Play-by-play completo por `gamePk`.
- Stats clave del juego (R/H/E y AVG por equipo) en vivo por `gamePk`.
- Líderes de bateo (AVG) por temporada de LIDOM.
- Filtros por estado de juego y por equipo.
- Salida legible en tabla para terminal.
- Salida JSON para integración con scripts.
- Reintentos automáticos con backoff para errores transitorios de red.

## Identificadores de API

- `sportId=17` (Winter Leagues)
- `leagueId=131` (LIDOM)

## Requisitos

- Python 3.10+

## Instalación

```bash
python3 -m pip install -e .
```

## Uso

Marcador de la fecha actual (zona horaria de RD):

```bash
lidom-live now
```

Marcador de una fecha específica:

```bash
lidom-live now --date 2026-10-16
```

Resultados recientes por período:

```bash
lidom-live history --period yesterday
lidom-live history --period last-week --status "Final"
lidom-live history --period last-month --team "Licey"
```

Schedule de juegos programados por período:

```bash
lidom-live schedule --period day
lidom-live schedule --period week
lidom-live schedule --period month --team "Escogido"
```

Schedule desde una fecha ancla:

```bash
lidom-live schedule --period week --date 2026-10-17
```

Salida JSON:

```bash
lidom-live now --date 2026-10-16 --json
```

Filtrar por estado y equipo:

```bash
lidom-live now --status "In Progress,Final" --team "Licey"
```

Vista compacta sin cabecera:

```bash
lidom-live now --compact --no-header
```

Modo en vivo (actualiza cada 20 segundos):

```bash
lidom-live watch
```

Cambiar frecuencia de actualización:

```bash
lidom-live watch --interval 10
```

Ejecutar un número limitado de iteraciones:

```bash
lidom-live watch --status "In Progress" --iterations 5 --no-clear
```

Turno actual del juego (at-bat):

```bash
lidom-live atbat --game-pk 851509
```

Seguimiento continuo del turno (modo watch):

```bash
lidom-live atbat --game-pk 851509 --watch --interval 10
```

Vista compacta del turno:

```bash
lidom-live atbat --game-pk 851509 --compact
```

Vista detallada con color ANSI:

```bash
lidom-live atbat --game-pk 851509 --color
```

Modo watch en vista compacta (5 iteraciones):

```bash
lidom-live atbat --game-pk 851509 --watch --compact --iterations 5 --no-clear
```

Play-by-play completo del juego:

```bash
lidom-live playbyplay --game-pk 826278
```

Play-by-play compacto con picheos:

```bash
lidom-live playbyplay --game-pk 826278 --compact --with-pitches
```

Filtrar play-by-play por inning o equipo:

```bash
lidom-live playbyplay --game-pk 826278 --inning 7
lidom-live playbyplay --game-pk 826278 --team "Licey"
```

Stats del juego en vivo (line score + AVG):

```bash
lidom-live game-stats --game-pk 851509
```

Líderes de bateo (AVG) para una temporada:

```bash
lidom-live leaders --season 2025 --limit 10
```

## Salida esperada

```text
LIDOM | Fecha: 2026-10-16 | Actualizado: 2026-10-16 20:14:05 AST
------------------------------------------------------------------------------------------------------------
gamePk   Visitante                    R  Home                       R  Estado             Hora RD
------------------------------------------------------------------------------------------------------------
851509   Aguilas Cibaenas             3  Gigantes del Cibao         2  In Progress        19:00
851491   Tigres del Licey             -  Leones del Escogido        -  Scheduled          19:15
```

Ejemplo de salida detallada para `atbat`:

```text
================================================================================
LIDOM EN VIVO
Juego: Tigres del Licey vs Leones del Escogido
Estado: Final | Fecha: 2025-12-05 | Estadio: Estadio Quisqueya Juan Marichal
Marcador: Tigres del Licey 5 - 3 Leones del Escogido
Inning: Baja 9 | Outs: 3 | Corredores: Bases vacías
================================================================================

TURNO ACTUAL
- Equipo al bate: Leones del Escogido
- Bateador: Junior Lake (R)
- Pitcher: Anderson Severino (L)
- Conteo: 0-2
- Último pitcheo: In play, out(s) (Sinker, 97.8 mph)

SECUENCIA DEL TURNO
1) Called Strike (Sinker, 96.0 mph)
2) Swinging Strike (Sinker, 97.6 mph)
3) In play, out(s) (Sinker, 97.8 mph)

CONTEXTO RÁPIDO
- Bateador hoy: 0-4 | BB, K, R
- Pitcher hoy: 1.2 IP, 0 ER, 2 K, BB
- Próximo bateador: Erik González
================================================================================
```

Ejemplo de salida compacta para `atbat --compact`:

```text
Tigres del Licey 5-3 Leones del Escogido | Baja 9 | Outs: 3 | Junior Lake (R) vs Anderson Severino (L) | Conteo 0-2 | Último: In play, out(s) (Sinker, 97.8 mph)
```

Ejemplo de salida para `playbyplay`:

```text
Play-by-play | Juego 826278 | Tigres del Licey vs Leones del Escogido | Estado: Final
Fecha: 2025-12-05 | Estadio: Estadio Quisqueya Juan Marichal
------------------------------------------------------------------------------------------------------------
  0) Alta 1 | Tigres del Licey | Gustavo Nunez vs Johnny Cueto
     Resultado: Gustavo Nunez grounds out, second baseman to first baseman. | Outs: 1 | Score: Tigres del Licey 0-0 Leones del Escogido
     Picheos en turno: 2

  1) Baja 1 | Leones del Escogido | Junior Lake vs Anderson Severino
     Resultado: Junior Lake singles on a line drive, one run scores. [SCORING] | Outs: 2 | Score: Tigres del Licey 0-1 Leones del Escogido
     Picheos en turno: 2
```

## Desarrollo

Instalar dependencias de desarrollo:

```bash
python3 -m pip install -e ".[test]"
```

Lint:

```bash
ruff check .
```

Tests:

```bash
pytest -q
```

## CI

Workflow de GitHub Actions:

- `lint` con Ruff
- `tests` con matriz Python 3.10/3.11/3.12

## Códigos de salida

- `0`: ejecución exitosa.
- `3`: error de red o respuesta HTTP del API.
- `4`: error de formato de respuesta.

## Comunidad

- Guía de contribución: [CONTRIBUTING.md](CONTRIBUTING.md)
- Código de conducta: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Reporte de seguridad: [SECURITY.md](SECURITY.md)
- Plantilla de PR: [.github/pull_request_template.md](.github/pull_request_template.md)

## Licencia

Este proyecto se distribuye bajo licencia MIT. Ver [LICENSE](LICENSE).
