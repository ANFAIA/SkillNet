---
title: "Content-based classification"
order: 52
section: "research"
---

# 3-Axis Classification System

## Why One Axis Is Not Enough

The research began with a single axis: semantic content (embeddings). Within a single domain (events/catering in Spain), this achieved 100% accuracy with zero labels. But when crossing to other domains (law firm, clinic), accuracy dropped to 55% and 64% respectively. On DSAC-Bench (1,280 documents across 8 domains), the Leave-One-Domain-Out ceiling was 78.2%.

20+ configurations were tested. None broke through 78.2%. The boundary is not an optimization problem; it is intrinsic. The function `content -> access_level` is not injective: the same text can be public or confidential depending on organizational policy.

### Everything That Was Tried (And Failed)

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

The 7 asymmetric cost variants are the most telling result: every single one produces exactly 78.2% accuracy with exactly 139 under-classifications and 140 over-classifications. The SVM decision boundary is geometrically invariant to cost weighting.

### Mutual Information by Domain

| Domain | I(X;Y)/H(Y) estimated | Accuracy ceiling |
|--------|----------------------|------------------|
| Catering (synthetic) | ~1.0 | ~100% |
| Technical/code | ~0.85 | ~90% |
| Clinical | ~0.70 | ~80% |
| Legal/contracts | ~0.45 | ~55-60% |

This formalizes why cross-domain classification fails: in legal documents, the content carries only ~45% of the information needed to determine access level. The remaining 55% is in provenance and organizational policy.

### Few-Shot Learning Breaks The Ceiling

| K (labeled examples per domain) | LODO Accuracy | Delta |
|---------------------------------|---------------|-------|
| 0 (zero-shot) | 78.2% | baseline |
| 3 | 79.1% | +0.9pp |
| 5 | **80.1%** | **+1.9pp (breaks the ceiling)** |
| 10 | 81.3% | +3.1pp |
| 20 | 82.8% | +4.6pp |
| 40 | 86.7% | +8.5pp |

**Actionable finding:** When deploying to a new domain, labeling just 5-10 documents breaks through the zero-shot ceiling.

## The Convergence Discovery

Every system that successfully imposes deterministic boundaries on probabilistic information, discovered independently across thousands of years, converges on three axes:

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

No system that works in real production depends on a single axis. All combine at least two. Our system used only one. That explains the 55%.

## Axis 1: Content (Already Implemented)

The existing classifier based on semantic embeddings and a 64-concept ontology. It works perfectly when vocabulary differs between access levels (catering: "menu" vs "payroll"). It fails when vocabulary is uniform (legal: a contract can be public, internal, or confidential with nearly identical text).

### Interface

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

### When It Is Reliable

- Margin > 0.05: direct classification, high confidence
- Margin 0.002-0.05: classification with verification (ask Axis 2)
- Margin < 0.002: NOT reliable, depend on Axes 2 and 3

## Axis 2: Provenance (New, The Missing Piece)

A contract from a law firm and a contract from a restaurant are semantically identical. But:
- The restaurant's was created by the manager for a local supplier: INTERNAL
- The law firm's was created by a senior partner for active litigation: CONFIDENTIAL
- The law firm's was created by communications for the website: PUBLIC

The difference is NOT in the words. It is in the context of creation.

### Features

**Explicit metadata** (when available): author role, department, workflow, creation date, recipients, source system.

**Automatic extraction** (when metadata is absent, ~80% of cases):
- Author and role detection via signature patterns and title recognition
- Department inference via structural patterns (legal numbering, HR terminology, financial reporting)
- Workflow inference via structural cues ("for immediate release" = public, "strictly confidential" = confidential)
- Explicit classification marks ("CONFIDENTIAL", "INTERNAL") in headers/footers

### Classification Tables (Domain-Invariant)

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

### Why Axis 2 Is Domain-Invariant

Provenance features do not depend on domain vocabulary. They depend on:
- Structural patterns (legal numbering, signatures, letterheads), which exist in all domains
- Organizational roles (CEO, director, employee), which are universal
- Business workflows (publication, internal review, filing), which are universal
- Explicit marks ("CONFIDENTIAL"), which are universal

## Axis 3: Combination / Mosaic (New)

### The Nuclear Precedent

The Progressive case (1979): a magazine tried to publish an article about how a hydrogen bomb works. All information was from public sources. The government argued: "The danger is not in each individual piece of information, but in the **exposure of certain concepts never before revealed in conjunction with one another.**"

This is the mosaic/compilation problem: individually unclassified pieces that, combined, BECOME classified.

### Co-Occurrence Rules

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

### Aggregation Rules

