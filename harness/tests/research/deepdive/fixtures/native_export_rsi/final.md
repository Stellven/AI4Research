# Recursive Self-Improving Models

## Introduction

Recursive self-improvement (RSI) describes systems whose design lets them improve their own ability to improve; the classic framing predicts ultraintelligent machines that design ever-better machines [cite:ev_1], while modern work trains on self-generated rationales and reasoning traces [cite:ev_2].

## Evidence Synthesis

Verbal self-reflection improves later attempts [cite:ev_3]; iterative refinement lets a model refine its own outputs [cite:ev_4]; step-level process supervision beats outcome-only reward [cite:ev_5]; and verifier-driven selection raises accuracy over unverified self-improvement [cite:ev_7].

## Contradictions and Limits

Self-reflection gains are capped by the fidelity of the feedback signal [cite:ev_8], and automated discovery still depends on a reviewer running experiments in the loop [cite:ev_6].

## Engineering Implications

The engineering implication is a design that pairs self-generated rationales [cite:ev_2] with a verifier-driven selection gate [cite:ev_7], adding explicit evaluation and failure boundaries rather than open-ended self-modification.
