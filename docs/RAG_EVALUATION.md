# STEP 08 RAG Evaluation

- Evaluation cases: 30
- K: 5
- Dataset: `data/evaluation/rag_cases.json`

| Strategy | Recall@5 | MRR@5 | nDCG@5 | Precision@5 | Citation Precision | Abstention Accuracy | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| keyword | 0.9800 | 0.9600 | 0.9550 | 0.2080 | 0.5547 | 0.0000 | 1.80 | 1.98 |
| vector | 0.8600 | 0.7027 | 0.7369 | 0.1840 | 0.1840 | 0.0000 | 6.69 | 7.52 |
| hybrid | 1.0000 | 0.9333 | 0.9505 | 0.2160 | 0.2160 | 0.0000 | 8.10 | 10.45 |
| rerank | 0.9800 | 0.9600 | 0.9550 | 0.2080 | 0.2080 | 0.0000 | 255.84 | 288.87 |
| rerank_prod | 0.8600 | 0.8400 | 0.8350 | 0.1840 | 0.7533 | 1.0000 | 255.84 | 288.87 |

## Notes

- Positive cases evaluate Recall, MRR, nDCG, Precision and citation precision.
- Negative cases evaluate whether the strategy returns no accepted evidence.
- Rerank raw reports unthresholded ranking quality.
- Rerank prod applies a calibrated minimum score of -2.9.
- The threshold was calibrated on this 30-case set, so an independent holdout is still recommended.
