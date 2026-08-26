---
title: "Cómo funciona md-reader"
order: 60
section: "research"
---

# Cómo funciona md-reader

Referencia técnica de `@anfaia/md-reader-mcp` —el servidor MCP que da a los agentes de IA conciencia estructural de los ficheros Markdown.

Fuente: [`packages/mcp-md-reader/`](https://github.com/ANFAIA/SkillNet/tree/main/packages/mcp-md-reader)

## Visión general

mcp-md-reader es un servidor MCP que reemplaza las lecturas planas de ficheros por navegación consciente de la estructura. En lugar de leer ficheros enteros como texto plano, los agentes navegan árboles de encabezados, extraen secciones individuales y recorren grafos de todo el vault —todo con ~90% menos tokens.

Cinco herramientas. Cero dependencias externas de parseo. Resultados deterministas (sin llamadas a LLM). Parseo puro de cadenas que entiende encabezados, bloques de código, frontmatter y wikilinks.

## El pipeline

Cada petición a una herramienta sigue el mismo camino:

```
fichero .md → Cargador (comprobación de tamaño, detección de binario)
         → Parser (extracción de encabezados, consciente de bloques de código)
         → Árbol (jerarquía HeadingNode[] con estimaciones de tokens)
         → Caché (LRU en memoria + persistencia en disco)
         → Herramienta (md_tree / md_section / md_find / md_frontmatter / md_vault_index)
```

El parser es **consciente de bloques de código**: un `#` dentro de un bloque de código con fences nunca se confunde con un encabezado. Esto es lo que hace determinista el árbol.

## md_tree

La primera herramienta que se llama. Devuelve la jerarquía de encabezados con estimaciones de tokens por sección —así el agente sabe qué hay dentro del fichero y cuánto cuesta cada sección antes de leer nada.

**Entrada:** ruta del fichero
**Salida:** árbol de encabezados anidado con recuentos de tokens

Ejemplo para un fichero de ~820 tokens:

```
File: project.md
Full file: ~820 tokens
This tree: ~50 tokens
Savings: ~93%

# Project Alpha  (~7 tok)
  ## Architecture  (~312 tok)
    ### Database  (~89 tok)
    ### API Layer  (~76 tok)
  ## Deployment  (~64 tok)
  ## Roadmap  (~48 tok)
```

### Cómo se construye el árbol

1. Escanear líneas buscando el patrón de encabezado: `^(#{1-6})\s+(.+)$`
2. Saltar líneas dentro de bloques de código con fences (``` o ~~~)
3. Construir una lista plana de encabezados con nivel, título, lineIndex
4. Asignar lineEnd: el contenido de cada encabezado termina donde empieza el siguiente encabezado (o al final del fichero)
5. Construir la jerarquía usando una pila:
   - Para cada nodo: desapilar hasta encontrar el padre (número de nivel inferior)
   - Si la pila está vacía → nodo raíz
   - Si no → adjuntar al último elemento de la pila (padre)
   - Apilar el nodo

Estimación de tokens: `Math.ceil(content_length / 4)` por sección.

## md_section

Tras ver el árbol, el agente solicita una sección concreta por nombre. La coincidencia es **difusa**: maneja abreviaturas, subcadenas, acrónimos y consultas multi-palabra.

**Entrada:** ruta del fichero + nombre del encabezado (difuso)
**Salida:** contenido de la sección con números de línea y ahorro de tokens

### Algoritmo de coincidencia difusa

El algoritmo se adapta según la longitud de la consulta:

**Consultas cortas (2-3 caracteres):** solo modo de límite de palabra.
- `db` → coincide con "Database" (prefijo de inicio de palabra)
- `API` → coincide con "API Layer" (límite de palabra exacto)
- `no` → **rechazado** (sin coincidencia de límite de palabra —evita el falso positivo de "conocimiento")

**Consultas medias (4+ caracteres):** coincidencia por subcadena.
- `deploy` → coincide con "Deployment" (subcadena, puntuación 0,9)
- `database` → coincide con "Database Design" (subcadena, puntuación 0,9)

**Consultas multi-palabra:** puntuación por solapamiento de palabras.
- Cada palabra coincidente = +0,5 de puntuación base, +0,3 por ratio de coincidencia
- `road map plan` → coincide con "Roadmap" (puntuación 0,65)

Umbral de coincidencia: puntuación ≥ 0,5 (escala 0-1). Devuelve solo la mejor coincidencia.

## md_find

La puerta de entrada para vaults grandes. Toma una consulta en lenguaje natural, la tokeniza, escanea encabezados/etiquetas/nombres de fichero en todo el vault y devuelve resultados ordenados dentro de un presupuesto de tokens.

### Flujo de procesamiento

1. **Tokenizar la consulta:** dividir por caracteres no alfanuméricos, pasar a minúsculas, filtrar stopwords (≥3 caracteres). Stopwords en español e inglés integradas.
2. **Escanear el índice del vault:** comprobar encabezados, etiquetas, nombres de fichero de todos los documentos.
3. **Ordenar por cobertura:** cuantos más tokens de la consulta coincidan, mayor la posición. Relación: dos tokens coinciden si uno contiene al otro O comparten un prefijo de 4+ caracteres (`aislar` ↔ `aislamiento`, `config` ↔ `configuración`).
4. **Tope de presupuesto (~4k tokens):** máximo 12 regiones mostradas, detección de ambigüedad.

### Tres modos de respuesta

- **Normal:** regiones coincidentes ordenadas (≤20 documentos coinciden)
- **Ambiguo:** lista de documentos (>20 documentos coinciden) —el usuario refina la consulta
- **Sin coincidencia:** puntos de entrada centrales (notas más conectadas para explorar)

## md_vault_index

Compila todos los ficheros `.md` en un grafo dirigido donde los nodos son documentos y las aristas son wikilinks. Admite 7 tipos de consulta:

| Consulta | Propósito |
|-------|---------|
| `stats` | Total de nodos, aristas, distribución de tipos |
| `node` | Información completa del nodo (estructura, enlaces, frontmatter) |
| `neighbors` | Recorrido BFS de N saltos (enlaces de entrada + salida) |
| `search_type` | Filtrar nodos por el campo `type` del frontmatter |
| `most_connected` | Los N centros principales por grado total |
| `isolated` | Nodos con cero enlaces de entrada + salida |
| `path` | Camino más corto por BFS entre dos nodos |

### Resolución del ID de nodo

- Por defecto: nombre de fichero sin extensión (en minúsculas)
- Duplicados: ruta completa con `/` → `_` (p. ej., `src_design` + `docs_design`)

### Resolución de enlaces

1. Extraer wikilinks `[[target]]` con soporte de alias
2. Construir un mapa de nombre simple a ID
3. Resolver cada enlace saliente a su ID de destino
4. Rellenar los backlinks (links_in) en los destinos

## md_frontmatter

Lee solo el frontmatter YAML sin el fichero completo. Ahorro típico: 99%.

Admite arrays inline (`tags: [a, b, c]`) y arrays multi-línea. Devuelve `Record<string, string | string[]>`.

## Arquitectura de caché

Caché de dos capas con validación por mtime:

```
Tool Request
  ↓ check
Memory Cache (LRU)          — 100 entries, mtime-validated, ~0.1ms
  ↓ miss → fallback
Disk Cache                   — JSON index, 7-day TTL, survives restarts
  ↓ miss → fallback
Full Parse                   — Read file → extract headings → build tree (~1.6ms)
```

- **Memoria:** desalojo LRU por último acceso. Clave = ruta del fichero. Validación = el mtime del fichero debe coincidir.
- **Disco:** un único índice JSON en `$TMPDIR/mcp-md-reader-cache/`. Máximo 100 entradas, TTL de 7 días. Guarda frontmatter + árbol (JSON), no el texto completo.
- **Caché caliente:** ~4,5x más rápido que un parseo en frío.

## Resumen de ahorro de tokens

| Herramienta | Escenario | Ahorro |
|------|----------|---------|
| md_tree | Solo árbol (fichero de 3k tokens) | ~93-98% |
| md_tree + md_section | Leer 1 sección | ~88-91% |
| md_frontmatter | Solo metadatos | ~99% |
| md_find | Buscar en el vault, leer 1 sección | ~85-88% |

## Rendimiento

| Operación | Tiempo | Escala |
|-----------|------|-------|
| Parsear un único fichero | 1,6ms | 14 ficheros medidos |
| Compilar el índice del vault | 355ms | 699 nodos |
| Consulta media | 0,61ms | Una sola consulta |
| Emparejador difuso | <0,1ms | Por encabezado |

## Stack técnico

| Capa | Tecnología |
|-------|-----------|
| Protocolo | MCP SDK (transporte stdio) |
| Lenguaje | TypeScript |
| Parser | Parseo puro de cadenas (sin dependencias externas) |
| YAML | paquete `yaml` para el frontmatter |
| Runtime | Node.js ≥18 |

Directorios ignorados al recorrer el vault: `node_modules`, `.git`, `.obsidian`, `ATTACHMENTS`, `.mcp-md-reader`.
Tamaño máximo de fichero: 2 MB. Detección de binario: se escanean los primeros 8KB en busca de bytes nulos.
</content>
