# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 6 / 6
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | apertura-cierre-caja | ERROR | — | — | — | — | — | — |
| balanced | alergenos-hosteleria | ERROR | — | — | — | — | — | — |
| balanced | atencion-reclamaciones | ERROR | — | — | — | — | — | — |

## Fallos de política

- **balanced / apertura-cierre-caja**: KnowledgePackGenerationError: reviewed pack failed contract validation
- **balanced / alergenos-hosteleria**: KnowledgePackGenerationError: reviewed pack failed contract validation
- **balanced / atencion-reclamaciones**: KnowledgePackGenerationError: reviewed pack failed contract validation
