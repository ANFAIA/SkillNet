# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 4 / 4
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| traceable | apertura-cierre-caja | ERROR | — | — | — | 6368/3392 | 37264 ms | $0.002990 |
| traceable | alergenos-hosteleria | FAIL | 100% | 10 | 1 | 6163/2956 | 73344 ms | $0.002698 |

## Fallos de política

- **traceable / apertura-cierre-caja**: KnowledgePackGenerationError: reviewed pack failed contract validation: must_preserve.10.kind: Input should be 'fact', 'safety_rule', 'procedure_step', 'constraint' or 'criterion'; must_preserve.11.kind: Input should be 'fact', 'safety_rule', 'procedure_step', 'constraint' or 'criterion'
- **traceable / alergenos-hosteleria**: pack status is not ready
