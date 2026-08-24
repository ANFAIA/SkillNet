---
title: "Aprendizaje adaptativo"
order: 37
section: "extensibility"
---

# Aprendizaje adaptativo y preferencias de presentación

**Fecha:** 2026-08-11
**Estado:** decisión de producto y dirección de diseño; la instrumentación causal descrita aquí no está implementada completa.
**Aplica a:** cursos dinámicos v2, catálogo de componentes y futura librería externa.

## 1. Tesis

SkillNet debe respetar lo que el aprendiz pide y, dentro de esa preferencia, combinar estrategias que
le ayuden a comprender, practicar y transferir el conocimiento.

> El cliente manda sobre la presentación. El sistema adapta la enseñanza, no pelea contra la elección
> del cliente.

Si una persona quiere imágenes, audio, vídeo o texto, debe recibirlos cuando el kit y la fuente puedan
producirlos. La respuesta no es invalidar esa elección, sino **componer**:

```text
preferencia explícita: imagen
    + estrategia: recuperación
    + actividad: identificar errores en una escena
    + feedback: informativo
```

## 2. Cuatro capas distintas

| Capa | Pregunta | Ejemplos | Autoridad |
|---|---|---|---|
| Preferencia explícita | ¿Cómo quiere recibirlo? | imagen, audio, texto, vídeo | El usuario manda |
| Accesibilidad | ¿Qué necesita para operar el contenido? | teclado, contraste, menos movimiento | Restricción dura opt-in |
| Estrategia pedagógica | ¿Qué debe hacer para aprenderlo? | recuperar, explicar, comparar, decidir | Diseñador adaptativo |
| Componente | ¿Qué interacción implementa la estrategia? | choice, ordenación, diálogo, mapa | Catálogo/librería |

Una tabla, imagen o audio son presentaciones. Un test puede implementar recuperación, pero también
puede ser una comprobación superficial. El renderer no conoce por sí solo la intención pedagógica.

## 3. Evolución de `format_vector`

El vector actual (`texto`, `ejercicio`, `codigo`, `dato`) registra afinidad de uso, no aprendizaje.
No se elimina sin datos mejores; se reclasifica como preferencia inferida y se separa del efecto:

```json
{
  "presentation_preferences": {
    "declared": ["image", "audio"],
    "inferred": {"text": 0.3, "exercise": 0.7}
  },
  "learning_effects": {
    "retrieval_practice": {
      "immediate_delta": 0.10,
      "retention_delta": 0.16,
      "transfer_delta": 0.08,
      "samples": 12,
      "confidence": 0.64
    }
  }
}
```

Reglas:

1. Una preferencia declarada prevalece sobre la inferida.
2. La inferencia ordena opciones compatibles; nunca retira la modalidad solicitada.
3. `learning_effects` no se actualiza con clics aislados; necesita resultados comparables.
4. Engagement, dominio inmediato, retención y transferencia no se colapsan prematuramente.
5. Toda decisión adaptativa registra razón, muestra y confianza.

## 4. Taxonomía educativa

La librería de componentes no debe ser la ontología pedagógica. SkillNet selecciona primero la
función educativa y después pide a la librería un componente capaz de implementarla.

| Eje | Valores iniciales |
|---|---|
| Función | explicar, recuperar, diagnosticar, practicar, transferir, reflexionar |
| Conocimiento | factual, conceptual, procedimental, condicional, interpersonal |
| Acción cognitiva | reconocer, recordar, ordenar, clasificar, explicar, decidir, producir |
| Interacción | choice, text-entry, order, match, dialogue, map, simulation |
| Presentación | text, table, image, audio, video, diagram |

Esto extiende `ContentFunction` de
[`arquitectura-componentes-funcional.md`](arquitectura-componentes-funcional.md): aquella capa
describe la forma de la fuente (`CONTRASTAR`, `PROCEDIMENTAR`); esta añade la acción del aprendiz y
el resultado observable.

## 5. Contrato con la librería externa

Los componentes actuales serán sustituidos gradualmente. El backend no importa nombres internos de
React ni conoce su implementación. El límite es un descriptor versionado:

```json
{
  "component_id": "scenario.dialogue",
  "version": 1,
  "pedagogical_functions": ["practice", "transfer"],
  "knowledge_types": ["conditional", "interpersonal"],
  "cognitive_actions": ["decide", "explain"],
  "presentations": ["text", "audio"],
  "qti_interaction": "extendedTextInteraction",
  "xapi_interaction": "long-fill-in",
  "requirements": ["branching_script"],
  "accessibility": {"keyboard": true, "drag_alternative": null},
  "events": ["started", "answered", "requested_hint", "completed"],
  "props_schema": {}
}
```

- La librería publica catálogo, schemas, renderer y adaptadores de eventos.
- SkillNet conserva política pedagógica, perfil, caché, generación y evaluación.
- `component_id` es estable y versionado; el nombre React no se persiste.
- Renderer antiguo y nuevo conviven hasta tener golden specs equivalentes.
- Un componente declina si faltan datos o media; nunca inventa relaciones ausentes en la fuente.
- QTI/xAPI son mapeos de interoperabilidad, no el modelo interno completo.

Referencias de diseño:

