# Onboarding

Cómo un usuario nuevo llega a *entender y usar* SkillNet. Este documento fija el **modelo**
(principios + flujos), la **arquitectura** que lo sostiene, y un **plan por fases**. Es la vara
de medir: cualquier pantalla futura del onboarding se contrasta contra esto.

Relacionado: [degraded-mode-ux.md](degraded-mode-ux.md) (estados sin clave),
[personalization.md](personalization.md) (perfil del aprendiz),
[audience-modes.md](audience-modes.md) (organización / individual).

---

## 1. Principio rector

**Que libere, no que ate.** SkillNet vende libertad y adaptación; el onboarding tiene que
*sentirse* igual. El filtro de toda decisión: **¿esto para al usuario o lo libera?**

De ahí, seis pilares:

1. **La plataforma nunca está vacía.** Se arranca con un curso de demo ya montado (seed). Nada
   de tablero en blanco.
2. **Guía sí, pero puerta siempre abierta.** Un "paso 1 de N" por defecto (mucha gente lo
   quiere y es el camino que más convierte) **cerrable, reabrible y que recuerda el progreso**.
   Cerrar no castiga con vacío: caes en la plataforma llena.
3. **El valor se descubre tocando, al instante.** La primera victoria es contenido
   **pre-generado** (rápido, sin clave, sin esperar). Nunca una generación en vivo como
   bienvenida (lenta = derrota).
4. **El diferenciador es la UI generativa.** No son plantillas con el texto cambiado: la
   interfaz de cada lección se **compone** para ese contenido y esa persona. Se hace evidente
   con un empujón *ignorable* ("mira la misma lección para otra persona → es distinta").
5. **La personalización se ofrece o se infiere, nunca se impone.** La captura de "cómo
   aprendes" es opcional; lo que no se pregunta se aprende del comportamiento.
6. **La clave (API key) desbloquea, no cobra.** Sin clave exploras la demo; con clave lo haces
   con lo tuyo. Se llega a la clave *cuando ya se vio el valor y se quiere*.

---

## 2. La idea arquitectónica: **onboarding dirigido por capacidades**

El punto elegante: onboarding, degradación sin-clave y defaults inteligentes **son el mismo
problema** — *"según lo que hay disponible y quién eres, muestra una cosa u otra"*. Se resuelven
con **una sola fuente de verdad** en vez de `if (hayClave)` esparcidos por todo el código.

```
                 ┌──────────────────────┐
   settings/env  │  Capabilities        │  ai, generation, tutor, tts, images
   claves        │  (¿qué IA hay?)      │  → GET /capabilities  (o /setup/status)
                 └──────────┬───────────┘
                            │  useCapabilities()
        ┌───────────────────┼────────────────────┐
        ▼                   ▼                    ▼
  Onboarding steps    Elementos de UI      Banners degradado
  (filtrados)         (<Gated requires>)   (degraded-mode-ux)
```

### 2.1 `Capabilities` — la fuente de verdad
Un objeto derivado de la presencia (y validez) de claves, expuesto por el backend:

```ts
interface Capabilities {
  ai: boolean          // hay un LLM utilizable (nada funciona sin esto)
  generation: boolean  // generar cursos/lecciones
  tutor: boolean       // chat tutor
  tts: boolean         // voz (mascota / podcast) — degrada a offline, ver degraded-mode
  images: boolean      // infografías
}
```

- Backend: se calcula en un sitio (presencia de `LLM_API_KEY`, `TTS_API_KEY`, `OPENROUTER_API_KEY`).
  Hoy `GET /setup/status` ya existe y es el sitio natural (ya le añadimos `onboarding_enabled`).
- Frontend: **un hook `useCapabilities()`**. Cualquier pieza de IA lo consulta; nadie hardcodea
  "hay clave".

### 2.2 Gating declarativo (elemento estático vs. necesita-clave)
En lugar de esparcir condicionales, un componente/hook único:

```tsx
<Gated requires="tutor">
  <TutorPromptChip />        {/* solo se pinta si capabilities.tutor */}
</Gated>
```

Regla: **el elemento de IA se enciende solo si su capacidad está.** Sin clave **no se muestra**
(no un callejón/error). Ejemplos:

