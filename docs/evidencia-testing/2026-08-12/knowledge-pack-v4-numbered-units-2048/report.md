# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 1 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| coverage | atencion-reclamaciones | ERROR | — | — | — | 2038/2048 | 28764 ms | $0.001535 |

## Fallos de política

- **coverage / atencion-reclamaciones**: KnowledgePackGenerationError: extractor returned invalid JSON
