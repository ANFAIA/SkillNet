---
title: "Coordinación multiagente"
order: 57
section: "research"
group: "multi-agent"
---

# Coordinación Multiagente

## Un problema nuevo

Está ocurriendo un cambio de paradigma. Los agentes de codificación con IA generan cantidades enormes de código. Proyectos que solían tardar semanas aparecen en horas. Los repositorios crecen más rápido de lo que cualquier equipo puede revisar. Las plataformas de hosting alcanzan límites de tasa porque los agentes hacen demasiadas peticiones. Los repos se rompen bajo el volumen de cambios automatizados.

Esta es la realidad de trabajar con agentes hoy, y funciona razonablemente bien para **una persona con un agente**. Pero en el momento en que se escala a un equipo (múltiples personas, cada una con su propio agente, trabajando sobre la misma base de código o base de conocimiento), todo se desmorona. ¿Qué agente tiene prioridad? ¿Qué pasa cuando dos agentes modifican el mismo fichero? ¿Cómo se evita que el agente de una persona acceda al contexto privado de otra?

No existe un sistema para esto. Git rastrea cambios de código pero no sabe nada de la intención del agente. RBAC controla el acceso a recursos pero no al contexto de conocimiento. MCP conecta agentes a herramientas pero no dice nada sobre la coordinación entre agentes. La brecha es la **gobernanza para equipos de agentes**.

Esta investigación explora esa brecha, desde el problema específico de la autoridad ("¿de quién es este agente?") hasta la pregunta más amplia de cómo múltiples humanos y múltiples agentes coexisten en proyectos compartidos.

---

## Explorando estructuras organizativas

La primera pregunta fue: **¿qué estructuras usa la gente en el mundo real para organizar la autoridad?** Exploramos varios modelos para ver cuál encaja con la realidad de múltiples humanos trabajando con múltiples agentes.

**Árboles (jerarquías).** El modelo más simple. Un jefe arriba, ramas debajo. Pero los agentes no tienen un único jefe. Cuando dos personas usan el mismo agente, el árbol se rompe porque un nodo no puede colgar de dos padres.

**Grafos.** Más flexibles que los árboles porque permiten múltiples conexiones. Pero un grafo por sí solo no dice nada sobre autoridad, permisos, o quién decide qué. Es una estructura de datos, no un modelo de gobernanza.

**Holones.** Una estructura recursiva donde cada humano es la raíz de su propio árbol, con agentes ramificándose debajo. Tres puntos de interacción: declarar intención, aprobar promoción, decidir por excepción. Esto parecía prometedor porque resuelve el cuello de botella por diseño. Se entra por tres puntos, no vigilando una pantalla.

Pero los holones se rompen en el momento en que un subagente sirve a dos usuarios. Un árbol con un nodo colgando de dos padres no es un árbol. "¿De quién es este holón?" no tiene respuesta, y sin un dueño: ¿quién aprueba sus promociones? ¿bajo qué permisos opera? ¿a quién escala?

## El descubrimiento: mandatos sobre propiedad

La exploración llevó a una constatación clave. El error fundacional en todas estas estructuras era modelar la autoridad como **pertenencia** (el agente es propiedad de alguien) cuando debería modelarse como una **relación** (el agente actúa en nombre de alguien, para un propósito específico).

- "¿De quién es?" fuerza un único dueño.
- "¿En nombre de quién actúa, y para qué propósito?" admite múltiples principales sin contradicción.

La unidad primaria de diseño se convierte en el **mandato**: en nombre de quién actúa este agente, con qué permisos, hacia qué objetivo, dentro de qué límites.

- Un agente puede llevar **múltiples mandatos** simultáneamente.
- Un subagente que sirve a dos usuarios lleva dos mandatos, uno de cada uno.
- Su **autoridad es la intersección** de lo que ambos mandatos permiten.

| Concepto | Con Mandatos |
|---------|---------------|
| **Permisos** | Intersección de mandatos, no herencia de un dueño |
| **Promoción** | Aprobada por todos los principales afectados, no un único dueño |
| **Escalación** | Escala a quien corresponda según qué mandato disparó la excepción |
| **Estructura** | Una red de mandatos, no un árbol con un vértice humano |

### El Límite Irreducible

Cuando dos mandatos se contradicen (A quiere una cosa, B quiere lo opuesto), la intersección de permisos no dice qué hacer, solo qué está permitido. La arquitectura distribuye permisos y detecta conflictos, pero **no decide entre voluntades opuestas**. Eso sigue siendo cosa de los humanos. El mismo problema que enfrenta cualquier mediador humano.

### Representación Formal (Abierto)

¿Cómo deberían representarse formalmente los mandatos?

- **Tupla:** `(principal, agente, objetivo, permisos, límites)`
- **Grafo:** Los nodos son agentes y humanos, las aristas son mandatos con atributos
- **Contrato:** Un documento declarativo que especifica términos

