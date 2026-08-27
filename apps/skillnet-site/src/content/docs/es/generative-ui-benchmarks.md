---
title: "Bancos de pruebas de prototipos"
order: 56
section: "research"
group: "generative-ui"
---

# Bancos de Pruebas de Prototipos: Cinco Enfoques de UI Generativa Comparados

Cinco prototipos construidos en paralelo el 6 de julio de 2026. Todos producen HTML autocontenido. Datos de un dataset de benchmark real (1280 documentos, 8 dominios, límites semánticos).

---

## Los Cinco Prototipos

### P1: Nivel Estático (Simulador AG-UI)

El usuario escribe un prompt. El LLM decide qué componentes preregistrados mostrar (gráfico, tarjeta, tabla). Los componentes se renderizan con datos reales.

- 3 componentes registrados: BarChart (Chart.js), MetricCard, DataTable
- 6 prompts rápidos + entrada libre
- El LLM recibe el prompt + el catálogo de componentes, responde con JSON especificando qué componentes y datos
- Fallback por coincidencia de palabras clave si la API no está disponible

**Tokens:** ~200-500 por interacción (solo decisión, sin generación de código)
**Latencia:** <2s (decisión + renderizado local instantáneo)
**Interactividad:** Prompt -> respuesta. Unidireccional.

---

### P2: Generativo Completo (Nivel 3)

El LLM genera TODO el HTML+CSS+JS. Sin componentes preconstruidos. Cada página es única.

Tres páginas generadas con métricas medidas:

| Página | Tokens de entrada | Tokens de salida | Latencia | Caracteres HTML |
|------|-------------|---------------|---------|------------|
| Visión general de arquitectura | 221 | 2,400 | 16.1s | 8,732 |
| Análisis de curva de aprendizaje | 228 | 3,564 | 25.0s | 14,004 |
| Análisis de errores | 295 | 4,065 | 27.7s | 14,430 |
| **Promedio** | **248** | **3,343** | **22.9s** | **12,389** |
| **Total** | **744** | **10,029** | **68.8s** | **37,166** |

**Interactividad:** Ninguna. Páginas estáticas generadas.

---

### P3: Declarativo (A2TL-Web Nivel 2)

Especificaciones A2TL-Web compactas procesadas por un renderizador existente hacia HTML autocontenido. Sin LLM en el proceso de renderizado.

| Spec | Caracteres de spec | Tokens de spec | Caracteres HTML |
|------|-----------|-------------|------------|
| Visión general de arquitectura | 1,967 | 492 | 10,965 |
| Curva de aprendizaje | 1,572 | 393 | 10,419 |
| Análisis de errores | 1,952 | 488 | 10,081 |
| **Total** | **5,491** | **1,373** | **31,465** |

**Ratio de compresión:** A2TL-Web es 5.7x más compacto que el HTML resultante.
**Latencia:** Instantánea (renderizado local, ~100ms).
**Interactividad:** Gráficos interactivos (hover/tooltips de Chart.js), pero no bidireccional.

---

### P4: Bucle Bidireccional

El agente genera UI. El usuario interactúa. La interacción vuelve al agente. El agente genera nueva UI. Ida y vuelta continua.

- Ciclo 0 (local): panel con botones de dominio + botones de análisis + entrada libre
- El usuario hace clic o pregunta -> la acción se envía al LLM con contexto completo + historial (últimos 6 ciclos)
- El LLM genera nuevo HTML con botones/formularios -> se renderiza -> los nuevos botones se conectan automáticamente -> el bucle continúa
- Registro lateral: número de ciclo, acción, tokens, marca de tiempo

**Tokens:** ~3,000-4,000 por ciclo (similar al Nivel 3, pero acumulativo)
**Latencia:** ~20-30s por ciclo
**Interactividad:** Máxima. Cada interacción produce nueva UI. El bucle es infinito.

---

### P5: Vault-to-Page (Pipeline Determinista)

Lee un fichero markdown -> lo convierte a UIDL (determinista, sin LLM) -> el renderizador genera HTML -> se abre en el navegador.

| Paso | Caracteres | Tiempo |
|------|-------|------|
| MD fuente | 6,112 | — |
| UIDL generado | 5,839 | 2ms |
| HTML final | 14,653 | 102ms |
| **Total** | — | **310ms** |

