# Estrategia de integración Didact–SkillNet

**Fecha:** 2026-08-12
**Estado:** dirección de trabajo para la integración incremental.
**Ámbito:** catálogo educativo, selección de componentes, recipes y GenUI de nivel 3.

## 1. Punto de partida

Didact ya no es únicamente un conjunto de primitivas visuales. El catálogo declara 24 tipos
educativos diferenciados y dispone de:

- manifests tipados con rol, familias, representaciones, acciones del alumno, propósitos y contextos;
- disponibilidad, madurez y versión por componente;
- esquema de autoría, capacidades, eventos, evidencia pedagógica y accesibilidad;
- mappings QTI/xAPI y dependencias opcionales;
- cinco colecciones editoriales: fundamentos, matemáticas/datos, idiomas, visual/espacial y formación
  corporativa;
- registry y kits para copiar código sin convertir Didact en una dependencia rígida del producto;
- componentes generales como quizzes, matching/sort/categorize, rúbricas, timelines, hotspot,
  práctica generativa, preguntas numéricas e `InteractiveMedia` experimental;
- una dirección explícita hacia plataformas de experiencia: medios interactivos, datos, decisiones,
  simulaciones y creación de artefactos.

SkillNet continúa siendo el primer consumidor exigente, no el criterio de diseño de Didact. La
librería debe seguir siendo general y el adaptador específico vive en SkillNet.

## 2. Decisión principal: catálogo grande, contexto pequeño

El crecimiento del catálogo no debe ensanchar linealmente el prompt. El modelo nunca recibe los 24,
50 o 100 componentes completos. SkillNet resuelve en capas y solo expone una lista corta de
candidatos compatibles:

```text
NodeKnowledgePack
  -> objetivo + misión + evidencia + requisitos disponibles
  -> filtros obligatorios del catálogo
  -> prioridad de colección/contexto
  -> ranking de capacidades y diversidad
  -> shortlist de 3–5 candidatos
  -> productor configura o devuelve Declined
  -> validación de props, evidencia, accesibilidad y ensamblaje
  -> OpenUI on-the-fly
```

Los filtros obligatorios se ejecutan antes de cualquier decisión del LLM:

1. componente disponible y con madurez admitida;
2. misión, propósito y acción del alumno compatibles;
3. representación soportada por la fuente y por las preferencias declaradas;
4. requisitos presentes (`numeric_series`, regiones de imagen, media, grafo de decisiones...);
5. alternativa accesible operable;
6. productor disponible y compatible con el dialecto OpenUI actual;
7. coste, latencia y dependencias dentro del presupuesto;
8. eventos capaces de producir la evidencia requerida por el pack.

Las colecciones son priors editoriales, no listas cerradas. `corporate-training` puede priorizar
práctica, rúbrica, progreso o medios interactivos, pero un componente externo a la colección sigue
siendo elegible cuando sus capacidades encajan mejor.

El ranking final debe favorecer cobertura de misión y evidencia, no novedad visual. La exploración
de componentes poco usados ocurre solo entre candidatos válidos y con rollback medible.

## 3. Frontera de responsabilidades

### Didact posee

- esquema y versión de props;
- renderizado, estado efímero y comportamiento interactivo;
- contrato de respuesta, resultado, feedback y eventos;
- accesibilidad y alternativa equivalente;
- variantes propias del componente;
- lifecycle, dependencias y compatibilidad técnica;
- recetas generales que demuestran reutilización en varios dominios.

### SkillNet posee

- objetivo, misión cognitiva y hechos obligatorios del curso;
- `NodeKnowledgePack` y evidencia que debe obtenerse;
- proyección de personalización y preferencias declaradas;
- política de selección, coste, privacidad y caché;
- disponibilidad de datos, media y servicios;
- elección de productor y fallback;
- interpretación de eventos como progreso o dominio;
- composición de la pantalla y distribución del aprendizaje entre nodos.

El adaptador traduce manifests de Didact a descriptores de SkillNet. No copia manualmente nombres en
`shape.py`, prompts o agentes. El plan congela `component_id@version`, capacidades, productor,
requisitos, eventos y modelo de estado antes de generar la pantalla.

## 4. Recipes, variantes y componentes especializados

Un caso de curso específico es una **recipe** por defecto. Puede combinar configuración, contenido,
tema, assets y reglas de feedback sin crear otro export público.

Se crea un componente nuevo únicamente cuando aporta al menos una diferencia estructural:

- nueva representación del conocimiento;
- nueva acción significativa del alumno;
- modelo de estado o respuesta diferente;
- validación o feedback propios del dominio;
- contrato de accesibilidad específico;
- composición estable de varias interacciones que deba reutilizarse.

Cambiar textos, ejemplos, sector, dificultad, imagen, estética o dataset no justifica otro componente.
Eso pertenece a props, variantes o recipes. Una recipe que se repite en dominios distintos puede
promocionarse a plataforma o molécula reutilizable después de demostrar el patrón.

## 5. Moléculas y GenUI de nivel 3

Una molécula es una experiencia educativa compuesta con contrato propio: coordina varios estados,
acciones, feedback y evidencia, pero sigue siendo declarativa y validable. Ejemplos posibles son un
escenario ramificado, un laboratorio de manipulación, un medio con checkpoints o un entorno de
creación de artefactos.

