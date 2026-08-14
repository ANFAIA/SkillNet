# Campaña dirigida de personalización y aprendizaje

## Estado heredado

La comparación `output/agent-round-1` se clasificó como intento fallido y se retiró. Sus seis recorridos
resolvieron cero cursos porque el brief pedía `Alergenos: informar sin equivocarse`, pero la API
activa contiene `Alergenos: responder y actuar`. Los modelos DeepSeek, GLM, MiniMax, Qwen y Kimi
eran agentes QA que ejecutaban el mismo arnés; no eran los modelos del pipeline de SkillNet. Por
eso sus nombres no constituyen tratamientos experimentales sobre la generación.

## Preguntas que sí puede responder la campaña

1. ¿Cambiar una sola señal del perfil cambia la representación sin alterar los hechos críticos?
2. ¿Una respuesta incorrecta modifica mastery y la planificación posterior de forma observable?
3. ¿Qué tasa de éxito, latencia, tokens, fallbacks y reparaciones tiene el pipeline real?
4. ¿Las pantallas generadas caben en el viewport y funcionan en escritorio y móvil?

## Controles

- Curso fijo: `Alergenos: responder y actuar`.
- Pipeline fijo en las rondas de perfil: `gpt-4o-mini`.
- Un único cambio respecto al perfil base por brazo causal.
- `force=true` para evitar confundir caché compartida con personalización.
- Artefactos por recorrido: `journey.json`; por ronda: `summary.json` y `report.md`.
- Un curso solicitado que no se resuelva invalida el recorrido y debe aparecer como error.

## Rondas

### R0 — smoke

Un perfil base, un nodo. Verifica curso, matrícula, render, captura y respuesta antes de gastar una
ronda completa.

### R1 — ablación causal del perfil

Cinco brazos sobre los mismos tres nodos: base, experiencia, presentación visual, presentación
textual y bloques cortos. Ejecutar al menos tres renders forzados por brazo. Comparar formato,
componentes, texto, hechos críticos, errores, duración y similitud dentro y entre brazos. Esta ronda
evalúa SkillNet, no el modelo del agente que pulsa el arnés. Una sola repetición es solo un piloto.

### R2 — error, mastery y replanificación

Ejecutar primero una respuesta incorrecta y después una correcta con perfiles y estado controlados.
Registrar respuesta del endpoint, mastery antes/después, historial de intentos y siguiente nodo.
El arnés actual solo detecta `QuizItem`; debe ampliarse para actividades Didact antes de declarar
esta ronda válida.

**Hallazgo previo a la ejecución:** la evaluación Didact (`POST /activities/{id}/evaluate`) devuelve
resultado y emite telemetría, pero no aplica `transition_on_answer` ni escribe mastery. Esa transición
solo existe en `POST /nodes/{id}/answer` para `QuizItem`, mientras el runtime Didact evita generarlo.
R2 no puede demostrar adaptación real hasta diseñar e implementar ese puente de forma explícita.

### R3 — telemetría de generación

Agregar tokens de entrada/salida de todos los agentes internos, coste, latencia p50/p95, reintentos,
fallbacks y errores de validación. No aceptar una mejora de calidad sin su coste total.

### R4 — validación visual y regresión

Comprobar viewport sin scroll inesperado, interacción, feedback, consola, escritorio/móvil y las
rutas de entrega v1 y v2.

### R5 — comparación de modelos del pipeline (opcional)

Solo es válida si se cambia `LLM_MODEL` en SkillNet manteniendo el resto fijo. No se sustituye por
agentes QA con modelos distintos. Requiere credenciales disponibles para cada proveedor y un juez
ciego sobre artefactos anonimizados.

## Cierre

La campaña se cierra cuando R1-R4 tengan artefactos reproducibles y conclusiones explícitas. R5
clasifica cada modelo como adoptar, adoptar para casos concretos, mantener en pruebas o descartar.
