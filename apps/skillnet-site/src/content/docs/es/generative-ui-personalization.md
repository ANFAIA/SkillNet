---
title: "Personalización de interfaz generativa"
order: 39
section: "extensibility"
---

# Generative UI Personalization

> **Estado: vision de futuro.** Este documento describe la direccion a largo plazo para la
> personalizacion de la interfaz de SkillNet mediante agentes. No es un plan de implementacion
> inmediata — es la estrella polar que guia las decisiones de arquitectura.

## La tesis

La UI se adapta al usuario, no el usuario a la UI. Un agente observa como usa la plataforma
cada persona y genera, propone o modifica la interfaz en tiempo real usando OpenUI Lang —
el mismo motor que ya genera las lecciones.

## Tres niveles

### Nivel 1 — Preferencias basicas (implementado parcialmente)

El agente puede cambiar ajustes de la app mediante tool calls sobre SSE.

- `set_locale(locale)` — cambia el idioma de la interfaz
- `set_sidebar_collapsed(collapsed)` — colapsa/expande la barra lateral

**Infraestructura existente (2026-08-07):**
- Zustand store (`stores/preferences.ts`) persistido en localStorage
- Tool registry (`lib/toolRegistry.ts`) despachado desde eventos SSE `action`
- Backend: `chat_service.py` parsea lineas `ACTION:` del LLM y emite eventos SSE
- Prompts: `llm/prompts/tools.py` ensena al LLM las herramientas disponibles
- i18n: react-intl con catalogos es/en, IntlProvider en App.tsx

**Pendiente nivel 1:**
- Temas de color predefinidos (3-5 sets de CSS variables)
- Variantes de layout (sidebar izquierda, barra superior, sin sidebar)
- Persistencia en backend (`PATCH /users/me/preferences`) para cross-device

### Nivel 2 — Widgets personalizados (el salto)

El admin o el empleado pueden "anclar" artefactos generados por el chat en su dashboard.

**Ejemplo:** El admin pregunta al chat "cual es el % de compliance de mi equipo". El chat
genera una metrica con OpenUI Lang y la muestra inline. El admin dice "dejalo ahi fijo" y
el widget se persiste como un programa OpenUI en su dashboard personalizado.

**Arquitectura:**
```
Usuario habla con el chat
    -> El agente genera un programa OpenUI Lang (como ya hace con lecciones)
    -> El frontend lo renderiza inline en el chat
    -> El usuario dice "anclalo" (o el agente lo propone)
    -> El programa se persiste en `user_dashboard_widgets`
    -> El dashboard lo renderiza con el mismo <Renderer> de las lecciones
```

El dashboard de cada usuario es una coleccion de programas OpenUI, cada uno generado por
el agente en algun momento y anclado por el usuario. No hay un dashboard fijo para todos —
cada persona ve lo que le importa.

**Referencia de la industria:** A2UI (Google, 2026) define `createSurface` / `updateComponents`
para que agentes generen regiones de UI. AG-UI (CopilotKit, respaldado por Microsoft) define
el protocolo de transporte. SkillNet ya tiene ambos de facto: SSE como transporte y OpenUI
Lang como formato de superficie.

### Nivel 3 — Agente proactivo

Un agente que corre en background, observa patrones de uso y propone personalizaciones
sin que el usuario las pida.

**Ejemplos:**
- "Este admin consulta el % de compliance todos los lunes" -> le genera el widget y se lo
  ofrece la proxima vez que abre la app.
- "Este empleado siempre pregunta por alergenos antes de empezar turno" -> le pone una
  chuleta rapida en su dashboard.
- "Este admin nunca usa el skill map" -> se lo ofrece ocultar de su sidebar.
- "Este empleado falla siempre en el mismo tipo de pregunta" -> el tutor ajusta el
  contenido sin que el admin tenga que intervenir.

**Mecanismo:**
- Un cron o un trigger por sesion que analiza `learning_events` y `llm_usage_log`
- El agente genera una propuesta (widget, ajuste, recomendacion)
- La propuesta se muestra como una notificacion o un mensaje proactivo del buddy
- El usuario acepta, rechaza o modifica

**Inspiracion:** Brilliant's Koji observa lo que haces y ajusta su nivel de ayuda. Aqui
es lo mismo pero para toda la plataforma, no solo para una leccion.

## Principio de diseno

> "Good personalization makes itself invisible. The user does not configure the app —
> the app learns the user."

La personalizacion no es un panel de ajustes con 50 opciones. Es un agente que observa,
propone y ejecuta. El usuario siempre tiene el control (puede rechazar, revertir, pedir
cambios) pero nunca tiene que buscar la opcion en un menu.

## Orden de implementacion recomendado

1. Completar nivel 1: temas de color + variantes de layout + persistencia backend
2. Nivel 2 minimo: un widget anclable desde el chat (proof of concept)
3. Nivel 2 completo: dashboard personalizado con multiples widgets
4. Nivel 3: agente proactivo con cron de analisis de uso

## Dependencias tecnicas

- **OpenUI Lang** — ya implementado, es el motor de rendering
- **SSE action events** — ya implementado, es el transporte
- **Tool registry** — ya implementado, es el despacho
- **Zustand store** — ya implementado, es la persistencia local
- **react-intl** — ya implementado, es la i18n basica
- **Dashboard widget table** — por crear (modelo + API + frontend)
- **Usage analytics agent** — por crear (cron + LangGraph + trigger rules)

## Autoridad del usuario sobre la presentación

La personalización inferida nunca contradice una petición explícita. Si una persona pide una
explicación con imágenes, audio, vídeo o texto y el kit dispone de esa modalidad, esa elección
prevalece sobre el `format_vector`, las heurísticas y las recomendaciones del agente.

Eso no obliga a convertir toda la experiencia en una sola forma. Dentro de la modalidad solicitada,
SkillNet puede combinar funciones pedagógicas distintas —por ejemplo, explicación visual,
recuperación activa, autoexplicación y escenario— siempre que no oculte ni sustituya lo que la
persona pidió. El sistema puede sugerir alternativas, pero el cambio requiere aceptación.

La separación entre preferencia de presentación, accesibilidad, estrategia pedagógica y componente
se define en [`adaptive-learning.md`](/docs/adaptive-learning).
