# Logo de TherionLabs (favicon e íconos)

Pon aquí el logo oficial con uno de estos nombres:

- `therionlabs-logo.svg` (recomendado: escala a cualquier tamaño), o
- `therionlabs-logo.png` (cuadrado, mínimo 512 × 512 px, fondo transparente).

Después ejecuta, desde `frontend-next/`:

```
npm run iconos
```

Genera `app/favicon.ico` (16 y 32 px), `app/icon1.png` (16), `app/icon2.png` (32), `app/icon3.png` (512)
y `app/apple-icon.png` (180). Next.js agrega solo las etiquetas `<link>` del `<head>`.
Mientras no esté el logo, se usa la marca hexagonal provisional (`app/icon.svg`).