- More than 5 person records in a single document: escalate +1 level (re-identification risk)
- More than 10 monetary figures: escalate +1 level (cost structure exposure)
- Document references a confidential document: inherit maximum level (derivative classification)

### Why Axis 3 Is Domain-Invariant

- Name + salary = CONFIDENTIAL in a law firm, a clinic, and a restaurant
- PII (national ID, bank account) = CONFIDENTIAL in any domain
- 5+ person records = escalate in any domain
- These are rules about INFORMATION PATTERNS, not domain vocabulary

## The Combination Function

The three axes are combined following a Bell-LaPadula lattice model with NASA FDIR escalation principles:

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

## Worked Example: Law Firm Contract

**Document:** Lease agreement between Garcia & Associates (Tax ID B-12345678) and Southern Real Estate Ltd. for 4,500 EUR/month. Signed by Antonio Garcia, Senior Partner.

**Axis 1 (Content):**
- Embedding close to "contract" and "lease" concepts
- Ontology votes: INTERNAL (margin 0.018, low, both public and confidential concepts nearby)

**Axis 2 (Provenance):**
- Author detected: "Antonio Garcia, Senior Partner" -> executive role -> CONFIDENTIAL
- Department inferred: legal (contractual patterns) -> CONFIDENTIAL
- Workflow: contract with figures, not for publication -> CONFIDENTIAL

**Axis 3 (Mosaic):**
- Entities: 2 ORGANIZATION, 1 PERSON, 1 MONEY (4,500 EUR), 1 PII (Tax ID)
- Rule triggered: PII present -> CONFIDENTIAL
- Rule triggered: contract + 2 orgs + money -> CONFIDENTIAL

**Combination:**
1. Mosaic floor: CONFIDENTIAL
2. Provenance at 0.75 (below 0.80 threshold), no override
3. Content margin 0.018 (below 0.05 threshold), not reliable
4. Neither reliable -> fail-closed: max(INTERNAL, CONF) = CONFIDENTIAL
5. Result: **CONFIDENTIAL** (provisional, flagged for human confirmation due to low Axis 1 confidence)

Even without domain-specific calibration, Axes 2 and 3 classify correctly. The content axis alone would have said INTERNAL, which is wrong.

## Key Numbers

| Metric | Value |
|--------|-------|
| Best single-domain accuracy | 100% (zero labels) |
| Cross-domain ceiling (content only) | 78.2% LODO |
| Realistic holdout accuracy | 90.0% |
| Classification latency | 11-41 us |
| Minimum human input for 92.7% | 53 words |
| Labels needed for 100% (single domain) | 50 (active learning) |
| Few-shot to break cross-domain ceiling | 5 examples/domain |

## Other Approaches That Failed

- **Spheres (centroid + radius):** All domains overlap. 139 of 200 documents fall in multiple spheres.
- **NLI zero-shot:** 27-37%. Not designed for this.
- **LLM as classifier:** 70-84%, expensive, non-deterministic.
- **Clustering + sampling (Cyera-style):** 83.3% max. Clusters group by topic, not access.
- **PCA before quantization:** Destroys accuracy (93% -> 53%). Access info is distributed across many dimensions.
- **spaCy NER rules:** Too aggressive. For every document corrected, 3 false positives.
- **Domain whitening:** 25%. Removes the signal entirely.

## Competitive Landscape

| System | Accuracy | Supervision | Notes |
|--------|----------|-------------|-------|
| **This research** | **100% intra / 78% cross** | **0 labels** | **41us, deterministic** |
| Cyera (patent US12210594B2) | Claims 95% | Proprietary | Metadata string matching, NOT embeddings |
| BigID | — | Prompt-based | Validates our ontology approach has market demand |
| Microsoft Purview | — | Semi-supervised | SearchLeak CVE bypassed information barriers |
| TorchSight (Qwen 27B) | 95.0% | 78K samples | Heavy inference |
| Lbl2Vec | 82-89% F1 | None | Closest conceptual competitor |
| DLP legacy (regex) | 50-80% | Manual rules | Industry baseline |

## Limitations

1. The 100% single-domain result is on synthetic data. Real enterprise documents may be harder.
2. The 3-axis system is theoretically motivated but experimentally unvalidated at cross-domain scale.
3. For most deployments, a knowledge graph + PostgreSQL RLS is sufficient. The binary embedding layer adds value primarily in high-throughput or high-security scenarios.
4. If the embedding model is updated, all binary codes and centroids must be recomputed.

## Next Validation Step

Test the 3-axis system on the 150 law firm documents that gave 55% with content only. Target: >85% accuracy. If it holds, the thesis is validated.
