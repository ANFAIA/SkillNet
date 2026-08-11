# Informe E2E de personalización

Fecha: 2026-08-11  
Rama: `feat/notebook-media`  
Entorno: API/DB/Ollama Docker, frontend Vite `http://localhost:5174`

## Veredicto ejecutivo

La personalización existe y se percibe sobre todo en la **estructura y el formato**, pero el
encuadre semántico por rol es todavía flojo. En cuatro nodos comparables Aitana (novata, focus,
short blocks) y Diego (experto, perfil caliente) obtuvieron una similitud textual media de
`0,4233` y formatos distintos en 3/4 nodos. Sin embargo, sus puestos concretos no aparecen en
2.720 de 3.081 caracteres analizados; las diferencias son difíciles de atribuir a una señal
concreta porque el contraste mezcla rol, experiencia, preset, accesibilidad y calibración.

La hipótesis «solo `user.md`» no funciona con el diseño actual: `memory_md` no entra en el prompt
de render. Inyectar la prosa directamente sería inseguro con una caché compartida. Se recomienda
mantener señales estructuradas mínimas y usar memoria narrativa en el tutor; si más adelante entra
en generación, debe convertirse antes en un bucket semántico allowlisted, versionado y presente
en la clave de caché.

## Matriz de personalización observada

| Dimensión | Aitana | Diego | Veredicto |
|---|---|---|---|
| Tono inicial | «ponerte al día en tu puesto» | «dominar lo que viniste a resolver» | Personaliza y se nota |
| Apertura, contenido | Tabla de 5 comprobaciones | Tabla de 4 comprobaciones | Difiere, atribuibilidad parcial |
| Apertura, evaluación | Test de fondo de caja | Test distinto sobre primera revisión | Personaliza pero flojo |
| Formato (4 nodos) | Varios formatos | Formato distinto en 3/4 | Personaliza y se nota |
| Profundidad | Media 678,5 caracteres | Media 768,8 caracteres (+13,3 %) | Coherente con experiencia, no causalmente aislado |
| Rol/sector explícito | No menciona «camarero/novata» | No menciona «encargado» | No personaliza de forma visible |
| `short_blocks` | 5 filas en apertura | 4 filas en apertura | Resultado contrario a la expectativa local |
| Tutor | Respuesta contextual no evaluada | Reconoce «como encargado», con grounding | Personaliza pero con ruido |

Comparaciones API completas: [`api-sweep/report.md`](evidencia-testing/2026-08-11/api-sweep/report.md)
y [`api-sweep/sweep.json`](evidencia-testing/2026-08-11/api-sweep/sweep.json).

## Qué enseña y variedad

- El nodo «Apertura del turno» está anclado al protocolo fuente: reservas, montaje, TPV/fondo de
  caja y briefing. No se observó relleno temático ajeno en la lección.
- La separación tabla → ejercicio cumple «una idea por pantalla» en Aitana. Diego recibió tabla y
  evaluación separadas, pero el contenido de la tabla es casi el mismo con redacción distinta.
- En cuatro nodos comparados el formato divergió en 3: `explanation→mixed`,
  `explanation→mixed`, `exercise→explanation`; el cuarto permaneció `explanation`.
- La respuesta incorrecta permite `Reintentar`; tras responder correctamente aparece
  `Siguiente nodo` y no obliga a repetir. Regresión E2E superada.

## Experimentos

### Fuerza actual del prompt

Resultado: divergencia estructural alta, personalización semántica baja. La regla de prompt que
pide ejemplos del puesto no basta para que el rol sea reconocible de forma consistente. Antes de
subir su fuerza conviene ejecutar un A/B con perfiles idénticos salvo rol y estimar primero el ruido
del modelo con 3–5 repeticiones del mismo perfil.

### `format_vector` y calibración

Durante los tres primeros nodos su contribución es exactamente cero. Diego está fuera de
calibración (`nodes_completed=4`, bucket `texto:0.5`) y Aitana no; por eso el contraste actual no
permite afirmar cuánto aporta el vector. Debe medirse con un diseño 2×2: estado frío/caliente ×
vector vacío/poblado, manteniendo iguales las demás señales.

### Solo `memory_md`

Descartado como reemplazo directo. La prosa está disponible en estado pero se excluye del prompt
de render para evitar fugas. Un hash completo fragmentaría la caché por usuario; un bucket
semántico seguro vuelve a ser, en la práctica, una señal estructurada. Conservar `memory_md` para
tutor/chat y no retirar mastery, scaffold, error-state ni densidad.

## Bugs encontrados y cambios aplicados

1. **[Crítico] Colisión de caché entre mismo rol y sectores distintos.** El prompt incluía rol y
   sector, pero la clave solo usaba `role_title OR sector`. Se añadió un bucket de caché privado
   que incorpora ambos mediante digest; el bucket legacy del prompt se conserva para no invalidar
   fixtures. Regresión añadida en `tests/test_cache_key.py`.
2. **[Alto] Directiva interna visible en el tutor.** La UI mostraba literalmente
   `ACTION: {"tool":"set_sidebar_collapsed",...}`. El streaming ahora filtra directivas antes de
   emitir tokens, pero conserva el evento de acción. Regresión en `tests/test_chat_gen_ui.py`.
3. **[Medio] Grounding demasiado amplio.** Una pregunta de apertura citó también manuales de
   alérgenos y caja. No se modificó el ranking: requiere evaluación específica de precisión de
   citas antes de ajustar retrieval.
4. **[Medio] Suite de fixtures no reproducible.** La suite completa termina con 2.776 pruebas
   aprobadas y 13 fallos de `test_runtime_graph.py` por claves de fixture LLM ausentes. Los cambios
   dirigidos pasan 121/121.

## Onboarding y experiencia

- Noa completa los cinco pasos: puesto, objetivo, experiencia, preset y accesibilidad.
- El flujo persiste y vuelve al dashboard sin errores de consola.
- Las transiciones animadas mantienen durante ~0,8 s el contenido del paso anterior mientras el
  contador ya cambia; no rompe el flujo, pero puede dar sensación de inconsistencia en equipos lentos.
- El chat de mascota abre y responde; en el nodo probado no se expusieron controles de mute ni un
  elemento de audio, por lo que la promesa «mute silencia pero conserva texto» queda sin evidencia.

## Cobertura y límites

- Se recorrió en navegador el nodo 1 con Aitana y Diego, ejercicio incorrecto/correcto, tutor y
  onboarding completo de Noa; se realizó barrido API conservador sobre los renders ya fijados.
- No se forzaron los tres renders faltantes para evitar gasto y repinneado indiscriminado.
- No se probó el control admin/Overviews: `seed_demo_v2` no crea `admin2` y la contraseña admin se
  obtiene de `ADMIN_PASSWORD`, no de las credenciales del brief.
- Podcast/imagen, mute/TTS y final de curso siguen pendientes de una corrida con proveedor multimedia
  y credencial admin confirmados.

## Evidencia y reproducibilidad

- [Informe HTML](informe-testing-personalizacion.html)
- [Capturas del navegador](evidencia-testing/2026-08-11/browser/)
- [Barrido API](evidencia-testing/2026-08-11/api-sweep/)
- Script reproducible: `apps/skillnet-api/scripts/personalization_sweep.py`. Por defecto es de solo
  lectura; `--force` exige `--confirm-force I_UNDERSTAND`.

Validación final:

- Backend dirigido: `121 passed`.
- Frontend Header: `3 passed`.
- Frontend completo ejecutado por el subagente: `451 passed`.
- Ruff dirigido: sin errores.
- Oxlint: sin errores, 17 avisos preexistentes.

