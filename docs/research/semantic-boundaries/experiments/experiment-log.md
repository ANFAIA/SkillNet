# Experiment Log

46 experiments were run to test how far content-based access classification can go.

## Results

| # | Experiment | Result |
|---|-----------|--------|
| 1 | Benchmark base (MiniLM 384d) | 93% float, 90.5% binary |
| 2 | Benchmark base (e5-large 1024d) | 98.7% float, 100% binary |
| 3 | Adversarial (same topic pairs) | 97.5% with labels, 90% without |
| 4 | Regex rules | 70.5-83.3% |
| 5 | Anomaly detection | 89% (2-stage), 97.7% binary |
| 6 | Ontology 20 concepts | 95.3% |
| 7 | Minimum definition (53 words) | 92.7% baseline, 90% adversarial |
| 8 | LLM zero/few-shot | 70-84% |
| 9 | Policy space (Voronoi, spheres) | Voronoi 96.5%, spheres FAIL |
| 10 | Designed dimensions + fine-tuning | LDA 98%, FT +144% silhouette |
| 11 | Combined pipeline ontology->binary | 96.0% without labels, 11us |
| 12 | Error analysis + concepts | 99.3% main, 92.5% adv (64 concepts) |
| 13 | Combined cascades (7 variants) | 99.3% main, 92.5% adv (onto->anomaly->Voronoi) |
| 14 | Serious fine-tuning (11K pairs, TripletLoss) | IN PROGRESS |
| 15 | Cross-domain (law firm, clinic) | Does NOT generalize: 47-55% in other domains |
| 16 | New approaches (NLI, archetypes, ensemble, AL) | NLI fails; SVM concat=100%; AL 50 labels=100% |
| 17 | Ordinal classification | Ordinal LR 100% main; Cost-Sensitive SVM 97.5% adv |
| 18 | Clustering+sampling (Cyera-style) | 83.3% max, clusters by topic, not access |
| 19 | Conformal prediction | SVM too good, CP adds nothing |
| 20 | Dimension analysis | 200 dims optimal. Voronoi improves +4.5pp with reduction |
| 21 | GNN / graph-enhanced | KNN-10 neighbor mean -> 100% supervised. Homophily 93.6% |
| 22 | Legal text as descriptor | GDPR is NOISE: 28-74% vs 92.7% ontology |
| 23 | Graph-enhanced unsupervised | 100% main (0 labels). KNN corrects last error |
| 24 | Optimized pipeline | 99.33% main + 100% adv (0 labels). Voronoi 100d + SVM fallback |
| 25 | Cross-domain v2 (150 law firm docs) | 55% max. Structural limit |
| 26 | New embedding models | Qwen3 100%/95% SVM. e5-large still best for unsupervised |
| 27 | 3-axis system (design) | Hypothesis: content+provenance+mosaic >85% cross-domain |
| 28 | 3-axis v1 (naive concat) | 77.9% LODO |
| 29 | 3-axis Bell-LaPadula | 69.0% holdout 84.4% |
| 30 | Domain-adversarial MI | 78.5% LODO |
| 31 | Domain residual | 78.4% LODO |
| 32 | IRM-stable dims | 78.0% LODO |
| 33 | Mahalanobis PCA-64 | 70.5% LODO |
| 34 | Holdout E5-large (clean) | 90.0% holdout |
| 35 | Holdout + PII floor | 89.4% holdout (GER 1.2%) |
| 36 | Asymmetric cost (7 variants) | 78.2% ALL of them |
| 37 | LLM (DeepSeek) on 16 holdout errors | 56.3% (9/16 corrected). Complementary, not replacement |
| 38 | TDA separability geometry | CH predicts LODO with r=0.71, p=0.049 |
| 39 | spaCy NER + 10 formal rules | LODO 72% (WORSENS). 793 elevations, 73% make things worse |
| 40 | Hierarchical (PUB vs rest) | LODO 76% (worse than baseline) |
| 41 | Few-shot K=3 | LODO 79.1% (+0.9pp) |
| 42 | Few-shot K=5 | **LODO 80.1% (+1.9pp), BREAKS THE CEILING** |
| 43 | Few-shot K=10 | LODO 81.3% (+3.1pp) |
| 44 | Few-shot K=20 | LODO 82.8% (+4.6pp) |
| 45 | Few-shot K=40 | LODO 86.7% (+8.5pp) |
| 46 | Cross-encoder zero-shot | 45.2% (ranking model, not classification) |

## Key Findings

### What worked
- Binary quantization **improves** accuracy (acts as regularizer)
- 53 words of human input = 92.7% accuracy without any labels
- 64 directed concepts = 99.3% (only 1 error in 150 docs)
- Ontology + KNN cascade = 100% without labels
- Voronoi top-100 dims + Cost-Sensitive SVM fallback = 100% adversarial without labels
- Graph-enhanced features (KNN-10 neighbor mean) -> 100% supervised
- Few-shot K=5 breaks the 78% cross-domain ceiling -> 80.1%

### What did not work
- Spheres overlap across domains, only Voronoi works
- NLI zero-shot: 27-37%
- LLM as classifier: 84% max, expensive, non-deterministic
- Clustering+sampling (Cyera-style): tops at 83.3%, clusters by topic not access
- Legal text (GDPR/LOPD) as descriptor: 28-74% vs 92.7% ontology
- PCA before quantization destroys accuracy (93% -> 53%)
- spaCy NER rules: too aggressive, 3 false positives for every correction
- Cross-domain does not generalize from content alone (47-55%)