Esto hace viable GenUI de nivel 3 sin generar código libre:

```text
el modelo NO genera JSX, hooks ni HTML
el modelo SÍ elige una plataforma y genera una configuración versionada
la plataforma controla estados, acciones, solución, feedback y eventos
el validador rechaza configuraciones imposibles antes de renderizar
```

Un componente complejo puede producir una experiencia más rica que una colección de bloques
pequeños porque ofrece profundidad de acción, estados y feedback. La métrica no es el número de
componentes en pantalla, sino:

- affordances educativas distintas;
- estados significativos alcanzables;
- decisiones o manipulaciones que realiza el alumno;
- feedback ligado a la acción;
- evidencia observable;
- transferencia al objetivo del nodo.

La primera plataforma de nivel 3 debe validarse con al menos dos recipes de dominios diferentes. Si
solo funciona para un ejemplo, todavía es una implementación especializada, no una molécula general.

## 6. Integración incremental

### Fase A — Exportador de catálogo

- Leer manifests de Didact mediante un artefacto versionado de build.
- Producir descriptores SkillNet sin importar React en el backend.
- Detectar drift: componente añadido, eliminado, renombrado o con schema incompatible.
- Mantener temporalmente el adaptador legacy como fallback.

### Fase B — Matriz de compatibilidad

Clasificar cada tipo disponible como:

- `FIT_STATIC`: props literales y estado React efímero;
- `FIT_SERVER_EVALUATED`: necesita evaluación autocontenida del backend;
- `FIT_MEDIA`: necesita productor/asset con procedencia;
- `FIT_SIMULATION`: necesita modelo de estado validado;
- `BLOCKED`: falta infraestructura;
- `DECLINED`: no cumple seguridad o contrato OpenUI.

La clasificación se deriva de capacidades y requisitos; no se mantiene como otra lista de nombres
hardcodeados.

### Fase C — Primer conjunto integrado

Integrar pocas capacidades diferentes, no muchos componentes equivalentes. Buenos candidatos para
aprender sobre la frontera son:

- `Hotspot`, por representación espacial y alternativa accesible;
- matching/categorize, por manipulación y scoring;
- `NumericQuestion`, por validación cuantitativa;
- `InteractiveMedia`, por composición, transcript y checkpoints;
- práctica generativa o autoexplicación, por evidencia distinta a un test de elección.

La selección final depende de que el adaptador confirme sus requisitos reales; esta lista no es un
compromiso de implementación.

### Fase D — Resolución acotada

- Resolver candidatos desde misión, representación, acción, requisitos y evidencia.
- Entregar como máximo 3–5 candidatos al productor.
- Registrar filtros, ranking, `Declined` y fallback en `PlanTrace`.
- Añadir versión de catálogo y componente a la caché.

### Fase E — Evals y sustitución

- Golden specs de props y eventos entre bloque legacy y Didact.
- Pruebas de teclado, lector de pantalla, reduced motion y alternativa al arrastre.
- Hechos críticos y evidencia conservados desde pack hasta UI alcanzable.
- A/B por objetivo y perfil, no solo conteo de tipos.
- Retirar el bloque legacy únicamente después de equivalencia o mejora demostrada.

### Fase F — Piloto de nivel 3

- Elegir una plataforma declarativa con estado y feedback propios.
- Crear dos recipes de dominios diferentes.
- Generar configuraciones, nunca código.
- Medir validez a la primera, estados alcanzables, evidencia, latencia, coste y transferencia.
- Mantener fallback a una experiencia de nivel 2 cuando falten datos o infraestructura.

## 7. Métricas que evitan optimizar variedad vacía

Por render:

- cobertura de invariantes y seguridad;
- evidencia requerida realmente obtenible;
- candidato solicitado, elegido y motivo de fallback;
- componente y versión;
- affordances, estados y eventos alcanzables;
- validez al primer intento y reparaciones;
- latencia, tokens y coste;
- accesibilidad y operabilidad;
- diversidad entre objetivos equivalentes, no dentro de una sola pantalla.

Por incorporación al catálogo:

- número de ediciones centrales necesarias;
- porcentaje de nodos donde resulta compatible;
- tasa de selección cuando es candidato;
- tasa y motivos de `Declined`;
- solapamiento con componentes existentes;
- mejora de aprendizaje o evidencia frente al fallback.

La arquitectura habrá funcionado cuando añadir un componente consista en publicar su manifest,
adaptarlo y probarlo, sin modificar detectores, prompts globales ni ensambladores centrales.

## 8. Próximo punto de continuación

La siguiente sesión debe comenzar por un inventario ejecutable Didact → SkillNet, no por copiar
componentes visuales. El entregable inicial es:

1. export versionado de manifests disponibles;
2. adaptador puro a `ComponentDescriptor`;
3. matriz `FIT/BLOCKED/DECLINED` derivada;
4. shortlist de un componente por capacidad nueva;
5. fixtures que demuestren resolución sin enseñar el catálogo completo al modelo.

Después se integra el primer componente real y se repite el banco raw/legacy/Didact con los mismos
packs trazables.
