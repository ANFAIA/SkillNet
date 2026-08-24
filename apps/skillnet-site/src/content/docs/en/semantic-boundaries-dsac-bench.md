---
title: "DSAC bench"
order: 53
section: "research"
---

# DSAC-Bench: Document Sensitivity and Access Classification Benchmark

## Motivation

No public benchmark exists for document access/sensitivity classification. Existing text classification benchmarks (AG News, 20Newsgroups, MTEB) measure topic, sentiment, or intent, never access level. The only real-world dataset with access labels is the WikiLeaks diplomatic cables corpus (Alzhrani et al., UC Colorado Springs), with limited availability.

This gap means that published accuracy numbers for access classification systems are incomparable. DSAC-Bench is designed to fill this gap.

## Structure

### 4 Access Levels (aligned with ISO 27001)

| Level | Code | Example |
|-------|------|---------|
| Public | PUB | Website FAQ |
| Internal | INT | Process manual |
| Confidential | CONF | Supplier contract |
| Restricted | REST | Board minutes with personal data |

### 8 Domains

1. **Catering/Events:** easy (vocabulary very distinct between levels)
2. **Legal/Law Firm:** very hard (vocabulary uniform across levels)
3. **Clinical/Health:** hard (signal in PII, not in topic)
4. **Technology/Startup:** medium-high (README vs vulnerability report)
5. **Education:** medium (syllabus vs student record)
6. **Public Administration:** high (transparency vs reserved)
7. **Finance/Banking:** high (MiFID regulation, insider information)
8. **Human Resources:** medium-high (payroll, evaluations, policies)

### 7 Functional Splits

| Split | Abbrev | Purpose | Difficulty |
|-------|--------|---------|------------|
| Core | CORE | Typical docs of each level/domain | Easy-Medium |
| Same-Topic Adversarial | STA | Same topic, different level (4 versions) | Hard |
| Minimal Signal | MINSIG | 1-3 sentences, minimal signal | Hard |
| Cross-Domain | XDOM | Train on A, evaluate on B | Medium-Hard |
| Temporal | TEMP | Same doc, policy changes over time | Hard |
| Noisy | NOISE | OCR errors, jargon, fragments | Medium |
| Scale-Variant | SCALE | From 1 sentence to 5 pages | Medium |

### Volume

| Split | Docs/domain | Domains | Total |
|-------|-------------|---------|-------|
| CORE | 160 | 8 | 1,280 |
| STA | 80 | 8 | 640 |
| MINSIG | 40 | 4 | 160 |
| TEMP | 20 | 4 | 80 |
| NOISE | 40 | 4 | 160 |
| SCALE | 40 | 4 | 160 |
| **Total** | | | **~2,480** |

## Metrics

### Primary Metrics

- **Macro F1.** Field standard
- **WSE (Weighted Security Error).** Novel metric that penalizes grave errors asymmetrically
- **Recall REST.** How many restricted documents escape

### WSE Cost Matrix

```
              Predicted ->
              PUB   INT   CONF  REST
Real    PUB  [ 0     1     2     3  ]
        INT  [ 3     0     1     2  ]
        CONF [ 6     3     0     1  ]
        REST [ 10    6     3     0  ]
```

REST->PUB = 10 (maximum damage: restricted document classified as public).
PUB->INT = 1 (minor annoyance: public document requires internal clearance).

### DSAC-Score (Aggregate)

```
0.30 x F1_CORE + 0.30 x F1_STA + 0.15 x (1-WSE/10) + 0.10 x F1_NOISE
    + 0.10 x (1-CrossGap) + 0.05 x F1_SCALE
```

## Generation Protocol

1. **Manual gold standard:** 192 documents (2-3 per cell domain x level)
2. **Synthetic generation:** 3 different LLMs (40% DeepSeek, 30% Claude, 30% GPT-4o)
3. **Cross-validation:** Verifying LLM is different from generating LLM
4. **Human validation:** 3 annotators, minimum 30% of docs (~750)
5. **Anti-bias:** model detection test, "trojan" documents

## Evaluation Modes

- **Mode A (zero-shot):** Only receives level descriptions, no labeled data
- **Mode B (supervised):** Receives 640 train + 128 dev from CORE split

## First Results (Core Split, 1,280 docs)

```
ZERO-SHOT (ontology):       53.1% accuracy | F1 0.523 | WSE 1.70 | GER 23.0% | DSAC 0.575
SVM LODO (cross-domain):    78.2% accuracy | F1 0.784 | WSE 0.56 | GER  4.6% | DSAC 0.839
SVM INTRA (5-fold):          93.2% accuracy | F1 0.932 | WSE 0.20 | GER  2.1% | DSAC 0.939
```

### Accuracy by Domain (SVM LODO)

| Domain | Accuracy |
|--------|----------|
| Legal | 90.6% |
| HR | 84.4% |
| Catering | 81.2% |
| Admin | 78.1% |
| Education | 75.0% |
| Finance | 75.0% |
| Clinic | 71.2% |
| Technology | 70.0% |

### Fine-Tuning Results (3 epochs, MiniLM 384d)

- LODO with leakage: 100%, NOT RELIABLE (embeddings saw test data)
- **Holdout test (160 new docs never seen):** KNN 84.4% (+12.5pp vs base), SVM 84.4% (+2.5pp)
- **Real learning confirmed.** Not memorization. GER drops from 15% to 5% (3x fewer grave errors)
- Legal domain: 95 -> 100% with fine-tuning. The hardest domain IMPROVES.

## Comparison with WikiLeaks Benchmark

The only other dataset with real access labels:

| Method | Accuracy | F1 | Dataset |
|--------|----------|-----|---------|
| RAC (Chang et al., 2026) | ~96% | ~94% | WikiLeaks cables |
| Fine-tuning supervised | — | 90% | WikiLeaks cables |
| Our SVM + e5-large (synthetic) | 100% | ~100% | DSAC-Bench intra-domain |
| Our SVM LODO | 78.2% | 0.784 | DSAC-Bench cross-domain |

The comparison is not apples-to-apples: WikiLeaks cables are real diplomatic documents where CONFIDENTIAL and UNCLASSIFIED can discuss the same topic (e.g., relations with Russia). Our synthetic data with distinct vocabulary per level makes the intra-domain task easier. The cross-domain LODO result (78.2%) is a more honest reflection of real-world difficulty.

