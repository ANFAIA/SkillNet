# Mascota (arañita SkillNet)

Mascota vectorial autocontenida y animable. Sin dependencias (solo React + CSS).
Fiel al arte de referencia: cuerpo trazado + piezas geométricas. Colores editables por variables CSS.

## Uso

```tsx
import { Mascota } from '@/components/mascota'

<Mascota anim="celebrar" size={140} />
<Mascota anim="talk" say="¡Muy bien!" />
<Mascota anim="pensar" size={90} followCursor={false} />
```

`anim` cambia la animacion. Las de un solo disparo (`saltar`, `temblar`, `saludar`, `idea`)
vuelven solas a `idle` al terminar. Para las continuas, cambia `anim` cuando quieras.

## Animaciones

**Aprendizaje (estilo Duolingo/Koji):**

| anim | Cuando usarla |
|------|---------------|
| `celebrar` | Acierto / leccion completada (salto + confeti) |
| `animar`   | Motivar entre pasos (rebote + bocadillo "¡Vamos!") |
| `pensar`   | Mientras se genera/carga contenido (nube de puntos) |
| `idea`     | Pista o "¡lo pillaste!" (bombilla) |
| `ups`      | Fallo suave, sin castigar (cejas + gotita) |
| `amor`     | Le gusta / favorito (corazones) |
| `fuego`    | Racha diaria (llama) |

**Basicas:** `idle` (por defecto), `talk` (bocadillo, texto via `say`), `web` (se cuelga de un hilo),
`saltar`, `caminar` (se desplaza de lado), `temblar`, `saludar`, `dormir` (ojos en U + zzz).

## Props

- `anim?: MascotaAnim` — animacion actual (default `idle`).
- `size?: number | string` — ancho (px o cualquier medida CSS). El alto escala solo.
- `say?: string` — texto del bocadillo para `anim="talk"`.
- `followCursor?: boolean` — las pupilas siguen el puntero (default `true`).
- `className?`, `onClick?`.

## Personalizar color

En `mascota.css` (o sobreescribiendo en tu CSS):

```css
.skn-mascota { --mas-blue: #3F7EE0; --mas-navy: #0A1A3E; }
```

## Ficheros

- `Mascota.tsx` — el componente.
- `mascota.css` — estilos + keyframes (scopeados a `.skn-mascota`, keyframes con prefijo `mas-`).
- `mascota.svg` — version estatica neutra (logo/favicon).
- `index.ts` — reexport.

Respeta `prefers-reduced-motion` (desactiva animaciones).
