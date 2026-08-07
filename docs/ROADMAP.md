# Roadmap

> Actualizado: 2026-08-07. Organizado en slices paralelizables.

---

## Slice 1 — Calidad del contenido generado (BLOQUEA TODO)

Nada importa si los cursos son malos. Se hace primero y solo.

- [ ] Subir PDFs reales de Ticketrona (manual entradas, ecosistema) como fuente
- [ ] Generar cursos desde esos documentos con el pipeline multi-agente
- [ ] Evaluar output: leads, contenido de concepto, preguntas, variedad de componentes
- [ ] Iterar prompts de Blueprint, Content Writer e Interaction Designer
- [ ] Correr quality_bench con LLM real, medir cobertura de componentes
- [ ] Objetivo: first-pass >80%, preguntas de caso concreto, leads que enganchen
- [ ] Probar con temas variados (no solo compliance)

**Criterio para avanzar:** un curso generado desde un PDF real que un empleado de
Ticketrona pueda usar sin que de verguenza.

---

## Slice 2 — En paralelo (despues de que slice 1 sea aceptable)

Tres lineas de trabajo independientes que pueden ir a la vez:

### 2A — UX del stepper y visualizacion

- [ ] Centrado vertical testeado con todos los tipos de bloque
- [ ] Responsive: pantallas pequenas, tablets
- [ ] Spider buddy: posicion en diferentes resoluciones
- [ ] Intro del curso: titulo + outcomes en una pantalla
- [ ] Transiciones entre nodos: fluidas, sin parpadeo
- [ ] Componentes visuales: animaciones de entrada, feedback de quiz, charts

### 2B — Chat del tutor en las lecciones

- [ ] Testear end-to-end: contexto del nodo llega, respuestas relevantes
- [ ] Tono: companero cercano, no bot formal
- [ ] Funciona con auth de empleado (no admin)
- [ ] Reaccion a aciertos/errores del quiz (futuro: como Koji)

### 2C — Idiomas (i18n)

La infraestructura esta montada (react-intl + catalogos es/en + agent tool set_locale).

- [ ] Migrar sidebar, node view, stepper a useIntl() / FormattedMessage
- [ ] Migrar create course, course view
- [ ] Migrar componentes de bloque (quiz, drag, etc.)
- [ ] El contenido de los cursos se genera en el idioma del admin

---

## Slice 3 — Despues de slice 2

### 3A — Temas visuales predefinidos

- [ ] Disenar 3-5 sets de CSS variables (corporate, warm, minimal, dark...)
- [ ] Tool set_theme en el agent para cambiar entre ellos
- [ ] Persistencia en preferencias del usuario

### 3B — Flujo de crear curso

- [ ] Eliminar clicks innecesarios entre crear y probar
- [ ] UX de la creacion: progreso, feedback, preview
- [ ] Chat del admin con tools para modificar esquema (futuro)

---

## Slice 4 — Futuro

Ver `docs/design/generative-ui-personalization.md` para el diseno completo.

### Nivel 2 — Widgets anclables
- [ ] El chat genera artefactos OpenUI que el usuario puede anclar en su dashboard
- [ ] Tabla `user_dashboard_widgets` con programas OpenUI persistidos
- [ ] El dashboard renderiza widgets con el mismo `<Renderer>` de las lecciones

### Nivel 3 — Agente proactivo
- [ ] Cron que analiza patrones de uso (learning_events, llm_usage_log)
- [ ] Propone widgets, ajustes de sidebar, contenido adicional
- [ ] Notificacion no intrusiva: el buddy lo sugiere, el usuario acepta o rechaza

### Traduccion de contenido on-demand
- [ ] Regenerar lecciones en el idioma del empleado
- [ ] O traducir con modelo rapido al vuelo

---

## Paralelismo

```
Slice 1 (calidad) ─────────────┐
                                ├── Slice 2A (stepper UX)
                                ├── Slice 2B (chat tutor)
                                ├── Slice 2C (i18n)
                                │
                                ├── Slice 3A (temas) ── depende de 2C
                                ├── Slice 3B (crear curso) ── depende de 1
                                │
                                └── Slice 4 (gen-ui, proactivo, traduccion)
```

## Principios

1. **Calidad primero.** No anades features sobre una base rota.
2. **El usuario no configura.** La app aprende de el.
3. **OpenUI Lang es el motor.** Lecciones, widgets, dashboards — todo son programas OpenUI.
4. **El agente tiene tools, no opiniones.** Solo actua cuando se lo piden o cuando los datos lo justifican.
