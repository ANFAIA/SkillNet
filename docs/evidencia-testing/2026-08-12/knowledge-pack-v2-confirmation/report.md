# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 2 / 2
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | apertura-cierre-caja | FAIL | 57% | 4 | 0 | 4149/1472 | 21417 ms | $0.001506 |

## Fallos de política

- **balanced / apertura-cierre-caja**: pack status is not ready; fact coverage 57.1% < minimum 100.0%; missing=opening-claim,card-and-vouchers,same-day; no required evidence specification
