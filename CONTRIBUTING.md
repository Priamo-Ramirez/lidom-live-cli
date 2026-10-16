# Contribuir a LIDOM Live CLI

Gracias por contribuir.

## Flujo recomendado

1. Crea una rama desde `main`.
2. Implementa cambios pequeños y enfocados.
3. Ejecuta validaciones locales antes de abrir PR:
   ```bash
   python3 -m pip install -e ".[test]"
   ruff check .
   pytest -q
   ```
4. Abre un Pull Request con descripción clara:
   - problema que resuelve,
   - cambios principales,
   - evidencia de pruebas.

## Convenciones

- Python 3.10+.
- Mantener compatibilidad con Linux/macOS.
- Evitar romper la interfaz CLI existente (`lidom-live now`, `lidom-live watch`).

## Cambios aceptados

- Nuevos comandos CLI relacionados a LIDOM.
- Mejoras de confiabilidad (red, errores, reintentos).
- Mejoras de DX (tests, documentación, CI).