**Tokens de LLM:** 0 (enteramente determinista)
**Ratio MD-a-UIDL:** 0.96x (casi 1:1)
**Ratio UIDL-a-HTML:** 2.51x
**Interactividad:** Ninguna en la página, pero el script acepta cualquier fichero markdown como entrada.

---

## Tabla Comparativa

| | P1 Estático | P2 Generativo | P3 A2TL-Web | P4 Bidireccional | P5 Vault-to-Page |
|---|---------|-----------|---------|------------------|---------------|
| **Nivel** | 1 | 3 | 2 | 3+ (colaborativo) | 2 |
| **Tokens/página** | ~300/interacción | 3,343/página | 0 (o ~458 si el agente genera la spec) | ~3,500/ciclo | 0 |
| **Latencia** | <2s | 22.9s | <0.1s | 20-30s/ciclo | 0.3s |
| **Salida HTML** | Dinámica | 12,389 caracteres/página | 10,488 caracteres/página | Dinámica | 14,653 caracteres |
| **Interactividad** | Prompt->respuesta | Ninguna | Hover en gráficos | Bidireccional continua | Ninguna |
| **Calidad visual** | Consistente (componentes) | Variable (depende del LLM) | Consistente (sistema de diseño) | Variable | Consistente |
| **Predictibilidad** | Alta | Baja | Muy alta | Muy baja | Muy alta |
| **Coste por página** | Bajo | Alto | Cero | Muy alto (acumulativo) | Cero |
| **Requiere LLM** | Sí (decisión) | Sí (generación) | No* | Sí (generación continua) | No |

*La spec de A2TL-Web puede ser generada por una persona o un agente. El renderizador es determinista.

---

## Hallazgos Clave

### 1. El Nivel 2 (A2TL-Web) es 7.3x más eficiente en tokens que el Nivel 3

Para la misma información (visión general de arquitectura, curva de aprendizaje, análisis de errores):
- **Nivel 3:** 3,343 tokens promedio por página (el LLM genera todo el HTML)
- **Nivel 2 A2TL-Web:** 458 tokens promedio por spec (el LLM solo genera la descripción)
- **Ratio: 7.3x** menos tokens con A2TL-Web

### 2. La latencia del Nivel 3 es prohibitiva para la interacción

22.9 segundos para generar una página. El Nivel 2 es instantáneo (<100ms). Para UIs que se muestran una sola vez (informes, paneles), el Nivel 3 es aceptable. Para UIs interactivas, no lo es.

### 3. El bucle bidireccional funciona pero es costoso

P4 demuestra que el concepto es viable: el agente genera UI, el usuario interactúa, el agente regenera. Pero cada ciclo cuesta ~3.5K tokens y ~25s. Para un producto, esto requiere: cachear ciclos anteriores, usar el Nivel 2 (A2TL-Web) en lugar del Nivel 3 para reducir tokens, y pregenerar opciones probables.

### 4. Vault-to-Page es el pipeline más eficiente

0 tokens de LLM. 310ms. HTML funcional. El pipeline MD -> UIDL -> HTML es determinista, predecible y gratuito. Para contenido que ya existe en forma estructurada, no se necesita un LLM. Un buen parser basta.

### 5. La calidad visual del Nivel 3 es inconsistente

Los tres ficheros HTML generados por el LLM son funcionales pero cada uno tiene estilos distintos. El Nivel 2 (A2TL-Web) produce salida consistente porque usa el mismo sistema de diseño (renderer.js). Esto importa para un producto.

---

## Nivel Recomendado según el Caso de Uso

| Caso de Uso | Recomendado | Tokens | Latencia |
|----------|-------------|--------|---------|
| Contenido existente (documentación, cursos) | P5: Vault-to-Page | 0 | <1s |
| Paneles e informes | P3: A2TL-Web generado por agente | ~458 | <1s |
| UI personalizada por usuario | P1: Patrón Estático/AG-UI | ~300 | <2s |
| Exploración libre / tutoría adaptativa | P4: Bucle bidireccional | ~3.5K/ciclo | 25s |
| Demos / de un solo uso | P2: Nivel 3 completo | ~3.3K | 23s |

El enfoque no es un solo nivel para todo. Un agente orquestador decide qué nivel usar según la situación: cuánta personalización se necesita, cuán sensible al tiempo es la interacción, y si el contenido ya existe en forma estructurada.
