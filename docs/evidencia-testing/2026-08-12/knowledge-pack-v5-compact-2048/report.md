# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 2 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| coverage | atencion-reclamaciones | FAIL | 29% | 4 | 1 | 4979/1159 | 15804 ms | $0.001442 |

## Fallos de política

- **coverage / atencion-reclamaciones**: invariants 4 < minimum 5; fact coverage 28.6% < minimum 100.0%; missing=reformulate,effect-not-blame,commitment,crm-timing,written-deadline
