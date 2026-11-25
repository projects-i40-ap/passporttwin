# MVP evaluation closeout

Updated on 24 November 2026 from the reports archived for the thesis. The experiments task was closed after the seven workflows, within the agreed scope. These experiments have not been rerun for this documentation update.

## Results and conclusions

| EXP | Evidence | Interpretation and limitation |
| --- | --- | --- |
| 01 | 168/168 matches: 162 present values and six expected missing values, across 24 synthetic PDFs in three layouts. | Deterministic extractor results on the evaluated corpus. Does not measure OCR or LLM-assisted extraction from arbitrary documents. |
| 02 | 27 cases: 18 correct links and nine correct abstentions; three missing, three unknown and three ambiguous serial numbers. | Preserves human decision-making when identity is not unambiguous. Synthetic catalog of three instruments. |
| 03 | Expected rules in 24 PDFs: 21 alerts and three cases without alerts. Two supplementary checks passed. | The same PDF under a different filename was rejected with HTTP 409/R-DUP-01; acceptance of an error of −0.128 bar against a tolerance of 0.1 bar was recorded as out of tolerance in the calibration, instrument and audit trail. Does not demonstrate duplicate prevention under concurrency. |
| 04 | 576 trajectories; overall normalized MAE of 0.285 for M1 versus 0.329 for B0/B1. | At 30 days: 0.198 versus 0.160. Improves at 60/90 days, but does not meet the comparative improvement criterion at every horizon. |
| 05 | Paired Brier score of 0.108 versus 0.154 across 1,512 predictions; 216 abstentions and estimation coverage of 87.5%. | Precision 55.7%, recall 49.8% and F1 0.526 at a threshold of 0.5. Nominal 95% intervals achieved 77.7% observed coverage: probabilities are not presented as calibrated for industrial use. |
| 06 | Two AASX cases: 129/129 and 43/43 critical entries preserved at every evaluated boundary. | Controlled profile between two empty BaSyx repositories. Does not certify every AAS/IDTA implementation or arbitrary binary content. |
| 07 | CERT and TRACE completed; reported times below 3 and 5 minutes. | Practical participant check without exact timing. Closed within that scope; not an AB/BA comparative study or statistical evidence of time savings. |

## Provenance and versions

The document and AASX reports record `f0978fbc77dfc346de79eeedd67c2afc094386ec`. In the AASX report, the commit was supplied by the operator (`caller_supplied_not_verified`), not independently verified against the working tree. The supplementary EXP-03 tests record the same revision.

The public summary of the automated reports is preserved in the [results package](../../experiments/results/mvp-closeout-2026-11-24.json). It contains selected metrics without recalculation and the SHA-256 of each local source report. This is a summarized publication, not the complete corpus or a promise of reproducibility from that JSON alone. Originals, the corpus and screenshots were archived for the thesis; personal paths, real certificates and credentials are not published here.

EXP-04/05 used a synthetic cohort of three families and eight scenarios, with 24 trajectories per combination, eight historical observations and three future observations per trajectory. Horizons from the same trajectory are correlated. EXP-04 executed numerical methods extracted from the code; EXP-05 imported risk services. They were not end-to-end tests of the deployed application.

EXP-07 is supported by the task record and the outcome reported by Pau. No exact times, additional participants or observations from a formal study have been invented.

## Relationship to earlier protocols

The [readiness document](final-execution-readiness.md) and [historical matrix](final-experiments-matrix.md) reflect planning on 2 November and earlier. They are retained as background. The formal [EXP-07 protocol](exp07-traceability-study.md) has a broader scope than the check ultimately performed; that comparative study remains a possible future evaluation.

The runners and their guides remain available for new evaluations. Each new run must record its own commit, data, date, parameters and deviations. Do not transfer this cohort's results to other formats, models, versions or installations without verification.

## Outside the closeout scope

Validation with industrial fleets, metrological certification, probability calibration on real data, comprehensive AI/OCR/RAG evaluation, concurrency, production restoration and a formal usability study are outside the MVP's conclusions. Academic completion also does not establish a granted patent or a certified industrial product.