La unidad de versionado se desplaza en consecuencia: no el artefacto (Git) ni la intención sola, sino el **mandato** (quién autorizó qué, para qué propósito, dentro de qué límites).

### Trabajo Asíncrono

El modelo de "un humano vigilando una pantalla" es un artefacto de diseño, no una ley natural. La alternativa: los agentes se ejecutan en segundo plano, entregan resultados con resúmenes jerárquicos (visión general de 10 segundos -> detalle de 1 minuto -> traza completa), una bandeja de decisiones pendientes, y escalación por excepción. El humano se convierte en un director que revisa por lotes y decide en los puntos de bifurcación.

> "Un resumen es una compresión con pérdida. Quien controla qué se comprime controla qué se revisa." La traza completa debe estar siempre disponible.

---

## Parte 2: Acceso Compartimentado

### El Problema

Múltiples personas trabajan con múltiples agentes. No comparten toda su base de conocimiento. Los solapamientos son asimétricos:

```
Persona A:  conoce {X, Y}
Persona B:  conoce {X}
Persona C:  conoce {X, Y, Z}
```

Los modelos de fábrica (árbol jerárquico) fallan porque los solapamientos no son jerárquicos. Los modelos de sala limpia (centro compartido) fallan porque no hay centro.

### Tres Ejes

**1. Compartimentos (necesidad de saber): ESENCIAL.** Horizontal y no jerárquico. Un compartimento es un cuerpo de conocimiento etiquetado. El acceso no se concede por rango o confianza, sino porque la tarea específica lo requiere.

**2. Diseminación: AÑADIR CUANDO SE NECESITE.** Direccional. Una pieza del compartimento X puede llevar una etiqueta "compartible con Persona B" o "no sale de mi dominio." Solo se necesita cuando hay excepciones dentro de un compartimento.

**3. Nivel de Habilitación: PROBABLEMENTE NO NECESARIO.** En la mayoría de escenarios multiagente, el problema es de particiones (quién sabe qué), no de grados (cuán secreto es algo).

### Traducción a Sistemas de Agentes

**Arranque (Read-In).** Lanzar un agente solo con los compartimentos que su tarea requiere. **Ventaja sobre los humanos:** un agente puede instanciarse sin acceso a cierto conocimiento. La necesidad de saber se vuelve perfecta, no aproximada.

**Frontera (Aduana).** Cuando el agente emite algo hacia afuera, un punto de control verifica las etiquetas de diseminación. **Crítico:** esta verificación vive en la FRONTERA, no dentro del agente. No se puede confiar en que un agente probabilístico se autocensure de forma fiable.

**Registro (Auditoría).** Cada cruce deja una traza: qué pieza, qué etiqueta lo autorizó, en qué dirección.

```
El control NO está dentro del agente (poco fiable).
Está en el ARRANQUE (lo que puede ver) y en la FRONTERA (lo que puede emitir).
El agente en medio puede ser tan inteligente y falible como quiera.
```

### Modelo Mínimo Viable

```yaml
---
compartment: project_research
---
```

Piezas etiquetadas con compartimentos + agentes con compartimentos permitidos + filtro en tiempo de arranque + aduana en la frontera. Solo eso proporciona control de acceso asimétrico.

---

## Parte 3: Cinco Protocolos de Gobernanza

Cinco protocolos cubren toda la superficie de gobernanza, listados en orden de prioridad de implementación.

### Protocolo 1: Compartición. Qué Cruza Entre Agentes y Personas

**Prioridad: CRÍTICA. Estado actual: existe la capa dura (DBP). La capa blanda sigue abierta.**

La frontera entre compartimentos es un filtro adaptativo:

| Nivel | Qué Sucede |
|-------|-------------|
| PASA | Cruza tal cual |
| PASA REDACTADO | Cruza con los datos sensibles eliminados |
| PASA RESUMIDO | Cruza la conclusión, no el detalle |
| PASA CON AVISO | Cruza pero queda registrado |
| PREGUNTA | Escala al humano |
| BLOQUEA | Solo en casos claros e irreversibles |

**Implementación de Dos Capas:**

```
Capa dura (escáner):        Filtro determinista por etiquetas -> rápido, gratuito, fiable
Capa blanda (agente de aduana): Agente que revisa lo que pasa -> detecta agregación, matices
```

