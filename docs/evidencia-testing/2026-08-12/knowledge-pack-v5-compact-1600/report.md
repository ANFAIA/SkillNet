# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 2 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | atencion-reclamaciones | FAIL | 0% | 4 | 1 | 4935/1071 | 12563 ms | $0.001383 |

## Fallos de política

- **balanced / atencion-reclamaciones**: fact coverage 0.0% < minimum 100.0%; missing=listen,reformulate,effect-not-blame,commitment,crm-timing,written-deadline,hold-limit
