# Roadmap

> Actualizado: 2026-08-07. Organizado en slices paralelizables. Todos pueden ir a la vez.

---

## Slice 1 — Calidad del contenido generado

Testeable autonomamente: subir PDFs reales, generar cursos, comparar output contra
el documento fuente.

- [ ] Subir PDFs reales de Ticketrona (manual entradas, ecosistema) como fuente
- [ ] Generar cursos desde esos documentos con el pipeline multi-agente
- [ ] Verificar fidelidad: datos coinciden con el PDF, no inventa, no falta nada
- [ ] Verificar componentes: procedimiento -> StepByStepReveal, lista -> Table, etc.
- [ ] Verificar leads: no copian el summary, enganchan
- [ ] Verificar quizzes: preguntas respondibles con info del documento, caso concreto
- [ ] Iterar prompts de Blueprint, Content Writer e Interaction Designer
- [ ] Correr quality_bench con LLM real

## Slice 2A — UX del stepper y visualizacion

- [ ] Transicion al entrar en un nodo: morph con framer-motion (no salto brusco)
- [ ] Transicion al salir del nodo: morph inverso (no desaparicion)
- [ ] Centrado vertical testeado con todos los tipos de bloque
- [ ] Responsive: pantallas pequenas, tablets
- [ ] Spider buddy: posicion en diferentes resoluciones
- [ ] Intro del curso: titulo + outcomes en una pantalla
- [ ] Componentes visuales: animaciones de entrada, feedback de quiz, charts

Normas de diseno (ver `design-system.md` y `motion-system.md`):
- Morph desde el trigger con layoutId (nunca aparicion de la nada)
- Opacity + scale, NUNCA blur
- Secuencial: cada elemento espera al anterior
- Chevrones, no flechas
- Sin spinners: shimmer o pasos con nombre
- Todo fluye: paso a paso, nodo a nodo, curso a leccion

## Slice 2B — Chat del tutor en las lecciones

- [ ] Testear end-to-end: contexto del nodo llega, respuestas relevantes
- [ ] Tono: companero cercano, no bot formal
- [ ] Funciona con auth de empleado (no admin)
- [ ] Reaccion a aciertos/errores del quiz (futuro: como Koji)

## Slice 2C — Idiomas (i18n)

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

### Traduccion de contenido on-demand
- [ ] Regenerar lecciones en el idioma del empleado

---

## Paralelismo

```
Slice 1 (calidad) ──────────────────┐
Slice 2A (stepper UX, transiciones) ├── todos en paralelo
Slice 2B (chat tutor) ──────────────┤
Slice 2C (i18n) ────────────────────┘
                                     │
                            Slice 3A (temas) ── depende de 2C
                            Slice 3B (crear curso)
                                     │
                            Slice 4 (gen-ui, proactivo, traduccion)
```

## Principios

1. **Calidad primero.** No anades features sobre una base rota.
2. **El usuario no configura.** La app aprende de el.
3. **OpenUI Lang es el motor.** Lecciones, widgets, dashboards — todo son programas OpenUI.
4. **El agente tiene tools, no opiniones.** Solo actua cuando se lo piden o cuando los datos lo justifican.
5. **Transiciones morph.** Todo fluye, nada salta. Framer-motion layout animations.
