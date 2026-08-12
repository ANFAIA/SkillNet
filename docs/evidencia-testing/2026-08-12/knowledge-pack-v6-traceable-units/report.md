# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 2 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | atencion-reclamaciones | FAIL | 14% | 4 | 1 | 5535/1200 | 18998 ms | $0.001550 |

## Fallos de política

- **balanced / atencion-reclamaciones**: pack status is not ready; fact coverage 14.3% < minimum 100.0%; missing=reformulate,effect-not-blame,commitment,crm-timing,written-deadline,hold-limit
