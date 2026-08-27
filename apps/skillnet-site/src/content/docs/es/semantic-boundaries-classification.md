---
title: "Clasificación basada en contenido"
order: 52
section: "research"
group: "semantic-boundaries"
---

# Sistema de Clasificación de 3 Ejes

## Por qué un solo eje no es suficiente

La investigación empezó con un solo eje: contenido semántico (embeddings). Dentro de un único dominio (eventos/catering en España), esto logró 100% de precisión con cero etiquetas. Pero al cruzar a otros dominios (despacho de abogados, clínica), la precisión cayó al 55% y 64% respectivamente. En DSAC-Bench (1.280 documentos en 8 dominios), el techo de Leave-One-Domain-Out fue del 78.2%.

Se probaron más de 20 configuraciones. Ninguna rompió el 78.2%. La frontera no es un problema de optimización; es intrínseca. La función `content -> access_level` no es inyectiva: el mismo texto puede ser público o confidencial según la política organizativa.

### Todo lo que se probó (y falló)

| Approach | LODO Result | Delta vs Baseline |
|----------|-------------|-------------------|
| SVM E5-large (baseline) | 78.2% | --- |
| 3-axis v1 (naive concat) | 77.9% | -0.3pp |
| 3-axis Bell-LaPadula (mosaic override) | 69.0% | -9.2pp |
| Domain-adversarial (MI ratio) | 78.5% | +0.3pp (marginal) |
| Domain residual (remove domain component) | 78.4% | +0.2pp |
| IRM-stable dimensions | 78.0% | -0.2pp |
| 7 variants of asymmetric cost | 78.2% ALL | 0pp (every single one) |
| Domain detection + domain-specific | 66.6% | -11.6pp |
| LDA (reduce to 3 dims) | 42.3% | -35.9pp |
| Domain whitening | 25.0% | -53.2pp |
| Gradient Boosting, RF, LogReg | all <= 78% | negative or zero |
| Cascading, stacking, PCA | all <= 78% | negative or zero |

Las 7 variantes de coste asimétrico son el resultado más revelador: cada una produce exactamente 78.2% de precisión con exactamente 139 sub-clasificaciones y 140 sobre-clasificaciones. La frontera de decisión del SVM es geométricamente invariante a la ponderación de costes.

### Información mutua por dominio

| Domain | I(X;Y)/H(Y) estimated | Accuracy ceiling |
|--------|----------------------|------------------|
| Catering (synthetic) | ~1.0 | ~100% |
| Technical/code | ~0.85 | ~90% |
| Clinical | ~0.70 | ~80% |
| Legal/contracts | ~0.45 | ~55-60% |

Esto formaliza por qué la clasificación entre dominios falla: en documentos legales, el contenido lleva solo ~45% de la información necesaria para determinar el nivel de acceso. El 55% restante está en la procedencia y la política organizativa.

### El aprendizaje few-shot rompe el techo

| K (labeled examples per domain) | LODO Accuracy | Delta |
|---------------------------------|---------------|-------|
| 0 (zero-shot) | 78.2% | baseline |
| 3 | 79.1% | +0.9pp |
| 5 | **80.1%** | **+1.9pp (breaks the ceiling)** |
| 10 | 81.3% | +3.1pp |
| 20 | 82.8% | +4.6pp |
| 40 | 86.7% | +8.5pp |

**Hallazgo accionable:** Al desplegar en un dominio nuevo, etiquetar solo 5-10 documentos rompe el techo de zero-shot.

## El descubrimiento de la convergencia

Todo sistema que impone con éxito fronteras deterministas sobre información probabilística, descubierto de forma independiente a lo largo de miles de años, converge en tres ejes:

| System | Axis 1 (Content) | Axis 2 (Provenance) | Axis 3 (Combination) |
|--------|-----------------|---------------------|---------------------|
| NASA FDIR | Sensor reading | Which subsystem sent it | Multi-sensor correlation |
| Military SCI/SAP | Report text | Program of origin (HUMINT, SIGINT) | Need-to-know cross-refs |
| Nuclear "born classified" | Individual data point | Origin classification | Pieces public alone but classified combined |
| Human cell (epigenetics) | DNA sequence | Cell type (liver vs neuron) | Gene co-expression |
| Vatican Archives | Manuscript content | Archive fund and chain of custody | Cross-fund intersections |
| Inca Quipus | Knot value | Cord color (data type) | Position (element identity) |
| **Our system (current)** | **Semantic embedding** | **Not used** | **Not used** |
| **Our system (proposed)** | **Semantic embedding** | **Metadata: author, dept, type** | **NER + co-occurrence** |

