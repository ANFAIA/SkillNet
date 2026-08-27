---
title: "Visión"
order: 20
section: "start"
---

# Visión

> **Estado: Borrador.** El fundamento filosófico de SkillNet. Este documento explica por qué SkillNet está construido así — no qué hace, sino qué cree.

---

## El problema del software de formación actual

La mayoría de las plataformas de formación están construidas de la misma manera: un admin crea cursos, los empleados los hacen, todo el mundo ve lo mismo. La plataforma no cambia entre el primer empleado y el centésimo. El contenido es estático. La experiencia es fija.

Se ha añadido IA a estas plataformas como una capa encima — un chatbot que responde preguntas, un generador que crea cuestionarios. Pero la estructura subyacente no ha cambiado. El curso sigue siendo el mismo para todos. El panel se ve idéntico. El camino está predeterminado.

**Añadir IA a un sistema estático no lo hace inteligente. Lo convierte en un sistema estático con un chatbot.**

## En qué cree SkillNet

### 1. La aplicación debe aprender del usuario, no al revés

Las plataformas actuales exigen que los empleados se adapten al sistema: aprender la interfaz, seguir el camino, completar los módulos. SkillNet debe adaptarse al empleado: su nivel, su ritmo, sus lagunas, sus preguntas.

Esto no va de opciones de personalización. Va de que el sistema observe cómo trabaja cada persona y se ajuste en consecuencia — sin que se le tenga que indicar.

### 2. La inteligencia vive en la arquitectura, no en el modelo

Un LLM potente es un componente más. La inteligencia real viene de cómo está estructurado el sistema:

- **Memoria** — qué recuerda el sistema de cada persona y de cada empresa
- **Contexto** — qué información está disponible en cada momento
- **Herramientas** — qué puede hacer el sistema, no solo qué puede decir
- **Bucles de retroalimentación** — cómo aprende el sistema de sus propios errores

El modelo es sustituible. La arquitectura es el producto.

### 3. La formación debe construirse a partir de conocimiento vivo, no de cursos estáticos

La documentación de la empresa cambia. Las políticas se actualizan, los procedimientos se revisan, aparecen nuevas normativas. La formación que era correcta el mes pasado puede ser errónea hoy.

SkillNet trata los documentos fuente como la única fuente de verdad. Los cursos y manuales se derivan de ellos, no son artefactos independientes. Cuando la fuente cambia, la formación se adapta.

### 4. El mismo conocimiento debe producir experiencias distintas para personas distintas

Dos empleados que leen el mismo manual no deberían hacer el mismo curso. Uno es nuevo y necesita fundamentos. El otro tiene cinco años de experiencia y necesita casos límite. El manual es el mismo — la formación no debería serlo.

Esto no es personalización como característica. Es el comportamiento por defecto de un sistema que entiende quién está aprendiendo.

## Cómo esto moldea las decisiones técnicas

| Decisión | Por qué |
|----------|-----|
| **Pipeline de LangGraph con puntos de control humanos** | La generación de contenido es demasiado importante para automatizarla del todo. El admin es responsable de lo que aprenden los empleados. El sistema propone, el humano decide. |
| **Tres niveles de UI (estático, declarativo, generativo)** | La mayor parte de la app debe ser rápida y predecible (Nivel 1). Donde el contenido varía según el usuario, se usan specs (Nivel 2). Solo se genera HTML completo cuando nada prefabricado encaja (Nivel 3). |
| **RAG condicional (los documentos pequeños van enteros, los grandes se trocean)** | No sobre-ingenierizar problemas que no existen. Una política de 3 páginas no necesita un vector store. El sistema debe ser inteligente sobre cuándo complicarse. |
| **Patrón PageIndex para la recuperación del tutor** | El contenido del curso ya está estructurado (módulos > lecciones). Usar esa estructura en lugar de vectorizarlo todo. Dos consultas SQL + una llamada corta al LLM supera a la búsqueda semántica para preguntas dentro del curso. |
| **Capa de LLM agnóstica de proveedor** | El modelo cambiará. La arquitectura no debe depender de ningún proveedor concreto. Cualquier API compatible con OpenAI funciona. |
| **Autoalojado, una instancia por empresa** | Los datos de formación de la empresa son sensibles. El multi-tenant añade complejidad y riesgo. Una instancia por empresa es más simple y más fiable. |
| **Intentos de ejercicio y eventos de aprendizaje registrados** | No para analítica vanidosa. Sostienen el futuro bucle de aprendizaje: separar preferencia, compromiso y eficacia. La repetición espaciada no está en la hoja de ruta actual; ver [adaptive-learning.md](/docs/adaptive-learning). |

## Qué significa esto para la hoja de ruta

**MVP (ahora):** Generar cursos a partir de documentos. Los empleados los hacen. El admin ve el progreso. El sistema es estático pero está bien diseñado para adaptarse.

**Fase 2:** Agente tutor que se adapta a cada empleado. Estrategias de aprendizaje mixtas que respetan las preferencias de presentación explícitas. Niveles de habilidad que reflejan capacidad real, no solo finalización.

**Fase 3:** Regeneración adaptativa — el sistema identifica módulos débiles a partir de datos reales y los regenera. Contenido vivo que se mantiene sincronizado con la documentación de la empresa.

**Fase 4:** Coordinación multiagente dentro de una empresa. Distintos agentes para distintos roles, compartiendo conocimiento a través de compartimentos estructurados.

Cada fase se construye sobre las decisiones de arquitectura tomadas en la anterior. Nada se añade a martillazos. Todo crece desde el mismo fundamento.

## La tesis en una frase

> SkillNet no es una plataforma que entrega formación. Es un sistema que construye la formación adecuada para cada persona, a partir del conocimiento que ya existe en su empresa.
