# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 2 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| traceable | atencion-reclamaciones | FAIL | 29% | 4 | 4 | 5570/1590 | 21824 ms | $0.001790 |

## Fallos de política

- **traceable / atencion-reclamaciones**: pack status is not ready; invariants 4 < minimum 5; fact coverage 28.6% < minimum 100.0%; missing=reformulate,effect-not-blame,commitment,crm-timing,hold-limit
