# apertura-cierre-caja (raw, pase 1) -> infra_error

- Motivo: [load_context] AssertionError: consulta inesperada en el banco: SELECT node_knowledge_packs.org_id, node_knowledge_packs.course_id, node_knowledge_packs.node_id, node_knowledge_packs.source_fingerprint, node_knowledge_packs.schema_version, node_knowledge_packs.generator_version, node_knowledge_packs.status, node_knowledge_packs.markdown, node_knowledge_packs.atoms, node_knowledge_packs.pack_payloa
- Formato elegido: ? (nivel ?, modelo )
- decide_formato llamo al LLM: no (calibracion, §6.4)
- Justificacion del formato: (ninguna)
- Estado de node_renders: sin fila
- Pasos del grafo: load_context -> fallback_seed
- Segundos: 0.031
- cache_key:
- Contexto: raw_source (e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855)
- Fuente recuperada: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- Atomos seleccionados: (raw)
- Invariantes: (raw)
- Firma UI: (sin spec servido)

## El aprendiz

- Puesto: Encargado de turno (supermercado de proximidad)
- Experiencia: experienced | preset: fast
- Nodos completados: 9 | densidad del curso: 3 | short_blocks: False
- Banda de andamiaje: advanced | maestria: 0.55
- Aciertos/fallos seguidos: 1/0 | ultimo error: None

## El nodo

- Titulo: Arqueo de apertura y cierre de caja
- Criticidad: critical | formato por defecto: exercise
- Fuente entregada al prompt: 0 caracteres

## No hubo ningun intento de generacion

El render se fue a fallback antes de llamar al modelo. Mira el motivo de arriba: casi siempre es la conexion, la clave o el limite de peticiones.
