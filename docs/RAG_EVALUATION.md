# STEP 08 RAG Evaluation

- Evaluation cases: 100
- K: 5
- Dataset: `data/evaluation/rag_cases.json`

| Strategy | Recall@5 | MRR@5 | nDCG@5 | Precision@5 | Citation Precision | Abstention Accuracy | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| keyword | 0.9062 | 0.8510 | 0.8605 | 0.1875 | 0.5535 | 0.1000 | 1.48 | 1.81 |
| vector | 0.8688 | 0.6927 | 0.7357 | 0.1800 | 0.1800 | 0.0000 | 6.09 | 17.32 |
| hybrid | 0.9500 | 0.8504 | 0.8762 | 0.1975 | 0.1975 | 0.0000 | 6.98 | 11.66 |
| rerank | 0.9125 | 0.8160 | 0.8340 | 0.1875 | 0.1875 | 0.0000 | 185.37 | 223.56 |
| rerank_prod | 0.6625 | 0.6542 | 0.6499 | 0.1375 | 0.5921 | 0.7500 | 185.37 | 223.56 |

## Notes

- Positive cases evaluate Recall, MRR, nDCG, Precision and citation precision.
- Negative cases evaluate whether the strategy returns no accepted evidence.
- Rerank raw reports unthresholded ranking quality.
- Rerank prod applies a calibrated minimum score of -2.9.
- The threshold -2.9 was calibrated on the original 30-case subset; the current set has 100 cases, and an independent holdout is still recommended.
## Holdout Check (70/30 stratified split)

- Split: 65 tune / 35 holdout (every 3rd case per category).
- A margin-based rule tuned on the tune set did **not** generalize (holdout Recall 0.5536 vs 0.5893 for the baseline), so the production rule stays `rerank_score >= -2.9`.
- Holdout @ -2.9: Recall@5 0.5893, Citation Precision 0.4762, Abstention 0.7143.
- Tune @ -2.9: Recall@5 0.7019, Citation Precision 0.6571, Abstention 0.7692.
- Interpretation: with 100 cases the split-to-split variance is large; a larger independent holdout is still needed.