- [QTI 3.0 Best Practices](https://www.imsglobal.org/spec/qti/v3p0/impl)
- [H5P semantics.json](https://h5p.org/semantics)
- [xAPI specification](https://github.com/adlnet/xAPI-Spec)

### Qué se adopta de las referencias y qué no

| Referencia | Uso en SkillNet | Decisión |
|---|---|---|
| QTI 3.0 | vocabulario de interacciones y compatibilidad futura | Mapear; no convertirlo en la IR interna |
| H5P semantics | precedente para schemas declarativos y validables | Inspirar el descriptor; no importar content types |
| xAPI | nombres de interacciones y exportación corporativa | Adaptador de reporting, no modelo pedagógico |
| `dnd-kit` | operación accesible de interacciones de arrastre | Responsabilidad de la librería externa; no añadirlo aquí |
| Ink/inkjs | representación compacta de escenarios ramificados | Evaluar como formato de autoría, sin hacerlo requisito del runtime |
| Sandpack | ejecución aislada para formación técnica | Sólo si aparece un caso real de cursos de código |
| FSRS | planificación de repasos | No adoptar mientras la repetición espaciada esté fuera de alcance |

Estas referencias orientan contratos y pruebas; no justifican añadir dependencias a SkillNet antes
de que la librería externa o un caso de producto las necesiten.

## 6. Estrategias iniciales

- Recuperación: responder sin releer inmediatamente la solución.
- Autoexplicación: explicar por qué una decisión es correcta.
- Comparación: discriminar casos próximos.
- Ejemplo resuelto: especialmente al introducir procedimientos a novatos.
- Escenario de decisión: conocimiento condicional e interpersonal.
- Ordenar/ejecutar: reconstruir procedimientos.
- Mapeo o dibujo: cuando la estructura espacial sea parte real del conocimiento.

Fiorella y Mayer describen ocho estrategias generativas —resumir, mapear, dibujar, imaginar,
autoevaluarse, autoexplicarse, enseñar y ejecutar— como vocabulario, no como obligación de usarlas
todas:

- [Eight Ways to Promote Generative Learning](https://link.springer.com/article/10.1007/s10648-015-9348-9)
- [Improving Students' Learning With Effective Learning Techniques](https://journals.sagepub.com/doi/10.1177/1529100612453266)
- [The Power of Feedback Revisited](https://www.frontiersin.org/articles/10.3389/fpsyg.2019.03087/full)
- [Does Simulation-Based Training Improve Learning?](https://onlinelibrary.wiley.com/doi/10.1111/j.1744-6570.2011.01190.x)

El feedback útil informa qué falló, por qué y cuál es el siguiente paso. Elogio, puntos o un
`Correcto/Incorrecto` sin información no son la unidad que se optimiza.

## 7. Eventos y resultados

Los eventos separan tratamiento, componente y presentación:

```json
{
  "verb": "answered",
  "node_id": "...",
  "strategy": "retrieval_practice",
  "component_id": "assessment.order",
  "presentation": ["image"],
  "result": {"success": false, "attempt": 1, "duration_ms": 42000, "hints": 0},
  "context": {"variant": "B", "exploration": true}
}
```

Resultados separados: engagement, dominio inmediato, retención diferida y transferencia. SkillNet
no inventa repasos artificiales solo para medir: puede obtener evidencia diferida en cursos
posteriores, reintentos, tareas reales o recertificaciones si llegan a existir.

## 8. Experimentos necesarios

### Preferencia explícita + mezcla

Para alguien que elige imágenes, mantenerlas en todas las variantes:

| Variante | Tratamiento |
|---|---|
| A | imagen + explicación |
| B | imagen + recuperación |
| C | imagen + escenario |

Así se aprende qué estrategia ayuda sin desobedecer la preferencia.

### Crossover dentro del aprendiz

Aplicar tratamientos diferentes a objetivos equivalentes y cruzarlos después. Esto reduce la
confusión por dificultad, conocimiento previo y tema.

### Preferencia frente a resultado

Guardar por separado preferencia declarada, uso y resultado. Una discrepancia no elimina la
preferencia: indica que debe mezclarse con otra estrategia.

### Ablaciones del modelo actual

1. Estado frío/caliente con vector vacío.
2. Estado frío/caliente con vector poblado.
3. Mismo estado y rol distinto.
4. Mismo rol y experiencia distinta.
5. Mismo perfil con/sin `short_blocks`.

Medir 3–5 renders del mismo perfil antes de atribuir una diferencia al tratamiento.

### Accesibilidad

Se prueba como conformidad, no como uplift. Toda funcionalidad de arrastre ofrece operación sin
arrastrar, conforme a WCAG 2.2 2.5.7:

- [Understanding Dragging Movements](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html)

## 9. Repetición espaciada

**Fuera de alcance del producto actual.** Los cursos son normalmente cortos y no hay un caso que
justifique scheduler, cola diaria, FSRS, streaks o una tabla de repasos.

Solo se reabre con evidencia de producto: programas largos, recertificación periódica, conocimientos
de seguridad que deban mantenerse meses o contratación explícita de entrenamiento continuo.
Mientras tanto se conservan intentos y eventos, pero no se construye una experiencia de repetición
espaciada. Las menciones antiguas en documentos v1 son planes históricos, no roadmap vigente.

## 10. Orden recomendado

1. Formalizar taxonomía y descriptor versionado de la librería.
2. Mapear los componentes actuales a función, conocimiento, acción e interacción.
3. Separar preferencia declarada de `format_vector` inferido.
4. Instrumentar estrategia, componente, presentación y variante en eventos.
5. Ejecutar pruebas de mezcla manteniendo la modalidad solicitada.
6. Añadir `learning_effects` solo con comparaciones suficientes.
7. Sustituir renderers gradualmente mediante golden specs; no migración big-bang.

La separación ejecutable entre objetivo, misión cognitiva, representación, componente y apoyo, con
sus invariantes de caché y el plan de migración, se define en
[`personalization-architecture.md`](personalization-architecture.md).

Los resultados que justifican estas decisiones, incluidos experimentos revertidos, se conservan en
el [`cuaderno de experimentos de personalización`](../personalization-experiments.md).