| Siempre (estático / pre-cocinado) | `requires` (se enciende con clave) |
|---|---|
| Curso demo (seed), verlo | Opción **"otro"** libre en preguntas (`generation`/`ai`) |
| Empujón de contraste (dos personas, seed) | Preview generado / "crea tu primer curso" (`generation`) |
| Presets fijos de las preguntas | Chat con el tutor (`tutor`) |
| Tour (joyride) | Personalización que regenera al vuelo (`generation`) |

**Clave de diseño:** el lado sin-clave debe sentirse **completo** (lo pre-cocinado carga el
valor). Lo de IA es **aditivo**, no "lo bueno estaba escondido".

### 2.3 Onboarding como **datos**, no como flujo hardcodeado
El tour es una lista declarativa de pasos; joyride solo la consume. Añadir/quitar/reordenar =
editar datos.

```ts
interface OnboardingStep {
  id: string
  role: 'employee' | 'admin'
  target: string           // selector del elemento a resaltar
  title: string; body: string
  requires?: keyof Capabilities   // se omite el paso si la capacidad no está
  order: number
}
```

Filtro en runtime: `steps.filter(role).filter(cap => !s.requires || capabilities[s.requires])`.
Un paso que habla del tutor **desaparece** sin clave, sin ramas ad-hoc.

### 2.4 Estado del onboarding — por usuario, persistido, reabrible
```ts
interface OnboardingState { completed: boolean; dismissedAt?: string; lastStepId?: string }
```
- Ortogonal al routing: **nunca** redirige a la fuerza (ya existe el flag `ONBOARDING_ENABLED`).
- MVP: `localStorage`. Fase posterior: campo por usuario (cross-device).
- Reabrible desde un "?" persistente; `lastStepId` da el "recuerda dónde iba".

### 2.5 Defaults inteligentes — un **resolver** desde el arquetipo de org
El admin da una pista mínima (educación / empresa) → un resolver mapea arquetipo → defaults.

