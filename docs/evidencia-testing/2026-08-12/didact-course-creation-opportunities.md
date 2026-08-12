# Experimento: oportunidades Didact durante la creación

Fecha: 2026-08-12
Estado: harness aislado; **no conectado a producción**

## Pregunta

¿Ayuda preparar, después del esquema y del knowledge pack, varias experiencias posibles
por nodo sin convertirlas en una pantalla fija ni esconder el resto de la librería?

La restricción del experimento es explícita: los **34 tipos Didact** forman siempre el
universo disponible. La lista de 3–8 elementos es una memoria de trabajo ampliable, no
una whitelist ni una decisión irreversible.

## Encaje en el flujo real

El flujo actual persiste el esquema propuesto y, una vez durable, lanza en segundo plano
la creación de `NodeKnowledgePack`. El punto limpio para este artefacto es inmediatamente
después de que un pack quede listo:

```text
esquema durable
  -> knowledge pack por nodo (hechos y evidencia)
  -> oportunidades Didact por nodo (3-8, ampliables, todavía sin pantalla)
  -> personalización y autoría on the fly
  -> actividad/render final
```

No debe formar parte de `NodeKnowledgePack`: el pack sigue siendo fuente de verdad del
contenido; las oportunidades son una proyección reemplazable y versionada.

## Contrato probado

`NodeExperienceOpportunities` conserva:

- hash del knowledge pack y del catálogo;
- los 34 `catalog_type_ids` considerados;
- 3–8 oportunidades únicas;
- referencias obligatorias a átomos del pack;
- rol pedagógico y códigos de razón;
- puertos necesarios y estado de preparación;
- ejes que el runtime todavía puede adaptar: apoyo, densidad, presentación, recuperación
  de errores y dificultad;
- `expandable=true`, para dejar claro que el runtime puede volver al catálogo completo.

No contiene props finales, texto de la lección, orden de pantallas ni una elección por
perfil. Por eso no congela la personalización posterior.

## Brazos y resultados

Harness: `apps/skillnet-api/scripts/didact_course_creation_opportunities.py`
Fixture: 10 nodos educativos ya usados por el banco Didact.
Pruebas: 5 superadas.

| Estrategia | Opciones/nodo | Cobertura acumulada de los 34 | Diversidad semántica | Cambio posible por perfil | Contexto estimado |
|---|---:|---:|---:|---:|---:|
| relevancia | 5 | 88,2% (30 tipos) | 0,429 | 0,21 | 829 tokens |
| balance relevancia/diversidad | 5 | 67,6% (23 tipos) | **0,624** | 0,38 | 829 tokens |
| exploratoria | 8 | 76,5% (26 tipos) | 0,587 | **0,68** | 1.148 tokens |

En todos los brazos:

- se consideraron los 34 tipos en cada nodo;
- el 100% de las oportunidades tenía referencias de grounding;
- los tipos todavía no ejecutables no desaparecieron: quedaron marcados como
  `needs_host_port` o `needs_authoring`;
- el artefacto siguió siendo pequeño frente a inyectar 34 contratos completos.

## Lectura honesta

La estrategia de relevancia cubre más tipos a lo largo del banco, pero en algunos nodos
produce familias casi idénticas —por ejemplo, cinco variantes de quiz—. Balancear
diversidad mejora mucho la variedad local, aunque reduce la cobertura global. Con ocho
oportunidades se conserva bastante más margen para que dos perfiles terminen recibiendo
experiencias diferentes, con un coste aproximado de 319 tokens adicionales por nodo.

Esto no demuestra todavía cuál genera el mejor curso: es un proxy determinista y no una
evaluación de salidas LLM. Sí demuestra que el paso puede existir sin retirar ninguno de
los 34 componentes ni fijar prematuramente el runtime.

## Propuesta de interfaz para una prueba futura

La generación debería ser automática, sin obligar al creador a pulsar nada. Dentro del
desplegable de cada punto del esquema se podría mostrar:

- “Experiencias posibles (8)” y su estado de generación;
- nombre, rol pedagógico y necesidad técnica de cada posibilidad;
- acción opcional “explorar más”, que vuelve al universo de 34;
- preferencias blandas: favorecer, evitar o dejar decidir a SkillNet;
- ningún componente preseleccionado como pantalla definitiva.

Así el creador puede aportar intención cuando quiera, mientras el camino normal sigue
siendo completamente automático.

## Siguiente ronda

1. Generar las oportunidades con modelos pequeños usando knowledge packs reales.
2. Comparar 5, 8 y expansión progresiva `5 -> 8 -> 34`.
3. Medir calidad pedagógica humana, grounding real, latencia, coste y repetición entre
   nodos; no solo diversidad de metadatos.
4. Probar dos variantes adicionales: propuesta por un solo agente y debate entre agentes
   especializados en pedagogía, medios y simulación.
5. Solo después decidir si el artefacto merece persistencia y UI de producción.
