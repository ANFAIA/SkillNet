# Prompt para la siguiente sesion

Pega esto al inicio de una sesion nueva de Claude Code.

---

## CONTEXTO

Proyecto SkillNet (ANFAIA). Lee `CLAUDE.md` para orientacion del repo y `.claude/projects/`
para la memoria de decisiones. El roadmap esta en `docs/ROADMAP.md`. Las normas de diseno
en `docs/design/design-system.md` y `docs/design/motion-system.md`.

Lo que se hizo en la sesion anterior (2026-08-07):
- Pipeline multi-agente implementado (4 agentes bajo MULTI_AGENT_RENDER=true)
- Stepper Brilliant-style (cada bloque es una pantalla)
- Araña mascota con chat IA inline
- Fullscreen lesson view con portal
- Agent-driven UI: Zustand store + tool registry + SSE action events + react-intl
- Docs actualizados: ROADMAP, design-system, motion-system, generative-ui-personalization

Todo esta en main, Docker arrancado con `docker compose up -d`.

## TU ROL

Ejecuta los 5 slices EN PARALELO con subagentes. Cada slice tiene su propio agente.
Usa `run_in_background: true` para todos. Lanza los 5 a la vez.

## SLICE 1 — Calidad del contenido generado

1. Sube estos PDFs como documentos fuente via la API:
   - `C:\Users\sonde\Downloads\2026 Manual para Recuperar Entradas 2026 Crocantickets.pdf`
   - `C:\Users\sonde\Downloads\Ecosistema-Ticketrona (1).pdf`
2. Crea un curso desde cada PDF con el pipeline multi-agente (MULTI_AGENT_RENDER=true)
3. Lee el render generado de cada nodo desde la base de datos
4. Compara contra el PDF original:
   - ¿Los datos coinciden con el documento? ¿Se invento algo?
   - ¿Falta algun paso del procedimiento?
   - ¿El componente es el adecuado? (procedimiento -> StepByStepReveal, lista -> Table)
   - ¿El lead engancha o copia el summary?
   - ¿Las preguntas del quiz son de caso concreto?
   - ¿Se responden con info del documento?
5. Documenta los fallos encontrados
6. Itera los prompts de los agentes (`src/agents/runtime/agents/`) para corregirlos
7. Regenera y verifica que mejoro
8. Corre `uv run python scripts/quality_bench.py --offline` para verificar que no rompio nada

## SLICE 2A — UX del stepper y visualizacion

Lee las normas de `docs/design/design-system.md` y `docs/design/motion-system.md` ANTES
de tocar nada. Reglas clave:
- Morph desde el trigger con layoutId (NUNCA aparicion de la nada)
- Opacity + scale, NUNCA blur
- Secuencial: cada elemento espera al anterior
- Chevrones, no flechas

Tareas:
1. La transicion al entrar en un nodo es un salto brusco — debe ser un morph. El NodeView
   es un portal fullscreen (`src/pages/employee/NodeView.tsx`). Necesita `layoutId` conectado
   con el elemento de la lista de nodos que lo abrio. Patron de referencia: el morph de
   CreateCourse (`src/pages/admin/CreateCourse.tsx`) donde el card se expande.
2. La transicion al salir (chevron atras) debe ser el morph inverso.
3. Testea centrado vertical con todos los tipos de bloque: tabla larga, quiz con 4 opciones,
   lead corto, StepByStepReveal, BeforeAfter. Si algo no centra, arregla.
4. Responsive: prueba el stepper en viewports de 375px, 768px y 1440px.
5. La araña (`LessonBuddy.tsx`): verificar que no tapa contenido en pantallas pequenas.
6. Los charts (`ChartBlock.tsx`) deben animar al entrar (ya implementado, verificar).
7. El feedback del quiz (`QuizItemBlock.tsx`) ya tiene motion, verificar que funciona.

## SLICE 2B — Chat del tutor en las lecciones