```ts
type Archetype = 'education' | 'enterprise' | ...
function resolveDefaults(a: Archetype): OrgSettings   // p.ej. enterprise ⇒ mascota off
```
- **Un solo resolver**, no condicionales dispersos.
- Los valores son **defaults**, siempre **overridables** (usuario/org).
- Toda decisión automática se **muestra y se puede revertir** ("Hemos desactivado la mascota
  porque es un entorno de empresa — cámbialo aquí"). Nunca magia silenciosa.

### 2.6 Demo compartido = asset de primera clase
El curso de prueba es seed presente en todo despliegue (`is_demo`), **ejemplo para los dos
roles**: el admin ve "esto se genera", el empleado lo *hace*. Visible sin clave (ya generado).
Con clave, **el mismo** curso se vuelve conversable (tutor) y adaptable/regenerable — la clave
no cambia *qué* ves, cambia *cuánto puedes hacer con ello*.

---

## 3. Flujos (un patrón, dos rellenos)

Bifurca solo en el **rol**; cada rama es mínima. Estructura común: **encuadre → una captura que
importa → primera victoria**.

### 3.1 Empleado (cuenta creada por el admin; nunca toca la clave)
1. Login → **home no-vacía** (matriculado en el demo / sus cursos) + "empieza aquí" suave.
2. **Tour por defecto, cerrable:** "abre tu primera lección" → toca una lección **ya
   pre-generada y personalizada** (instantánea, prewarm). *Aha* = rica **y** se adapta.
3. **Micro-captura opcional:** "¿cómo te gusta que te expliquen? (opcional)" → presets **+
   "otro"** (el "otro" solo con clave). Saltable → perfil por defecto + inferencia por conducta.
4. **Empujón de contraste (ignorable):** "así se lo explicamos a otra persona" → misma
   materia, distinta UI → capta la personalización.
5. A partir de ahí, solo aprende.

### 3.2 Admin / dueño (auto-hospeda y monta la empresa)
1. **Setup mínimo** (ya existe) + **una pregunta de arquetipo** (educación/empresa → defaults).
2. **Panel no-vacío** con el curso demo + tour cerrable.
3. **Descubre la UI generativa tocando** el demo (mismo contraste de dos personas).
4. **Momento "hazlo tuyo":** "Crea tu primer curso". Si **no hay clave** → "conecta tu IA"
   (por qué + enlace al proveedor + pegar + **validar en vivo**). No es peaje: llegas aquí ya
   convencido. Mientras, todo explorable; acciones de IA muestran "conecta una clave" en su sitio.
5. **Generación real = en segundo plano + aviso.** Nunca una barra de carga como bienvenida.
6. Invita a empleados.

---

## 4. Plan por fases (barato → caro; nada complejo de primeras)

Motor del tour: **react-joyride** (spotlight, "paso 1 de N", saltar/cerrar, control de pasos).
Nosotros ponemos los **datos y el estado** (§2.3, §2.4), no el motor.

> **Estado (2026-08-21):** Fase 0 ✅, la infra de Fase 2 (`Capabilities`/`<Gated>`) ✅ y el
> banner de degradado ✅ están hechos y en `main`; el tour de admin (Fase 1) también. Queda,
> con decisión/diseño de por medio: el 3-way de arquetipo + `resolveDefaults`, el empujón de
> contraste, la API key desde la UI, la generación en 2º plano, y la Fase 3.

### Fase 0 — MVP ✅ HECHO
- **home no-vacía** con el demo (seed). ✅
- **Tour joyride** empleado (home → primera lección pre-generada), cerrable, `localStorage`. ✅
- **Perfil no bloqueante** (`ONBOARDING_ENABLED` + captura existente). ✅
- Solo elementos **estáticos**. ✅

### Fase 1 — hacer visible el diferenciador  ◑ PARCIAL (resto: con diseño)
- ○ **Empujón de contraste** (dos personas, datos del seed) — pendiente.
- ✅ **Tour de admin** — hecho: `ProductTour` role-aware (mismo joyride, pasos admin).
- ○ **1 smart-default**: arquetipo empresa/educación → `resolveDefaults` (empresa apaga la
  mascota) + la línea que lo explica — pendiente (necesita backend del arquetipo).

### Fase 2 — el desbloqueo self-hosted (la capa de IA)  ◑ PARCIAL
- ✅ **`Capabilities` + `useCapabilities()` + `<Gated>`** (§2.1–2.2) — infra hecha (backend
  deriva de las claves y lo expone en `/setup/status`; front la consume).
- ✅ **Banners de degradado** (`CapabilityHealthBanner` en admin) — hecho.
- ○ **API key desde la UI** (pegar + validar) — pendiente (decisión de almacenamiento/seguridad).
- ○ Encender los `requires`: **"otro"** libre, **preview generado**, **chat con el tutor**.
- ○ **Generación en segundo plano + aviso**.

### Fase 3 — lo complejo, al final  ○ PENDIENTE
- **Inferir el perfil del comportamiento** (qué abre/relee/salta). Módulo separable de señales.
- Estado del onboarding **cross-device**, arquetipos más finos.

---

## 5. Qué ya existe vs. qué falta

| Ya existe (✅) | Falta (○) |
|---|---|
| Setup wizard + **bienvenida** (logo/mascota/degradado), login, home | Pregunta de **arquetipo** + `resolveDefaults` |
| Curso demo (seed) + lecciones pre-generadas (prewarm) | **Empujón de contraste** (dos personas) |
| **Tour joyride role-aware** (empleado + admin), reabrible, estado por rol | **API key en UI** (pegar+validar) — hoy en `.env` |
| Captura de perfil + flag `ONBOARDING_ENABLED` | **Generación en 2º plano** + `requires` ("otro"/preview/tutor) |
| **`Capabilities` + `useCapabilities` + `<Gated>`** + banner de degradado | Fase 3 (inferir perfil, cross-device) |

---

## 6. Resumen en una frase

**Plataforma llena desde el inicio · guía por defecto pero siempre cerrable y reabrible · valor
por tocar, no por contar · perfil ofrecido o inferido, nunca impuesto · defaults auto-elegidos y
reversibles · la clave desbloquea, no cobra** — todo bajo un motor limpio: la app declara *qué
necesita* (capacidad × rol) y un resolver decide *qué mostrar y cómo degradar*.
