# Roadmap

> Actualizado: 2026-08-07. Prioridades ordenadas. Cada fase construye sobre la anterior.

---

## Fase 1 — Calidad del contenido generado (PRIORIDAD)

Nada importa si los cursos son malos. El pipeline multi-agente esta implementado pero la
calidad real del contenido generado no esta validada con usuarios.

- [ ] Crear cursos reales con temas variados (no solo compliance)
- [ ] Evaluar output: leads, contenido de concepto, preguntas
- [ ] Iterar prompts de Blueprint, Content Writer e Interaction Designer
- [ ] Correr quality_bench con LLM real, medir cobertura de componentes
- [ ] Objetivo: first-pass >80%, preguntas de caso concreto, leads que enganchen

## Fase 2 — Visualizacion y experiencia de curso

El stepper Brilliant-style esta implementado. Falta pulirlo con contenido real.

- [ ] Centrado vertical testeado con todos los tipos de bloque
- [ ] Responsive: pantallas pequenas, tablets
- [ ] Spider buddy: posicion en diferentes resoluciones
- [ ] Intro del curso: titulo + outcomes en una pantalla
- [ ] Transiciones entre nodos: fluidas, sin parpadeo
- [ ] Componentes visuales: animaciones de entrada, feedback de quiz, charts

## Fase 3 — Chat del tutor en las lecciones

La araña esta conectada al tutor pero no testeada de verdad.

- [ ] Testear end-to-end: contexto del nodo llega, respuestas relevantes
- [ ] Tono: companero cercano, no bot formal
- [ ] Funciona con auth de empleado (no admin)
- [ ] Reaccion a aciertos/errores del quiz (futuro: como Koji)

## Fase 4 — Idiomas (i18n)

La infraestructura esta montada (react-intl + catalogos es/en + agent tool set_locale).
Falta migrar los componentes.

- [ ] Migrar sidebar, node view, stepper a useIntl() / FormattedMessage
- [ ] Migrar create course, course view
- [ ] Migrar componentes de bloque (quiz, drag, etc.)
- [ ] El contenido de los cursos se genera en el idioma del admin
- [ ] Futuro: traduccion on-demand del contenido para empleados en otro idioma

## Fase 5 — Temas visuales predefinidos

- [ ] Disenar 3-5 sets de CSS variables (corporate, warm, minimal, dark...)
- [ ] Tool set_theme en el agent para cambiar entre ellos
- [ ] Persistencia en preferencias del usuario
- [ ] Responsive: cada tema funciona en todos los layouts

## Fase 6 — Generative UI personalization

Ver `docs/design/generative-ui-personalization.md` para el diseno completo.

### Nivel 2 — Widgets anclables
- [ ] El chat genera artefactos OpenUI que el usuario puede anclar en su dashboard
- [ ] Tabla `user_dashboard_widgets` con programas OpenUI persistidos
- [ ] El dashboard renderiza widgets con el mismo `<Renderer>` de las lecciones

### Nivel 3 — Agente proactivo
- [ ] Cron que analiza patrones de uso (learning_events, llm_usage_log)
- [ ] Propone widgets, ajustes de sidebar, contenido adicional
- [ ] Notificacion no intrusiva: el buddy lo sugiere, el usuario acepta o rechaza

---

## Principios

1. **Calidad primero.** No anades features sobre una base rota.
2. **El usuario no configura.** La app aprende de el.
3. **OpenUI Lang es el motor.** Lecciones, widgets, dashboards — todo son programas OpenUI.
4. **El agente tiene tools, no opiniones.** Solo actua cuando se lo piden o cuando los datos lo justifican.
