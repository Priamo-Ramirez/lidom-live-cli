# LIDOM Live CLI

CLI en Python para consultar resultados de la Liga Dominicana de Béisbol (LIDOM) usando MLB Stats API.

## Identificadores de API

- `sportId=17` (Winter Leagues)
- `leagueId=131` (LIDOM)

## Requisitos

- Python 3.10+

## Instalación local

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

Salida JSON:

```bash
lidom-live now --date 2026-10-16 --json
```

Modo en vivo (actualiza cada 20 segundos):

```bash
lidom-live watch
```

Cambiar frecuencia de actualización:

```bash
lidom-live watch --interval 10
```

## Desarrollo

Instalar dependencias de tests:

```bash
python3 -m pip install -e ".[test]"
```

Ejecutar tests:

```bash
pytest -q
```
