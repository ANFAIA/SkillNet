# Experimento: selección progresiva sobre los 34 Didact

Fecha: 2026-08-12. Arnés offline, determinista y aislado de producción.

## Pregunta

¿Podemos mantener disponibles los 34 componentes sin entregar sus 34 contratos completos
en cada generación, y ampliar la búsqueda solo cuando la primera propuesta sea pobre?

Se compararon 13 temas, dos perfiles y cinco semillas (130 observaciones emparejadas por
estrategia):

- **Baseline `fixed-top5`:** recupera cinco descriptores y compone con uno o dos.
- **`progressive-34`:** prueba top 3; si el proxy de riqueza no alcanza 0,92, prueba top 5;
  si todavía no alcanza el umbral, un productor especializado examina el inventario
  completo de 34 y busca un complemento con una función educativa ausente.

Los hard gates solo comprueban que exista material fuente suficiente para construir los
campos obligatorios. No se elimina un componente por complejidad, por no tener hoy un
adaptador o por no pertenecer a una shortlist fija.

## Resultados

| Métrica | Top 5 fijo | Progresivo 34 |
|---|---:|---:|
| Calidad proxy media | 91,46 | **94,27** |
| Adecuación a preferencias | 53,9 % | **66,7 %** |
| Adecuación al tema | 94,9 % | **98,7 %** |
| Cobertura de acciones | 98,7 % | 98,7 % |
| Cobertura de evidencia | 100 % | 100 % |
| Entropía de selecciones | 4,239 bits | **4,393 bits** |
| Tipos distintos finalmente seleccionados | **13** | 12 |
| Unidades medias de contexto | **5,0** | 24,96 |
| Unidades proxy de latencia | **5,0** | 43,27 |

Distribución de fases del progresivo:

- top 3: 35/130 (26,9 %);
- expansión a top 5: 25/130 (19,2 %);
- productor especializado sobre los 34: 70/130 (53,8 %).

No hubo rechazos por hard gates en este fixture. Los 34 componentes fueron realmente
considerados en 70 ejecuciones; en las demás no hizo falta abrir el catálogo completo.

## Lectura

El experimento apoya **disponibilidad completa con contexto progresivo**, no un catálogo
permanentemente reducido. Mejora calidad, ajuste al tema, preferencia y variedad de
combinaciones, pero el coste proxy aumenta mucho porque el umbral 0,92 activa el productor
completo en más de la mitad de los casos.

También evita una conclusión demasiado cómoda: el progresivo seleccionó 12 tipos distintos
frente a 13 del baseline. Su variedad combinatoria fue mayor, pero no maximizó cobertura del
catálogo. Si queremos descubrir componentes infrarrepresentados, hará falta una política de
exploración/novelty explícita, sin convertir la novedad en el objetivo educativo.

## Decisión que todavía no se toma

No se activa este flujo en producción con estos números. El siguiente ensayo debe usar
generaciones reales pequeñas y medir latencia de pared, tokens, validez del contrato,
calidad pedagógica ciega y preferencias causales. También conviene probar umbrales entre
0,82 y 0,92 y recuperar por familias/productores antes de abrir los 34 contratos.

El resultado completo y auditable está en `report.json`. El arnés vive en
`apps/skillnet-api/scripts/didact_progressive_selection_bench.py` y no modifica el runtime.