Ningún sistema que funcione en producción real depende de un solo eje. Todos combinan al menos dos. Nuestro sistema usaba solo uno. Eso explica el 55%.

## Eje 1: Contenido (ya implementado)

El clasificador existente basado en embeddings semánticos y una ontología de 64 conceptos. Funciona perfectamente cuando el vocabulario difiere entre niveles de acceso (catering: "menú" vs "nómina"). Falla cuando el vocabulario es uniforme (legal: un contrato puede ser público, interno o confidencial con un texto casi idéntico).

### Interfaz

```python
class ContentAxis:
    def classify(self, text: str) -> AxisResult:
        embedding = self.model.encode(text)
        binary = (embedding > self.thresholds).astype(int)

        # Ontology: cosine distance to 64 concepts
        scores = cosine_similarity(embedding, self.concepts)
        level = self._vote_level(scores)
        margin = self._compute_margin(scores)

        # Cascade if margin is low
        if margin < 0.002:
            neighbors = self.knn.query(binary, k=5)
            level = Counter(v.level for v in neighbors).most_common(1)[0][0]

        return AxisResult(level=level, confidence=margin, source="content")
```

### Cuándo es fiable

- Margen > 0.05: clasificación directa, alta confianza
- Margen 0.002-0.05: clasificación con verificación (consultar el Eje 2)
- Margen < 0.002: NO fiable, depender de los Ejes 2 y 3

## Eje 2: Procedencia (nuevo, la pieza que faltaba)

Un contrato de un despacho de abogados y un contrato de un restaurante son semánticamente idénticos. Pero:
- El del restaurante fue creado por el gerente para un proveedor local: INTERNO
- El del despacho fue creado por un socio senior para un litigio activo: CONFIDENCIAL
- El del despacho fue creado por comunicación para el sitio web: PÚBLICO

La diferencia NO está en las palabras. Está en el contexto de creación.

### Características

**Metadatos explícitos** (cuando están disponibles): rol del autor, departamento, flujo de trabajo, fecha de creación, destinatarios, sistema de origen.

**Extracción automática** (cuando faltan los metadatos, ~80% de los casos):
- Detección de autor y rol mediante patrones de firma y reconocimiento de cargos
- Inferencia de departamento mediante patrones estructurales (numeración legal, terminología de RRHH, informes financieros)
- Inferencia de flujo de trabajo mediante indicios estructurales ("para publicación inmediata" = público, "estrictamente confidencial" = confidencial)
- Marcas de clasificación explícitas ("CONFIDENCIAL", "INTERNO") en encabezados/pies de página

### Tablas de clasificación (invariantes por dominio)

```
AUTHOR ROLE                DEFAULT MINIMUM LEVEL
CEO / Board                CONFIDENTIAL (presumption of strategy)
Director / Partner         CONFIDENTIAL
Manager / Team Lead        INTERNAL
Employee / Technician      INTERNAL
Communications / Marketing PUBLIC (presumption of dissemination)
External / Supplier        PUBLIC

DEPARTMENT                 DEFAULT MINIMUM LEVEL
Legal / Juridical          CONFIDENTIAL (attorney-client privilege)
HR / People                INTERNAL (CONF if PII present)
Finance / Accounting       CONFIDENTIAL
Operations                 INTERNAL
Communications / Marketing PUBLIC
IT / Infrastructure        INTERNAL (CONF if security-related)
```

### Por qué el Eje 2 es invariante por dominio

Las características de procedencia no dependen del vocabulario del dominio. Dependen de:
- Patrones estructurales (numeración legal, firmas, membretes), que existen en todos los dominios
- Roles organizativos (CEO, director, empleado), que son universales
- Flujos de trabajo empresariales (publicación, revisión interna, archivo), que son universales
- Marcas explícitas ("CONFIDENCIAL"), que son universales

## Eje 3: Combinación / Mosaico (nuevo)

### El precedente nuclear

