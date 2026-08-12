# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 1 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | atencion-reclamaciones | ERROR | — | — | — | 2038/1600 | 25226 ms | $0.001266 |

## Fallos de política

- **balanced / atencion-reclamaciones**: KnowledgePackGenerationError: extractor returned invalid JSON
