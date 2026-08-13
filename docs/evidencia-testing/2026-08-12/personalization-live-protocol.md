# Protocolo: personalización contrafactual on the fly

Estado: banco implementado y validable sin red. Una ejecución fixture prueba el
instrumental, **no** demuestra calidad del modelo. Las conclusiones de producto solo se
promueven después de una tanda online expresamente autorizada y una evaluación ciega.

## Pregunta

Con el mismo nodo, la misma fuente y la misma versión del catálogo, ¿el runtime produce
experiencias distintas cuando cambia información pedagógicamente relevante de la persona,
sin perder hechos, estabilidad, accesibilidad ni validez?

`scripts/personalization_live_bench.py` ejecuta el `run_node_render` real. No copia prompts.
Cruza los diez encargos de `quality_bench.py` con tres perfiles contrafactuales:

- principiante que necesita guía, bloques cortos y recuperación tras errores;
- profesional que practica el procedimiento con apoyo neutral;
- persona experta que quiere revisar excepciones con mayor densidad y rapidez.

Cada celda se repite tres veces. El valor por defecto son por tanto **90 renders**:

`10 nodos × 3 perfiles × 3 repeticiones = 90`.

La sesión en memoria de `quality_bench` no contiene una fila PostgreSQL de knowledge pack.
Para poder evaluar la autoría estricta de actividades, el banco deriva identificadores
opacos y estables de los mismos fragmentos de fuente recuperados. Es una costura explícita:
no altera el texto, pero no mide recuperación ni persistencia del pack. Esas capas conservan
sus bancos propios.

Para comparar estrategias se repite la misma matriz con otro `--strategy-label`. No se
mezclan tandas con modelos, prompts, catálogo o packs distintos.

## Evidencia capturada por render

- perfil de entrada y digest de la fuente;
- prompts exactos de autoría de actividad y generación, además de sus respuestas crudas;
- `plan_trace`, candidatos Didact y shortlist que recibió el prompt;
- `ActivityDefinition` pública materializada y estado de autoría;
- `ui_spec` canónico realmente persistido y servido;
- intentos, reparaciones, fallback, tokens, latencia y coste;
- firma semántica independiente del identificador del usuario.
- distribución del primer candidato, cuota dominante y detector de colapso (≥70 % con
  al menos cinco observaciones).

El inventario incluye una fila auditable para cada uno de los **34 tipos Didact**, incluso
si un componente no fue candidato o todavía está bloqueado por un puerto del host. “No fue
elegido” deja de ser indistinguible de “no existía para el sistema”.

## Gates automáticos

Una estrategia no es promocionable si falla cualquiera de estos mínimos:

1. inventario de exactamente 34 identificadores únicos;
2. ningún candidato fuera del catálogo fijado;
3. la fuente permanece idéntica entre perfiles;
4. cero errores de infraestructura;
5. cada ejecución termina con `ui_spec` válido o fallback honesto y visible;
6. similitud intraperfil de candidatos ≥ 0,50;
7. cambio contrafactual **útil** en ≥ 50 % de los nodos;
8. fallback ≤ 10 % de los renders sin error de infraestructura;
9. si se solicitó autoría rica, al menos 50 % termina en una `ActivityDefinition`
   materializada.

El cambio causal no se acredita por cambiar colores, texto expositivo, `Callout`, orden o
layout. La firma útil solo cambia por una acción distinta del aprendiz, evidencia observable,
política de apoyo servida, profundidad interactiva o una `ActivityDefinition` materializada
distinta. `Stack`, `TextContent`, `Markdown` y `Callout` no forman parte de ella. El JSON
canónico completo se conserva como `superficial_change_rate`, separado y sin poder abrir el
gate. También se excluyen perfil, proyección, prompt y ranking interno: una entrada diferente
que produce la misma experiencia útil cuenta como **cero adaptación**.

## Evaluación ciega

Cada tanda crea un `*-blind.json` con orden aleatorio y códigos `R0001…`. El evaluador ve
objetivo, fuente, `ui_spec` y actividad, pero no ve el perfil ni la estrategia. Puntúa del
1 al 5:

- fidelidad a la fuente;
- adecuación pedagógica;
- utilidad de la adaptación;
- riqueza de la interacción.

La clave perfil/estrategia se abre solo después. Se requieren al menos dos evaluadores;
si difieren en más de dos puntos, un tercero resuelve. Promoción: media ≥ 4 en fidelidad y
adecuación, ≥ 3,5 en adaptación y riqueza, y ninguna contradicción crítica.

## Coste y ejecución

Preflight sin red:

```bash
uv run python scripts/personalization_live_bench.py --plan
```

Con el supuesto conservador configurable de 5.000 tokens de entrada y 1.500 de salida por
render, 90 renders con `groq/llama-3.1-8b-instant` y las tarifas fijadas actualmente en el
banco cuestan aproximadamente **USD 0,0333**. Esto es una estimación, no una factura; el
informe usa los tokens devueltos por el proveedor y marca `n/d` si falta una tarifa.

Fixture local:

```bash
uv run python scripts/personalization_live_bench.py --only extintor --repeat 2
```

Modelo real, únicamente después de autorización explícita:

```bash
uv run python scripts/personalization_live_bench.py \
  --online \
  --model groq/llama-3.1-8b-instant \
  --repeat 3 \
  --strategy-label progressive-34
```

La primera tanda online completa debe ser una calibración, no una decisión definitiva.
Una estrategia se adopta solo si repite el resultado en otra semilla/tanda y mejora al
control sin empeorar gates, p95 de latencia ni coste más allá del presupuesto acordado.