El caso Progressive (1979): una revista intentó publicar un artículo sobre cómo funciona una bomba de hidrógeno. Toda la información provenía de fuentes públicas. El gobierno argumentó: "El peligro no está en cada pieza individual de información, sino en la **exposición de ciertos conceptos nunca antes revelados en conjunto entre sí.**"

Este es el problema del mosaico/compilación: piezas individualmente no clasificadas que, combinadas, SE VUELVEN clasificadas.

### Reglas de co-ocurrencia

```python
MOSAIC_RULES = [
    # Person name + salary = CONFIDENTIAL
    {"condition": has(PERSON) and has(MONEY) and has_keyword("salary"),
     "minimum_level": "CONF",
     "justification": "Personal data + compensation = sensitive (GDPR art. 9)"},

    # Organization + profit margin = CONFIDENTIAL
    {"condition": has(ORG) and has(MONEY) and has_keyword("margin", "EBITDA"),
     "minimum_level": "CONF",
     "justification": "Financial data with identifiable entity = trade secret"},

    # PII (national ID, bank account) present = CONFIDENTIAL
    {"condition": has(PII),
     "minimum_level": "CONF",
     "justification": "Direct identifier (GDPR art. 4)"},

    # Contract + identified parties + amounts = CONFIDENTIAL
    {"condition": has_keyword("contract") and count(ORG) >= 2 and has(MONEY),
     "minimum_level": "CONF",
     "justification": "Commercial relationship with economic terms = trade secret"},

    # Strategy + concrete figures = RESTRICTED
    {"condition": has_keyword("acquisition", "M&A", "due diligence") and has(MONEY),
     "minimum_level": "REST",
     "justification": "Potential insider information"},
]
```

### Reglas de agregación

- Más de 5 registros de personas en un único documento: escalar +1 nivel (riesgo de reidentificación)
- Más de 10 cifras monetarias: escalar +1 nivel (exposición de la estructura de costes)
- El documento hace referencia a un documento confidencial: heredar el nivel máximo (clasificación derivada)

### Por qué el Eje 3 es invariante por dominio

- Nombre + salario = CONFIDENCIAL en un despacho de abogados, una clínica y un restaurante
- PII (DNI, cuenta bancaria) = CONFIDENCIAL en cualquier dominio
- 5+ registros de personas = escalar en cualquier dominio
- Estas son reglas sobre PATRONES DE INFORMACIÓN, no sobre vocabulario de dominio

## La función de combinación

Los tres ejes se combinan siguiendo un modelo de retícula Bell-LaPadula con principios de escalado de NASA FDIR:

```python
def combine_3_axes(r_content, r_provenance, r_mosaic, config):
    """
    Rules:
    1. Axis 3 (mosaic) ONLY ESCALATES, never reduces ("born classified")
    2. If provenance metadata is reliable (conf > 0.8), provenance OVERRIDES
       content (SCI/SAP: classification is by origin, not by text)
    3. If provenance is unreliable, max(content, mosaic) (fail-closed)
    4. If axes disagree by > 1 level, flag for human review (NASA escalation)
    5. Final level is NEVER below the mosaic floor (Bell-LaPadula "no write down")
    """
    # Step 1: Mosaic sets the floor (never below this)
    floor = r_mosaic.level

    # Step 2: Decide between content and provenance
    if r_provenance.confidence >= config.provenance_threshold:
        base_level = r_provenance.level  # SCI/SAP: origin decides
    elif r_content.confidence >= config.content_threshold:
        base_level = r_content.level
    else:
        base_level = max(r_content.level, r_provenance.level)  # fail-closed

    # Step 3: Apply mosaic floor
    final_level = max(base_level, floor)

    # Step 4: Decide if human review needed
    discrepancy = max_difference_between_axes(r_content, r_provenance, r_mosaic)
    min_confidence = min(r_content.confidence, r_provenance.confidence, r_mosaic.confidence)
    needs_human = min_confidence < config.auto_threshold or discrepancy > 1

    return FinalResult(level=final_level, needs_human=needs_human, ...)
```

## Ejemplo resuelto: contrato de un despacho de abogados

**Documento:** Contrato de arrendamiento entre Garcia & Associates (NIF B-12345678) y Southern Real Estate Ltd. por 4.500 EUR/mes. Firmado por Antonio Garcia, Socio Senior.

