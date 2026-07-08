# Semantic Boundaries

## The problem

In AI systems that use embeddings for search, two documents about the same topic but with different access levels end up close in vector space. A semantic search can return the confidential one alongside the public one. This is not theoretical. Microsoft Copilot was bypassed this way (CVE-2026-42824).

## The experiment

We wanted to test **how far you can go classifying document access levels purely from content, without any human input.** The idea: use embeddings to determine whether a document is public, internal, or confidential, letting the machine decide based on what the text says.

We built a benchmark (DSAC-Bench: 1,280 documents across 8 domains) and ran 400+ configurations (SVM, gradient boosting, domain-adversarial training, asymmetric costs, IRM, and more). Within a single domain, it works perfectly (100% accuracy). But across domains, nothing broke **78.2%** accuracy. The ceiling is intrinsic.

## The conclusion

**Privacy is not a property of content. It's a human decision.** The same text can be public or confidential depending on organizational policy. A contract clause about liability is public in a law firm's template library but confidential in an active case. No amount of NLP can resolve this because the information simply isn't in the text.

The current thinking is that classifying access from content alone doesn't have a viable path forward. Several directions are worth exploring from here:

- **Structural access control.** The organization decides what goes where (folders, containers, labels), and the system enforces those boundaries. The human makes the access decisions; the machine handles enforcement.
- **Knowledge graphs.** Using graph structure rather than content to determine access. The G-SPEC paper showed 68% of security gains come from the graph, not the LLM.
- **Vector-based pre-filtering.** Binary embeddings as a fast first pass to narrow down candidates before applying deterministic rules.
- **Hybrid classification.** Combining content analysis with provenance metadata and co-occurrence rules (the 3-axis model). Content alone caps at 78%, but adding a few human-labeled examples per domain breaks through.

None of these are chosen yet. The experiment showed where the limits are; the next step is finding which combination works in practice.

The full details of what was tried and what was discovered are in the documents below.

## Interesting discoveries along the way

- **Binary quantization improves accuracy.** Reducing 1024-dimensional vectors to binary (0s and 1s) was expected to lose information. Instead, it acts as a regularizer, flattening noise while preserving the discriminant signal. This is counterintuitive and potentially useful beyond access control.

- **Every system that solves this problem in the real world uses 3 axes, not 1.** NASA FDIR, military compartmentalization, nuclear classification: they all independently converge on the same pattern of content + provenance + combination rules. No production system depends on content analysis alone.

- **5 labeled examples per domain breaks the ceiling.** The 78% wall is only for zero-shot. With just 5 human-labeled examples in a new domain, accuracy jumps to 80%+. The human input doesn't need to be exhaustive, just a small anchor.

- **Ghost Vectors.** Deleted embeddings survive in HNSW indexes. Researchers demonstrated 100% recovery of patient data from a vector database that had "deleted" the records. [arXiv:2606.18497](https://arxiv.org/abs/2606.18497)

- **G-SPEC.** A neuro-symbolic approach to policy enforcement found that 68% of security gains come from the graph structure, not from the LLM. [arXiv:2512.20275](https://arxiv.org/abs/2512.20275)

## Deep dives

- [Content-Based Classification](content-based-classification.md). The core discovery: content + provenance + combination, everything that was tried, convergence evidence from independent fields
- [experiments/dsac-bench.md](experiments/dsac-bench.md). DSAC-Bench benchmark design (1,280 docs, 8 domains)
- [experiments/experiment-log.md](experiments/experiment-log.md). Complete table of all 46 experiments
