# Ajuste de Node Knowledge Packs

- Modelo: `gpt-4o-mini`
- Llamadas reales al proveedor: 18 / 18
- Alcance: extracción + revisión; sin renders y sin escritura en cursos.

| Variante | Nodo | Política | Cobertura | Invariantes | Evidencia | Tokens E/S | Tiempo | Coste |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| compact | apertura-cierre-caja | FAIL | 0% | 0 | 0 | 2449/494 | 13968 ms | $0.000664 |
| compact | alergenos-hosteleria | FAIL | 29% | 1 | 0 | 2527/1116 | 15654 ms | $0.001049 |
| compact | atencion-reclamaciones | FAIL | 100% | 1 | 0 | 2819/1556 | 17984 ms | $0.001356 |
| balanced | apertura-cierre-caja | FAIL | 0% | 0 | 0 | 2449/494 | 7764 ms | $0.000664 |
| balanced | alergenos-hosteleria | FAIL | 29% | 1 | 0 | 2533/1128 | 13978 ms | $0.001057 |
| balanced | atencion-reclamaciones | FAIL | 100% | 1 | 0 | 2819/1556 | 21865 ms | $0.001356 |
| coverage | apertura-cierre-caja | FAIL | 0% | 0 | 0 | 2449/494 | 6200 ms | $0.000664 |
| coverage | alergenos-hosteleria | FAIL | 29% | 1 | 0 | 2527/1116 | 13223 ms | $0.001049 |
| coverage | atencion-reclamaciones | FAIL | 100% | 1 | 0 | 2819/1556 | 19124 ms | $0.001356 |

## Fallos de política

- **compact / apertura-cierre-caja**: pack status is not ready; invariants 0 < minimum 1; fact coverage 0.0% < minimum 80.0%; missing=float,opening-claim,cash-withdrawal,z-report,card-and-vouchers,mismatch-threshold,same-day
- **compact / alergenos-hosteleria**: pack status is not ready; fact coverage 28.6% < minimum 80.0%; missing=red-folder,cross-contact-oil,green-tools,never-guess,anaphylaxis
- **compact / atencion-reclamaciones**: pack status is not ready
- **balanced / apertura-cierre-caja**: pack status is not ready; invariants 0 < minimum 3; fact coverage 0.0% < minimum 100.0%; missing=float,opening-claim,cash-withdrawal,z-report,card-and-vouchers,mismatch-threshold,same-day; no required evidence specification
- **balanced / alergenos-hosteleria**: pack status is not ready; invariants 1 < minimum 3; fact coverage 28.6% < minimum 100.0%; missing=red-folder,cross-contact-oil,green-tools,never-guess,anaphylaxis; no required evidence specification
- **balanced / atencion-reclamaciones**: pack status is not ready; invariants 1 < minimum 3; no required evidence specification
- **coverage / apertura-cierre-caja**: pack status is not ready; invariants 0 < minimum 5; fact coverage 0.0% < minimum 100.0%; missing=float,opening-claim,cash-withdrawal,z-report,card-and-vouchers,mismatch-threshold,same-day; no required evidence specification
- **coverage / alergenos-hosteleria**: pack status is not ready; invariants 1 < minimum 5; fact coverage 28.6% < minimum 100.0%; missing=red-folder,cross-contact-oil,green-tools,never-guess,anaphylaxis; no required evidence specification
- **coverage / atencion-reclamaciones**: pack status is not ready; invariants 1 < minimum 5; no required evidence specification

## Conclusión

Ninguna variante es apta para runtime. Los nueve packs quedaron `review_required` y
ninguno cumplió su política. Aumentar el presupuesto de salida de `1.200/1.200` a
`2.048/2.048` no elevó la cobertura ni la granularidad:

- apertura/caja: `0 %` de cobertura y `0` invariantes en las tres variantes;
- alérgenos: `28,6 %` y `1` invariante en las tres variantes;
- reclamaciones: `100 %`, pero condensado en un único invariante monolítico y sin
  evidencia utilizable.

Por tanto, el presupuesto de tokens no es el dial que falta. Incluso la configuración
compacta dejó margen de salida; las variantes mayores produjeron esencialmente la misma
estructura a temperatura cero. No se elige una «ganadora»: `compact` solo sería la menos
costosa si el contrato ya funcionase, pero hoy también falla.

## Qué ha revelado la prueba

El modelo reprodujo texto semántico de los ejemplos del contrato (`source-backed optional
material`, `known source gap`) como si fueran contenido real. Además, la evidencia requerida
perdió sus referencias durante la normalización y se convirtió correctamente en un hueco
bloqueante. La puerta de seguridad funcionó: esos packs no pueden llegar a una pantalla.

La siguiente variable debe ser el **contrato de extracción**, no el presupuesto:

1. sustituir ejemplos rellenados por JSON Schema sin valores copiables;
2. exigir una lista de cobertura de hechos antes de construir átomos;
3. pedir un átomo por regla/procedimiento, con referencias de evidencia verificables;
4. comparar cada cambio contra el contrato actual con los mismos siete hechos gold por nodo;
5. no ejecutar renders hasta obtener `100 %` de hechos críticos, evidencia válida y packs
   `ready` en los tres nodos.

## Coste y tiempo

La matriz usó exactamente `18` llamadas, `23.391` tokens de entrada y `9.510` de salida.
Costó aproximadamente `$0,009215` con las tarifas declaradas. La preparación media fue
`14,42 s` por pack (`6,20–21,86 s`). Es trabajo asíncrono de creación del curso, no latencia
del alumno. Las diferencias temporales entre variantes no son causales porque se ejecutaron
en orden, no intercaladas.

Artefacto completo: [`results.json`](results.json). Contiene el payload canónico, Markdown,
hash, cobertura, hechos ausentes, tokens, duración y coste de cada celda.
