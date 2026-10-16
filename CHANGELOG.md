# Changelog

Todos los cambios relevantes se documentan en este archivo.

## [0.1.1] - 2026-10-16

### Added

- Filtros CLI por estado (`--status`) y equipo (`--team`).
- Opciones de presentación `--compact`, `--no-header` y `--separator`.
- Control de modo watch con `--iterations` y `--clear/--no-clear`.
- Códigos de salida para automatización (`0`, `3`, `4`).
- Manejo de errores de red/API con mensajes accionables.

### Changed

- README ampliado con ejemplos avanzados de uso para `now` y `watch`.

## [0.1.0] - 2026-10-16

### Added

- Comando `lidom-live now` para consultar resultados por fecha.
- Comando `lidom-live watch` para actualización continua en terminal.
- Salida JSON para automatización.
- Reintentos con backoff para llamadas a MLB Stats API.
- Suite de tests con `pytest`.
- Pipeline CI con GitHub Actions.
