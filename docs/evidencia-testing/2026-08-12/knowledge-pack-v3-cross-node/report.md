# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 4 / 4
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| balanced | alergenos-hosteleria | PASS | 100% | 8 | 1 | 4602/2278 | 27035 ms | $0.002057 |
| balanced | atencion-reclamaciones | FAIL | 86% | 7 | 0 | 4524/1944 | 24294 ms | $0.001845 |

## Fallos de política

- **balanced / atencion-reclamaciones**: fact coverage 85.7% < minimum 100.0%; missing=reformulate; no required evidence specification
