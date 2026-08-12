# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 2 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| traceable | atencion-reclamaciones | FAIL | 43% | 4 | 1 | 5466/1291 | 16172 ms | $0.001594 |

## Fallos de política

- **traceable / atencion-reclamaciones**: pack status is not ready; invariants 4 < minimum 5; fact coverage 42.9% < minimum 100.0%; missing=reformulate,effect-not-blame,crm-timing,hold-limit