1. Arranca Docker si no esta corriendo: `docker compose up -d`
2. Siembra datos: `docker compose exec api uv run python -m src.seed_demo_v2`
3. Abre un curso como empleado (password: `espiga2026`) y navega a un nodo
4. Abre el chat de la araña y hazle 10 preguntas variadas:
   - "Que estoy aprendiendo?" (debe saber el nodo)
   - "Explicame esto mas simple" (debe dar contexto)
   - "No lo entiendo" (debe ser paciente)
   - "Dame un ejemplo" (debe ser concreto)
   - "Esto para que sirve?" (debe conectar con el puesto)
5. Evalua:
   - ¿Llega el contexto del nodo? (titulo, summary)
   - ¿El tono es de companero o de bot formal?
   - ¿Las respuestas son relevantes al contenido de la leccion?
   - ¿El streaming funciona? (tokens llegan progresivamente)
6. Si el tono es demasiado formal, ajusta el system prompt del tutor en
   `src/llm/prompts/tutor.py`
7. Si el contexto no llega, revisa `LessonBuddy.tsx` y la funcion `streamChat`
8. Verifica que funciona con auth de empleado (no admin)

## SLICE 2C — Idiomas (i18n)

La infraestructura ya esta: react-intl, catalogos es/en en `src/i18n/`, IntlProvider en
App.tsx, tool set_locale registrada.

1. Migra estos componentes a useIntl() / FormattedMessage (en este orden):
   - `src/components/layout/Sidebar.tsx` (nav items, help card)
   - `src/components/layout/AdminSidebar.tsx` (mismos strings)
   - `src/components/courses/blocks/StackBlock.tsx` (aria-labels de chevrones)
   - `src/components/courses/blocks/LessonBuddy.tsx` (placeholder, hints)
   - `src/components/courses/blocks/QuizItemBlock.tsx` (Comprobar, Correcto, Incorrecto)
   - `src/components/courses/blocks/DragOrderBlock.tsx` (Comprobar, Reiniciar)
   - `src/pages/employee/NodeView.tsx` (titulo, aria-labels)
   - `src/pages/admin/CreateCourse.tsx` (botones, pasos de creacion)
2. Para cada componente: importar `useIntl` o `FormattedMessage`, reemplazar el string
   hardcodeado por la key del catalogo. Si falta una key, anadirla a `src/i18n/es.ts`
   y `src/i18n/en.ts`.
3. Verificar que `npx tsc --noEmit` pasa despues de cada componente.
4. Al final, testear: cambiar a ingles via la consola del navegador:
   ```js
   // En la consola del navegador:
   // El store de Zustand persiste en localStorage
   localStorage.setItem('skillnet-preferences', JSON.stringify({state:{locale:'en',theme:'system',sidebarCollapsed:false},version:0}))
   location.reload()
   ```
   Verificar que los strings migrados aparecen en ingles.

## SLICE 3B — Flujo de crear curso

1. Probar el flujo completo: crear curso desde idea → esquema → crear → probar
2. Verificar que la pantalla de progreso (4 pasos con check) funciona
3. Verificar que "Probar curso" va directo al primer nodo
4. Verificar que "Asignar a empleados" lleva a la pantalla de asignacion
5. Si algo no fluye, arreglar. Seguir las normas de transicion de motion-system.md.

## REGLAS PARA TODOS LOS SLICES

- Subagentes en paralelo, nunca uno solo haciendo todo
- Lee `docs/design/design-system.md` y `docs/design/motion-system.md` ANTES de tocar la UI
- NUNCA blur. Solo opacity y scale.
- Morph desde el trigger, nunca aparicion de la nada.
- Secuencial: los elementos entran uno tras otro, no todos a la vez.
- Commits frecuentes con `git add` + `git commit` + `git push origin main`
- Sin Co-Authored-By en los commits
- Tests: `uv run pytest -m "not integration" -x -q` en el backend, `npx tsc --noEmit` en el frontend
- Si algo rompe tests, arreglar antes de seguir