**Implementación:** [DBP (Data Boundary Protocol)](https://github.com/JoseEstevez520/DBP) proporciona la capa dura: verificaciones deterministas de etiquetas + habilitación en la frontera, con herencia automática para datos derivados. La capa blanda (agente de aduana) y la gobernanza multiusuario siguen abiertas.

### Protocolo 2: Conocimiento. Qué Sabe Cada Agente

**Prioridad: CRÍTICA. Estado actual: _context.md y skills (parcial).**

Define qué compartimentos puede acceder un agente y qué contexto se excluye deliberadamente. Un revisor de código con la pizarra limpia juzga mejor que uno cargado con el razonamiento del autor. La exclusión deliberada es una decisión de diseño, no un error.

### Protocolo 3: Trazas. Qué Se Registra

**Prioridad: Importante. Estado actual: agentvcs (un solo usuario) + git.**

Registra qué hizo el agente, por qué, qué leyó, qué compartió, y qué etiqueta autorizó cada cruce. Necesidades multiusuario: trazas de acceso, trazas de diseminación, trazas de mandato.

### Protocolo 4: Identidad. Quién Es Cada Agente

**Prioridad: Útil. Estado actual: AGENTS.md y skills.**

Lo que falta: una identidad formal que persista entre sesiones y que otros agentes o sistemas puedan consultar.

### Protocolo 5: Escalación. Cuándo Preguntar al Humano

**Prioridad: Útil. Estado actual: Hooks y aprobación de llamadas a herramientas.**

Escalar cuando: la información no está etiquetada, se sospecha agregación, los protocolos entran en conflicto, o una acción es irreversible. Lo que falta: criterios claros y escalación asíncrona cuando el humano no está presente.

---

## Fiabilidad Mediante Aislamiento

Cuando los subagentes son independientes, las tasas de error **se multiplican**:

```
1 agente con 1% de error:    tasa de fallo del 1%
3 agentes independientes:    0.01 x 0.01 x 0.01 = tasa de fallo del 0.0001%
```

La palabra clave es **independientes**: no comparten contexto. Si el revisor leyó el mismo material que el autor, carga el mismo sesgo.

El modelo de compartimentos se motivó inicialmente por el control de acceso. Pero el aislamiento que crea tiene una segunda propiedad: hace que la verificación sea genuinamente independiente. **El aislamiento no es una limitación de seguridad. Es lo que hace que la verificación funcione.**

**Advertencia:** la multiplicación de errores solo se sostiene bajo independencia real. Los sesgos de datos de entrenamiento compartidos o los modos de fallo correlacionados elevan la tasa real de fallo conjunto por encima de la multiplicación ingenua.

---

## Lo Que Ya Existe (Informalmente)

```
CLAUDE.md    -> protocolo de identidad + conocimiento
AGENTS.md    -> protocolo de identidad (capacidades)
_context.md  -> protocolo de conocimiento (compartimento del proyecto)
Skills       -> protocolo de conocimiento (por tarea)
"No tocar"   -> protocolo de compartición (frontera dura informal)
Hooks        -> protocolo de escalación (validación determinista)
Segundo plano -> trabajo asíncrono (parcial)
Subagentes   -> fiabilidad mediante aislamiento (parcial)
```

Funciona para un usuario. No escala a equipos.

## Brecha de la Industria

| Existe Hoy | No Existe |
|-------------|----------------|
| RBAC (permisos basados en roles) | Compartimentos por tarea para agentes |
| Scopes de OAuth | Aduana adaptativa entre agentes |
| agentvcs (un solo usuario) | Necesidad de saber aplicada al contexto del LLM |
| MCP (herramientas) | Control sobre qué conocimiento ve un agente |
| LangGraph (orquestación) | Gobernanza multiagente multiusuario |

## Trabajo relacionado

[agentvcs](https://github.com/EvolvingAgentsLabs/agentvcs) (Apache-2.0) explora el versionado para agentes autónomos. Cubre el caso de un solo usuario con un solo agente; el problema de coordinación multiusuario descrito aquí es una capa distinta.

[DBP (Data Boundary Protocol)](https://github.com/JoseEstevez520/DBP) (Apache-2.0) implementa el modelo de frontera determinista explorado en esta investigación. Proporciona compartimentos basados en etiquetas, verificaciones de frontera por inclusión de conjuntos, herencia, trazas de auditoría inmutables, y escalación para anulación humana. Ver el [documento de comunicación entre agentes](/docs/multi-agent-communication) para el modelo conceptual y el repo de DBP para la implementación de referencia.

## Preguntas Abiertas

1. ¿Cómo deberían representarse formalmente los mandatos? ¿Tupla, grafo, o contrato?
2. ¿Cómo se detectan los conflictos de mandatos antes de que ocurran?
3. ¿Quién arbitra mandatos contradictorios?
4. ¿Los mandatos son estáticos o evolucionan a medida que avanza el trabajo?
5. ¿Cómo escala de 2 usuarios a 500?
6. ¿Cómo se integra con agentvcs?
7. ¿Los compartimentos se corresponden con unidades de trabajo o con fuentes de conocimiento?
8. ¿Cómo se maneja la agregación, específicamente cuando las piezas A y B son individualmente inocuas pero revelan algo sensible combinadas?
9. ¿Qué formato deberían tener las trazas?

---

## Profundización

- [Comunicación entre agentes](/docs/multi-agent-communication) · cuando mi agente habla con el de mi vecino, qué puede cruzar · haciendo que la frontera sea determinista en lugar de una norma consultiva, a través del protocolo, la trazabilidad, y el espacio de trabajo.
