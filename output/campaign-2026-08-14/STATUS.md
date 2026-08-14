# Estado de la campaña — 14 de agosto de 2026

## Ronda heredada

`output/agent-round-1` no es evidencia válida: los seis recorridos terminaron con cero cursos porque
el título configurado no existía en la API activa. El arnés tampoco marcaba esa ausencia como error.
Los modelos nombrados eran ejecutores QA del mismo script, no tratamientos del pipeline de SkillNet.

## Cambios de instrumentación

- El arnés falla de forma visible si no resuelve todos los cursos solicitados.
- Conserva la respuesta inicial de `/render` para distinguir generación forzada de caché.
- El analizador separa recorridos, perfiles, similitud dentro del brazo y similitud entre brazos.
- Los tratamientos usan valores aceptados por la API (`experienced`, `textual`).

## R0 — smoke: superada

- 1 curso resuelto, 1 pantalla, 0 errores.
- Petición inicial no servida desde caché.
- Primer indicio de exceso de contenido: 1.102 caracteres y diez pasos en una pantalla.

## R1 — ablación causal: completada

- 5 perfiles × 3 repeticiones × 3 nodos = 45 pantallas.
- 0 errores y 0 peticiones iniciales servidas desde caché.
- Las 45 pantallas usaron la misma receta: `Stack`, `TextContent`, `StepSequence`, `Flashcard`.
- Similitud media dentro del mismo brazo: 0,7103.
- Similitud media entre brazos: 0,6908.
- Longitud visible media total: 980,8 caracteres; máximo: 1.102.
- `short_blocks`: 1.008 caracteres de media frente a 952,9 del perfil base.

Conclusión: no hay personalización estructural en esta muestra. La señal textual específica del
perfil es pequeña frente a la variación de muestreo, y `short_blocks` no cumple su efecto esperado.

## R2 — hallazgo bloqueante antes de ejecutar

El runtime Didact actual evita `QuizItem`. Las actividades Didact evaluadas emiten telemetría y
devuelven feedback, pero `/activities/{id}/evaluate` no actualiza mastery. La transición pedagógica
solo está implementada en `/nodes/{id}/answer`, que requiere un `QuizItem` servido.

Conclusión: hoy no existe un recorrido live Didact que permita demostrar «respuesta incorrecta →
mastery → replanificación». Antes de ejecutar R2 hace falta una decisión de producto y un puente
seguro entre evidencia Didact evaluada y `transition_on_answer`.

Verificación focalizada:

- Backend: 45 pruebas pasadas (`test_activity_definitions.py` y `test_runtime_assessment.py`).
- Frontend: 16 pruebas pasadas de `DidactActivityBlock.test.tsx`, incluida la expectativa explícita
  de completar una evaluación sin reclamar mastery.
- Una ejecución accidental de toda la suite frontend dejó 582/583 pruebas correctas y un fallo ajeno
  en `DidactSafeBlocks.test.tsx` por permanecer en el skeleton asíncrono; el archivo focalizado pasó.

## Próxima decisión

1. Diseñar e implementar el puente Didact → intento de nodo → mastery, con idempotencia y sin confiar
   en puntuaciones aportadas por el cliente.
2. Después ampliar el arnés y ejecutar R2.
3. Mantener R3 (telemetría total) y R4 (viewport/regresión) como rondas independientes.
