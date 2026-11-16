# Manuscript figures

Original PNG and SVG artwork is preserved byte for byte. Plot data are supplied externally; plotting code is in `biotracebench_analysis.publication.plot`.

## Figure 1

[PNG](Figure1.png) · [SVG](Figure1.svg)

Figure 1. From study materials to linked tables. (a) Clinical and basic research studies. (b) Sources supplied with a task. (c) The model receives the sources and task instructions. (d) Arrows identify references between tables. API denotes application programming interface and LLM denotes large language model.

## Figure 2

[PNG](Figure2.png) · [SVG](Figure2.svg)

Figure 2. Experimental Fidelity Evaluation. One mapping between submitted and reference objects governs all field and record judgments. Source review settles disputed identities or content. Programs verify coverage and count matches.

## Figure 3

[PNG](Figure3.png) · [SVG](Figure3.svg)

Figure 3. Field and record F1 across studies for each model. Boxes show the median and interquartile range. Whiskers extend to the most extreme observation within 1.5 interquartile ranges of the box. Circles mark observed scores and crosses mark assigned zeros. Field F1 covers 100 studies and Record F1 covers the 99 with eligible complete targets.

## Figure 4

[PNG](Figure4.png) · [SVG](Figure4.svg)

Figure 4. Recovered fields assigned to the wrong object or context. Points give each domain equal weight. Lines show 95% intervals from resampling studies within domains. The diamond identifies Qwen3.8 Flash, the model in the query example.

## Figure 5

[PNG](Figure5.png) · [SVG](Figure5.svg)

Figure 5. Answers with a classified error in each category. Circles represent clinical studies (596 answers) and diamonds basic research (594 answers). Each category counts an answer at most once.

## Figure 6

[PNG](Figure6.png) · [SVG](Figure6.svg)

Figure 6. Recall by record structure. (a) Study-weighted complete-record recall by record type and width. Labels give study counts. Bars show 95% intervals for at least five studies. (b) Mean link recall across models for each study with reference links, plotted against link count on a logarithmic scale. Circles denote clinical studies and triangles basic research. Intervals resample studies within domain.

## Figure 7

[PNG](Figure7.png) · [SVG](Figure7.svg)

Figure 7. Overall Field F1 and estimated generation cost per study. The horizontal axis uses a logarithmic scale in US dollars. Quality covers all 100 studies. Costs include retries and use complete usage records. Open markers denote configurations with incomplete cost coverage (Table 4).

## Supplementary Figure A1

[PNG](FigureA1_Study_Model_Heatmap.png) · [SVG](FigureA1_Study_Model_Heatmap.svg)

Figure A1. F1 by study and model. Each domain contains 50 studies, ordered by increasing mean Field F1 across all 12 models. The two metrics share the study order and the 0–100% color scale. Crosses identify positions assigned zero because of failure or missing output. Study identifiers link to article titles and DOIs in the accompanying study index.

## Supplementary Figure A2

[PNG](FigureA2_Synthetic_Scoring.png) · [SVG](FigureA2_Synthetic_Scoring.svg)

Figure A2. Field and complete-record scoring in a synthetic trial. Both outputs achieve Field F1 of 72.7%. Record F1 differs because the errors affect different numbers of records. Dashes mark omissions, and check marks identify complete records.