**Eje 1 (Contenido):**
- Embedding cercano a los conceptos "contrato" y "arrendamiento"
- Votos de la ontología: INTERNO (margen 0.018, bajo, tanto conceptos públicos como confidenciales cerca)

**Eje 2 (Procedencia):**
- Autor detectado: "Antonio Garcia, Socio Senior" -> rol ejecutivo -> CONFIDENCIAL
- Departamento inferido: legal (patrones contractuales) -> CONFIDENCIAL
- Flujo de trabajo: contrato con cifras, no destinado a publicación -> CONFIDENCIAL

**Eje 3 (Mosaico):**
- Entidades: 2 ORGANIZACIÓN, 1 PERSONA, 1 DINERO (4.500 EUR), 1 PII (NIF)
- Regla activada: PII presente -> CONFIDENCIAL
- Regla activada: contrato + 2 orgs + dinero -> CONFIDENCIAL

**Combinación:**
1. Suelo del mosaico: CONFIDENCIAL
2. Procedencia a 0.75 (por debajo del umbral de 0.80), sin override
3. Margen de contenido 0.018 (por debajo del umbral de 0.05), no fiable
4. Ninguno fiable -> fail-closed: max(INTERNO, CONF) = CONFIDENCIAL
5. Resultado: **CONFIDENCIAL** (provisional, marcado para confirmación humana por baja confianza en el Eje 1)

Incluso sin calibración específica de dominio, los Ejes 2 y 3 clasifican correctamente. El eje de contenido solo habría dicho INTERNO, lo cual es incorrecto.

## Cifras clave

| Metric | Value |
|--------|-------|
| Best single-domain accuracy | 100% (zero labels) |
| Cross-domain ceiling (content only) | 78.2% LODO |
| Realistic holdout accuracy | 90.0% |
| Classification latency | 11-41 us |
| Minimum human input for 92.7% | 53 words |
| Labels needed for 100% (single domain) | 50 (active learning) |
| Few-shot to break cross-domain ceiling | 5 examples/domain |

## Otros enfoques que fallaron

- **Esferas (centroide + radio):** Todos los dominios se solapan. 139 de 200 documentos caen en múltiples esferas.
- **NLI zero-shot:** 27-37%. No diseñado para esto.
- **LLM como clasificador:** 70-84%, costoso, no determinista.
- **Clustering + muestreo (estilo Cyera):** 83.3% máximo. Los clústeres agrupan por tema, no por acceso.
- **PCA antes de la cuantización:** Destruye la precisión (93% -> 53%). La información de acceso está distribuida entre muchas dimensiones.
- **Reglas NER de spaCy:** Demasiado agresivas. Por cada documento corregido, 3 falsos positivos.
- **Blanqueo de dominio:** 25%. Elimina la señal por completo.

## Panorama competitivo

| System | Accuracy | Supervision | Notes |
|--------|----------|-------------|-------|
| **This research** | **100% intra / 78% cross** | **0 labels** | **41us, deterministic** |
| Cyera (patent US12210594B2) | Claims 95% | Proprietary | Metadata string matching, NOT embeddings |
| BigID | — | Prompt-based | Validates our ontology approach has market demand |
| Microsoft Purview | — | Semi-supervised | SearchLeak CVE bypassed information barriers |
| TorchSight (Qwen 27B) | 95.0% | 78K samples | Heavy inference |
| Lbl2Vec | 82-89% F1 | None | Closest conceptual competitor |
| DLP legacy (regex) | 50-80% | Manual rules | Industry baseline |

## Limitaciones

1. El resultado del 100% en un solo dominio se obtiene con datos sintéticos. Los documentos empresariales reales pueden ser más difíciles.
2. El sistema de 3 ejes está motivado teóricamente pero no validado experimentalmente a escala entre dominios.
3. Para la mayoría de los despliegues, un grafo de conocimiento + RLS de PostgreSQL es suficiente. La capa de embeddings binarios aporta valor principalmente en escenarios de alto throughput o alta seguridad.
4. Si se actualiza el modelo de embeddings, todos los códigos binarios y centroides deben recalcularse.

## Próximo paso de validación

Probar el sistema de 3 ejes en los 150 documentos de despacho de abogados que dieron 55% solo con contenido. Objetivo: >85% de precisión. Si se sostiene, la tesis queda validada.
