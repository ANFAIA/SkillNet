# Experimento R1: intención educativa antes de seleccionar componentes

Fecha: 2026-08-12  
Estado: reproducible, offline, no integrado en runtime  
Artefacto completo: `experience-intent-r1.json`

## Pregunta

¿Selecciona Didact experiencias más versátiles y causalmente personalizadas si antes se
expresa la necesidad como un `ExperienceIntent` tipado, en lugar de consultar el catálogo
directamente con el texto del objetivo y del perfil?

La intención no contiene nombres de componentes. Solo declara:

- acciones del alumno;
- evidencia observable;
- política de feedback;
- representación;
- profundidad.

## Diseño

Se compararon dos adaptadores que alimentan **el mismo selector determinista, los mismos
pesos, el mismo top 3 y el catálogo completo de 34 tipos Didact**:

1. `direct`: extrae coincidencias exactas del vocabulario semántico desde el objetivo y
   el perfil en texto libre.
2. `experience-intent`: recibe una intención tipada declarada en el fixture.

El fixture tiene nueve casos: cuatro pares con el mismo objetivo y perfiles distintos, y
un caso que debe rechazarse porque requiere accesibilidad no disponible. Cada selección
se repitió 200 veces para medir el coste local. No se utilizó LLM, embeddings, red ni base
de datos.

## Resultados

| Métrica | Texto directo | ExperienceIntent |
|---|---:|---:|
| Calidad media de cobertura | 59,3% | **84,7%** |
| Cobertura de acciones | 53,7% | **77,8%** |
| Cobertura de evidencia | 50,0% | **83,3%** |
| Cobertura de feedback | 66,7% | **88,9%** |
| Cobertura de representación | 66,7% | **88,9%** |
| Pares cuyo resultado cambia causalmente | 25% (1/4) | **100% (4/4)** |
| Distancia media entre selecciones del par | 0,20 | **0,875** |
| Firmas semánticas útiles distintas | 4 | **6** |
| Entropía semántica útil | 1,92 bits | **2,52 bits** |
| Exactitud del rechazo | 100% | 100% |
| Latencia local p50 | 0,0099 ms | 0,0140 ms |
| Latencia local p95 | 0,0421 ms | 0,0596 ms |

La latencia adicional observada es de decenas de microsegundos y no es material frente a
una generación. Se informa aparte y no forma parte de la puntuación pedagógica.

## Qué aprendimos

El texto directo encuentra temas y algunas preferencias explícitas, pero no representa
bien la diferencia educativa entre, por ejemplo:

- estudiar un procedimiento con explicación progresiva o reconstruirlo sin apoyo;
- ensayar las consecuencias de una decisión o responder una comprobación breve;
- explorar una serie de datos o recibir un ejemplo trabajado;
- construir relaciones o redactar una autoexplicación.

Un contrato previo de experiencia hace que el cambio de perfil produzca cambios
observables en acciones, evidencia, feedback y representación. La variedad obtenida es
además variedad funcional, no una cuenta de widgets diferentes.

El resultado apoya esta arquitectura:

```text
objetivo + proyección del perfil
              ↓
ExperienceIntent sin nombres de componentes
              ↓
selector sobre capacidades Didact
              ↓
shortlist pequeña para OpenUI
              ↓
carga del renderer solo si se utiliza
```

## Límites y amenazas a la validez

- El `ExperienceIntent` es un **oracle humano en el fixture**. Este R1 demuestra el techo
  de la interfaz, no que ya sepamos inferirla automáticamente con esa calidad.
- Son nueve casos curados y no cursos completos.
- La calidad se mide como cobertura de capacidades declaradas, no mediante aprendizaje
  real, evaluación humana de pantallas ni retención.
- Los metadatos Didact todavía agrupan varios tipos bajo manifiestos compartidos; el
  selector no siempre puede distinguir variantes de quiz entre sí.
- La estrategia directa es intencionadamente sencilla y no incluye embeddings. Debe
  compararse después contra una recuperación semántica fuerte.

## Decisión provisional

Mantener `ExperienceIntent` como candidato serio a frontera interna y no exponerlo al
usuario. Todavía no sustituir el selector del runtime.

Siguiente ronda recomendada:

1. comparar tres productores del mismo contrato: reglas, embeddings y LLM pequeño;
2. añadir casos ciegos que no hayan servido para ajustar las reglas;
3. generar pantallas reales con la misma fuente y comparar preservación factual,
   coherencia pedagógica, variedad útil, tokens y tiempo;
4. usar la decisión tipada como explicación auditable de por qué se ofreció cada
   componente.

## Reproducción

Desde `apps/skillnet-api`:

```powershell
.\.venv\Scripts\python.exe scripts\experience_intent_bench.py tests\fixtures\experience-intent-v1.json
```

