# Local Normalization Experiment Review Packet

## Input

The input is a six-row local benchmark that compares a baseline parser with a
normalization variant on the same exact-match labeling task. The artifact keeps
the raw prompt examples, the baseline output, the variant output, and the
source ids that tie each row back to the evaluation spreadsheet.

## Method

The method runs the baseline and variant on the same local dataset, records
accuracy, and captures latency for both modes. The evaluation uses the same
labels, the same input rows, the same metric, and the same result bundle for
both conditions. The run also records the source artifact path and a local
runtime evidence id.

## Result

The bounded conclusion is that the normalization variant improves exact-match
accuracy from 0.50 to 0.83 on this local six-row dataset while preserving
usable latency. The claim is explicitly limited to the evaluated local dataset
and does not extend beyond the recorded benchmark conditions.

## Source

Source ids: `claim:complete-local-result`, `exp:complete-local-run`,
`code:claim-supported`. The linked evidence package includes the experiment
result JSON, the claim JSON, the code evidence map, and the local source notes
for the benchmark rows.
