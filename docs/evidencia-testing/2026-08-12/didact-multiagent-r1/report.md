# Didact: especialistas por capacidad y árbitro ciego (R1)

Fecha: 2026-08-12. Este experimento es un **proxy offline determinista** y no está
conectado a producción. El resultado completo está en `report.json`.

## Pregunta

¿Podemos mantener los 34 componentes dentro del espacio creativo sin entregar los 34
esquemas a una única llamada, usando agentes pequeños especializados por capacidad?

## Diseño

- Cinco especialistas: contenido, evaluación, media, simulación y determinista. No hay
  un agente por componente.
- Cada especialista ve el mismo `ExperienceIntent`/resumen del pack y **todos** los
  componentes de su partición. La unión auditada de las particiones contiene 34/34.
- Cada especialista puede proponer candidatos o declinar de forma tipada cuando no hay
  compatibilidad dura o el ajuste es débil.
- El árbitro recibe únicamente descriptor, relevancia, grounding, viabilidad de ports,
  riqueza y preferencia. No ve el nombre del brazo ni la identidad del especialista.
- Diez intenciones educativas, con un perfil gemelo por caso para comprobar cambios
  causales. Se comparan selección central completa, especialistas y especialistas con
  expansión.

## Resultados

| Estrategia | Riqueza | Grounding proxy | Cambio causal | Contexto total estimado | Camino crítico paralelo | Declines |
|---|---:|---:|---:|---:|---:|---:|
| Central, catálogo completo | 0,664 | 0,158 | 0,090 | 2.968 | 2.968 | 0 |
| Especialistas + árbitro | 0,628 | **0,258** | **0,133** | 3.789 | **2.085** | 37 |
| Especialistas + expansión | 0,647 | 0,200 | 0,100 | 3.890 | 2.127 | 37 |

La viabilidad de ports fue 1,0 en los tres brazos porque los requisitos se aplicaron
como puerta dura antes de arbitrar. Los declines no significan que los componentes
desaparezcan: indican que una familia no tenía un candidato honestamente compatible
para esa intención y los ports disponibles.

## Lectura

1. **Sí se conservan los 34.** Todos son inspeccionables y recuperables; la arquitectura
   no necesita meter sus 34 contratos completos en una sola llamada.
2. Los especialistas simples mejoran grounding y sensibilidad al perfil, además de
   reducir el camino crítico de contexto un 30%, aunque realizan más trabajo total.
3. La expansión recupera parte de la riqueza perdida, pero diluye grounding y apenas
   mejora la personalización. El umbral fijo de expansión no es suficiente.
4. Ningún brazo es aún ganador: el central es más rico en este proxy, pero también
   introduce componentes prohibidos en varios casos. La siguiente ronda debe premiar
   explícitamente el propósito pedagógico del componente y penalizar candidatos
   prohibidos antes de comparar con modelos reales.

## Decisión provisional

Mantener esta arquitectura como candidato experimental: los 34 en el inventario y
especialistas por capacidad, con un árbitro tipado. No conectarla aún a producción.
Probar después una variante en dos momentos: durante el diseño del curso se presentan
**familias de experiencia posibles** para revisión opcional; durante cada nodo se
materializa la opción elegida o se expande automáticamente si su definición no es
factible. La interfaz debe mostrar intención y experiencia, no una lista técnica de 34
widgets.

## Límites

- Grounding es un proxy de relevancia/evidencia, no una verificación factual.
- Los tokens son estimaciones independientes del tokenizer del proveedor.
- Falta una ronda con salidas de varios LLM pequeños, evaluación ciega de calidad y
  latencia/coste observados.
