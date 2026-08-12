# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 2 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | apertura-cierre-caja | ERROR | — | — | — | 4070/1530 | 17278 ms | $0.001528 |

## Fallos de política

- **balanced / apertura-cierre-caja**: KnowledgePackGenerationError: reviewed pack failed contract validation: : Value error, atom must.source:bbbbbbbb-0000-0000-0000-000000000004:node:966d3494-bfca-586b-b90f-e7d1354df30a references unknown sources
