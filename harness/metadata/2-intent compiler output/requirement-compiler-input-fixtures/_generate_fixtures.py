from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent


CASES: list[dict[str, Any]] = [
    {
        "slug": "research-scientific-reproducibility",
        "category": "research",
        "prompt": "Investigate the main causes of irreproducible results in machine-learning research. Synthesize peer-reviewed evidence, distinguish empirical findings from expert opinion, identify disagreements, and propose five testable improvements.",
        "goals": [
            "Determine the main causes of irreproducible results in machine-learning research.",
            "Propose five testable improvements grounded in the reviewed evidence.",
        ],
        "outcomes": [
            ["information", "An evidence synthesis separating empirical findings, expert opinion, and disagreements."],
            ["artifact", "A set of five testable reproducibility improvements."],
        ],
        "constraints": [
            ["content", "require", "Use peer-reviewed evidence and distinguish evidence classes.", ["peer_reviewed_evidence", "empirical_findings", "expert_opinion"]],
            ["content", "require", "Identify disagreements and provide exactly five testable improvements.", ["disagreements", "five_improvements", "testable"]],
        ],
        "ambiguity": "The publication date range and machine-learning subfields are not specified.",
        "unknowns": ["Which reported causes have the strongest replicated empirical support?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-ai-assisted-drug-discovery",
        "category": "research",
        "prompt": "Review how generative AI is being used in early-stage drug discovery. Compare demonstrated results with claimed benefits, identify major technical limitations, and list the strongest unresolved research questions.",
        "goals": [
            "Review current generative-AI applications in early-stage drug discovery.",
            "Separate demonstrated results from claimed benefits and identify unresolved questions.",
        ],
        "outcomes": [["artifact", "A comparative evidence review with limitations and prioritized open research questions."]],
        "constraints": [
            ["scope", "require", "Limit the review to early-stage drug discovery.", ["early_stage_drug_discovery"]],
            ["content", "require", "Separate demonstrated results, claimed benefits, technical limitations, and unresolved questions.", ["demonstrated_results", "claimed_benefits", "technical_limitations", "unresolved_questions"]],
        ],
        "ambiguity": "Generative AI and early-stage discovery can be defined at different levels of breadth.",
        "unknowns": ["Which claimed benefits have been independently demonstrated?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-urban-heat-mitigation",
        "category": "research",
        "prompt": "Analyze which urban heat-mitigation strategies work best in dense cities. Compare trees, reflective roofs, green roofs, shade structures, and cooling centers using effectiveness, cost, equity, and scalability.",
        "goals": ["Compare urban heat-mitigation strategies for dense cities and determine where each works best."],
        "outcomes": [["artifact", "A comparative assessment of five heat-mitigation strategies across four decision dimensions."]],
        "constraints": [
            ["content", "require", "Include all requested interventions.", ["trees", "reflective_roofs", "green_roofs", "shade_structures", "cooling_centers"]],
            ["content", "require", "Evaluate every intervention using all requested dimensions.", ["effectiveness", "cost", "equity", "scalability"]],
        ],
        "ambiguity": "The climate zones and definition of a dense city are not specified.",
        "unknowns": ["How does intervention effectiveness vary by climate and neighborhood context?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-ai-tutoring",
        "category": "research",
        "prompt": "Evaluate whether AI tutoring improves student learning compared with human tutoring and conventional educational software. Examine effect sizes, study quality, age groups, subjects, and possible harms.",
        "goals": ["Evaluate the learning effects and harms of AI tutoring against two comparison conditions."],
        "outcomes": [["artifact", "An evidence-quality-aware comparison of AI tutoring outcomes across learner and subject groups."]],
        "constraints": [
            ["content", "require", "Compare AI tutoring with human tutoring and conventional educational software.", ["ai_tutoring", "human_tutoring", "conventional_educational_software"]],
            ["content", "require", "Assess all requested evidence dimensions.", ["effect_sizes", "study_quality", "age_groups", "subjects", "possible_harms"]],
        ],
        "ambiguity": "No date range, education setting, or AI-tutor definition is specified.",
        "unknowns": ["Which effects remain after accounting for study quality and comparison condition?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-grid-storage-batteries",
        "category": "research",
        "prompt": "Compare lithium-ion, sodium-ion, solid-state, and lithium-sulfur batteries for grid storage. Evaluate energy density, lifetime, safety, material availability, cost, and commercial readiness.",
        "goals": ["Compare four battery technologies for grid-storage applications."],
        "outcomes": [["artifact", "A decision-oriented technology comparison with evidence and readiness limitations."]],
        "constraints": [
            ["content", "require", "Include all requested battery technologies.", ["lithium_ion", "sodium_ion", "solid_state", "lithium_sulfur"]],
            ["content", "require", "Evaluate every requested dimension.", ["energy_density", "lifetime", "safety", "material_availability", "cost", "commercial_readiness"]],
        ],
        "ambiguity": "Grid-storage duration and geographic market are not specified.",
        "unknowns": ["Which cost and readiness claims are supported by commercial-scale deployments?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-remote-hybrid-work",
        "category": "research",
        "prompt": "Conduct a literature review on how remote and hybrid work affect productivity, creativity, employee retention, and well-being. Explain why studies reach different conclusions.",
        "goals": ["Synthesize evidence on remote and hybrid work outcomes and explain heterogeneous study conclusions."],
        "outcomes": [["artifact", "A literature review linking outcome differences to study design, population, and work context."]],
        "constraints": [["content", "require", "Cover every requested outcome and explain conflicting conclusions.", ["productivity", "creativity", "retention", "well_being", "study_disagreement"]]],
        "ambiguity": "The industries, occupations, and post-pandemic date range are unspecified.",
        "unknowns": ["Which study-design and workforce differences explain the conflicting results?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-microplastics-health",
        "category": "research",
        "prompt": "Assess the evidence connecting microplastic exposure to human-health outcomes. Separate confirmed findings, plausible mechanisms, observational associations, and unsupported claims.",
        "goals": ["Assess the strength and type of evidence connecting microplastic exposure with human-health outcomes."],
        "outcomes": [["artifact", "An evidence map that classifies claims by support level and evidence type."]],
        "constraints": [["content", "require", "Separate all requested evidence categories.", ["confirmed_findings", "plausible_mechanisms", "observational_associations", "unsupported_claims"]]],
        "ambiguity": "Exposure routes, particle definitions, and health outcomes are not bounded.",
        "unknowns": ["Which human outcomes have causal evidence rather than observational association?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-open-weight-ai",
        "category": "research",
        "prompt": "Investigate whether open-weight language models accelerate useful innovation or primarily increase safety risks. Present the strongest evidence on both sides and identify measurements needed to resolve the debate.",
        "goals": [
            "Evaluate evidence that open-weight language models accelerate useful innovation.",
            "Evaluate evidence that open-weight language models increase safety risks and identify discriminating measurements.",
        ],
        "outcomes": [["artifact", "A balanced two-sided evidence assessment with a measurement agenda."]],
        "constraints": [["content", "require", "Present the strongest evidence for both benefits and risks without collapsing disagreement.", ["innovation_evidence", "safety_risk_evidence", "measurements"]]],
        "ambiguity": "Useful innovation and safety risk require explicit operational definitions.",
        "unknowns": ["Which measurements would causally distinguish innovation benefits from safety harms?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-autonomous-scientific-agents",
        "category": "research",
        "prompt": "Map the current state of autonomous scientific-research agents. Compare their abilities in literature review, hypothesis generation, experimentation, analysis, and reproducibility. Identify where human supervision remains essential.",
        "goals": ["Map current autonomous scientific-agent capabilities and the remaining need for human supervision."],
        "outcomes": [["artifact", "A current capability map with evidence, limitations, and supervision boundaries."]],
        "constraints": [["content", "require", "Compare every requested research capability and human-supervision boundary.", ["literature_review", "hypothesis_generation", "experimentation", "analysis", "reproducibility", "human_supervision"]]],
        "ambiguity": "Current requires a recorded search cutoff date and autonomous requires an operational definition.",
        "unknowns": ["Which claimed capabilities have been independently reproduced outside demonstrations?"],
        "execution_authorized": False,
    },
    {
        "slug": "research-longevity-interventions",
        "category": "research",
        "prompt": "Systematically compare exercise, calorie restriction, sleep optimization, metformin, rapamycin, and senolytics as longevity interventions. Separate human evidence from animal evidence and report uncertainty clearly.",
        "goals": ["Systematically compare six longevity interventions while preserving evidence-species distinctions."],
        "outcomes": [["artifact", "An uncertainty-aware comparison separating human and animal evidence."]],
        "constraints": [
            ["content", "require", "Include every requested intervention.", ["exercise", "calorie_restriction", "sleep_optimization", "metformin", "rapamycin", "senolytics"]],
            ["content", "require", "Separate human from animal evidence and report uncertainty.", ["human_evidence", "animal_evidence", "uncertainty"]],
        ],
        "ambiguity": "Longevity outcomes and acceptable surrogate endpoints are not specified.",
        "unknowns": ["Which interventions have credible human evidence for lifespan or healthspan outcomes?"],
        "execution_authorized": False,
    },
    {
        "slug": "internet-global-solar-capacity",
        "category": "internet_data",
        "prompt": "Find annual global solar-energy capacity additions from 2010 through the latest complete year. Use authoritative sources, reconcile conflicting numbers, and return a CSV-ready table with source links.",
        "goals": ["Assemble a reconciled annual series of global solar-capacity additions from 2010 through the latest complete year."],
        "outcomes": [["artifact", "A CSV-ready annual table with source links and reconciliation notes."]],
        "constraints": [
            ["scope", "require", "Cover every year from 2010 through the latest complete year.", ["2010_start", "latest_complete_year"]],
            ["content", "require", "Use authoritative sources and reconcile conflicts.", ["authoritative_sources", "conflict_reconciliation", "source_links"]],
            ["format", "require", "Return a CSV-ready table.", ["csv_ready"]],
        ],
        "ambiguity": "Solar-energy capacity may mean AC or DC capacity and the latest complete year depends on source release timing.",
        "unknowns": ["Which authoritative series use compatible capacity definitions?"],
        "execution_authorized": False,
    },
    {
        "slug": "internet-canadian-city-rentals",
        "category": "internet_data",
        "prompt": "Collect current rental prices, median incomes, population growth, and vacancy rates for the 25 largest Canadian cities. Record the measurement date, definition, unit, and source for every value.",
        "goals": ["Collect comparable housing and demographic indicators for the 25 largest Canadian cities."],
        "outcomes": [["artifact", "A source-linked city-level dataset with measurement metadata for every value."]],
        "constraints": [
            ["content", "require", "Collect all four requested indicators for 25 cities.", ["rental_prices", "median_incomes", "population_growth", "vacancy_rates", "25_cities"]],
            ["content", "require", "Record provenance and measurement metadata for every value.", ["measurement_date", "definition", "unit", "source"]],
        ],
        "ambiguity": "Largest city, rental-price statistic, and current measurement window require disclosed definitions.",
        "unknowns": ["Which city definition and source vintages yield the most comparable 25-city dataset?"],
        "execution_authorized": False,
    },
    {
        "slug": "internet-vector-database-metrics",
        "category": "internet_data",
        "prompt": "Find monthly downloads, GitHub stars, contributor counts, release frequency, and reported security incidents for five leading open-source vector databases. Return the raw data and explain comparability limitations.",
        "goals": ["Collect and compare adoption, activity, and security indicators for five leading open-source vector databases."],
        "outcomes": [["artifact", "A raw source-linked dataset plus comparability limitations."]],
        "constraints": [["content", "require", "Collect every requested metric for five projects and preserve raw values.", ["monthly_downloads", "github_stars", "contributors", "release_frequency", "security_incidents", "five_projects", "raw_data"]]],
        "ambiguity": "Leading, monthly downloads, contributor count, and security incident require explicit definitions.",
        "unknowns": ["Which five projects and metric definitions can be compared without overstating equivalence?"],
        "execution_authorized": False,
    },
    {
        "slug": "internet-glp1-weight-trials",
        "category": "internet_data",
        "prompt": "Collect clinical-trial data for GLP-1 medications used for weight management. Include sample size, treatment duration, average weight change, adverse-event withdrawals, sponsor, and trial-registration link.",
        "goals": ["Collect comparable registered clinical-trial results for GLP-1 medications used in weight management."],
        "outcomes": [["artifact", "A trial-level evidence table with outcomes, withdrawals, sponsorship, and registration links."]],
        "constraints": [["content", "require", "Record every requested trial field.", ["sample_size", "treatment_duration", "average_weight_change", "adverse_event_withdrawals", "sponsor", "trial_registration_link"]]],
        "ambiguity": "Eligible GLP-1 medications, populations, trial phases, and comparator designs are unspecified.",
        "unknowns": ["Which registered trials report sufficiently compatible weight-change and withdrawal outcomes?"],
        "execution_authorized": False,
    },
    {
        "slug": "internet-data-center-regions",
        "category": "internet_data",
        "prompt": "Find historical electricity prices, grid carbon intensity, and data-center capacity for ten potential data-center regions. Prefer government or grid-operator sources and flag missing or estimated values.",
        "goals": ["Build a historical infrastructure dataset for ten candidate data-center regions."],
        "outcomes": [["artifact", "A region-level dataset with authoritative provenance and missing/estimated-value flags."]],
        "constraints": [
            ["content", "require", "Collect all requested measures for ten regions.", ["electricity_prices", "grid_carbon_intensity", "data_center_capacity", "ten_regions"]],
            ["content", "require", "Prefer government or grid-operator sources and flag data quality.", ["government_sources", "grid_operator_sources", "missing_flags", "estimated_flags"]],
        ],
        "ambiguity": "The ten regions, historical period, customer tariff class, and capacity definition are unspecified.",
        "unknowns": ["Which regions and source definitions produce a decision-usable comparison?"],
        "execution_authorized": False,
    },
    {
        "slug": "experiment-rag-factual-accuracy",
        "category": "experiment",
        "prompt": "Test whether retrieval-augmented generation improves factual accuracy on a 100-question domain benchmark. Compare no retrieval, keyword retrieval, and embedding retrieval using accuracy, citation validity, latency, and cost.",
        "goals": ["Experimentally test whether retrieval improves factual accuracy on a 100-question domain benchmark."],
        "outcomes": [
            ["action", "Execute a controlled comparison of three retrieval conditions."],
            ["artifact", "Results covering accuracy, citation validity, latency, and cost."],
        ],
        "constraints": [
            ["content", "require", "Use the same 100-question benchmark for all conditions.", ["100_questions", "same_benchmark"]],
            ["content", "require", "Compare all conditions and metrics.", ["no_retrieval", "keyword_retrieval", "embedding_retrieval", "accuracy", "citation_validity", "latency", "cost"]],
        ],
        "ambiguity": "The domain, model, retrieval corpus, and statistical analysis are unspecified.",
        "unknowns": ["Which domain benchmark and model configuration should be frozen before execution?"],
        "execution_authorized": True,
    },
    {
        "slug": "experiment-hypothesis-paper-diversity",
        "category": "experiment",
        "prompt": "Evaluate whether an LLM generates better research hypotheses after reading diverse papers rather than only highly cited papers. Define novelty and testability metrics, run blinded scoring, and report statistical uncertainty.",
        "goals": ["Experimentally compare hypothesis quality after diverse-paper and highly-cited-paper reading conditions."],
        "outcomes": [
            ["action", "Run a blinded controlled hypothesis-generation evaluation."],
            ["artifact", "A statistically qualified comparison using defined novelty and testability metrics."],
        ],
        "constraints": [["content", "require", "Define metrics, use blinded scoring, and report statistical uncertainty.", ["novelty_metric", "testability_metric", "blinded_scoring", "statistical_uncertainty"]]],
        "ambiguity": "Paper-selection diversity, research domain, model, sample size, and evaluator pool are unspecified.",
        "unknowns": ["How should paper diversity and blinded scoring reliability be operationalized?"],
        "execution_authorized": True,
    },
    {
        "slug": "experiment-prompting-python-reliability",
        "category": "experiment",
        "prompt": "Test whether chain-of-thought prompting, structured planning, or direct prompting produces more reliable Python programs. Use the same tasks and model settings, execute every solution, and compare correctness, runtime, and token cost.",
        "goals": ["Experimentally compare Python-program reliability across three prompting strategies."],
        "outcomes": [
            ["action", "Generate and execute solutions under controlled prompting conditions."],
            ["artifact", "A comparison of correctness, runtime, and token cost."],
        ],
        "constraints": [
            ["content", "require", "Compare all three prompting strategies.", ["chain_of_thought", "structured_planning", "direct_prompting"]],
            ["content", "require", "Hold tasks and model settings fixed, execute every solution, and measure all outcomes.", ["same_tasks", "same_model_settings", "execute_every_solution", "correctness", "runtime", "token_cost"]],
        ],
        "ambiguity": "The model, task suite, sandbox, and number of repeated runs are unspecified.",
        "unknowns": ["Which task suite and execution sandbox provide a fair reliability comparison?"],
        "execution_authorized": True,
    },
    {
        "slug": "experiment-time-series-forecasting",
        "category": "experiment",
        "prompt": "Evaluate whether a proposed time-series forecasting method meaningfully outperforms seasonal naïve, ARIMA, and gradient-boosting baselines. Use multiple datasets, rolling validation, ablation tests, and confidence intervals.",
        "goals": ["Experimentally determine whether a proposed forecasting method meaningfully outperforms three baselines."],
        "outcomes": [
            ["action", "Run multi-dataset rolling-validation and ablation experiments."],
            ["artifact", "A baseline comparison with confidence intervals and practical-significance interpretation."],
        ],
        "constraints": [["content", "require", "Use all baselines and required evaluation methods.", ["seasonal_naive", "ARIMA", "gradient_boosting", "multiple_datasets", "rolling_validation", "ablation_tests", "confidence_intervals"]]],
        "ambiguity": "The proposed method, datasets, metrics, horizons, and meaningful-effect threshold are unspecified.",
        "unknowns": ["Which datasets, metrics, and effect threshold should be preregistered?"],
        "execution_authorized": True,
    },
    {
        "slug": "experiment-literature-summary-utility",
        "category": "experiment",
        "prompt": "Test whether automatically generated literature summaries help researchers answer questions faster without reducing accuracy. Design a controlled study with baseline conditions, measurable outcomes, failure criteria, and bias checks.",
        "goals": ["Design and run a controlled study of whether generated summaries improve researcher efficiency without reducing accuracy."],
        "outcomes": [
            ["action", "Execute or specify a controlled comparison against baseline conditions."],
            ["artifact", "A study protocol and results framework with outcomes, failure criteria, and bias checks."],
        ],
        "constraints": [["content", "require", "Include baseline conditions, measurable outcomes, failure criteria, and bias checks.", ["baseline_conditions", "measurable_outcomes", "failure_criteria", "bias_checks", "speed", "accuracy"]]],
        "ambiguity": "The researcher population, literature domain, summary system, and execution resources are unspecified.",
        "unknowns": ["Which participant population and question set can measure speed-accuracy tradeoffs fairly?"],
        "execution_authorized": True,
    },
    {
        "slug": "kid-sky-and-sunset-colors",
        "category": "child_question",
        "prompt": "Why is the sky blue, but sunsets are orange?",
        "goals": ["Explain why daylight skies appear blue while sunsets appear orange."],
        "outcomes": [["information", "A clear, age-appropriate causal explanation of atmospheric light scattering."]],
        "constraints": [["content", "require", "Explain both sky and sunset colors in accessible language.", ["blue_sky", "orange_sunset", "child_accessible"]]],
        "ambiguity": None,
        "unknowns": [],
        "execution_authorized": False,
    },
    {
        "slug": "kid-fish-thirst",
        "category": "child_question",
        "prompt": "Do fish ever get thirsty?",
        "goals": ["Explain whether and how fish experience water-balance needs analogous to thirst."],
        "outcomes": [["information", "An age-appropriate explanation distinguishing freshwater and saltwater fish."]],
        "constraints": [["content", "require", "Answer directly while explaining relevant freshwater and saltwater differences.", ["direct_answer", "freshwater_fish", "saltwater_fish", "child_accessible"]]],
        "ambiguity": None,
        "unknowns": [],
        "execution_authorized": False,
    },
    {
        "slug": "kid-tiny-dragon-bedtime-story",
        "category": "child_creative",
        "prompt": "Can you make up a bedtime story about a tiny dragon who is scared of fire?",
        "goals": ["Create a bedtime story about a tiny dragon who is afraid of fire."],
        "outcomes": [["artifact", "An original, gentle, child-appropriate bedtime story."]],
        "constraints": [["content", "require", "Feature a tiny dragon, fear of fire, and a bedtime-appropriate tone.", ["tiny_dragon", "afraid_of_fire", "gentle_tone", "child_appropriate"]]],
        "ambiguity": "The child's age and desired story length are not specified.",
        "unknowns": [],
        "execution_authorized": False,
    },
    {
        "slug": "kid-how-airplanes-fly",
        "category": "child_question",
        "prompt": "How do airplanes stay up when they are so heavy?",
        "goals": ["Explain how a heavy airplane generates enough lift to remain airborne."],
        "outcomes": [["information", "An age-appropriate explanation of lift, thrust, weight, and airflow."]],
        "constraints": [["content", "require", "Connect airplane weight to lift and forward motion without unnecessary jargon.", ["weight", "lift", "thrust", "airflow", "child_accessible"]]],
        "ambiguity": None,
        "unknowns": [],
        "execution_authorized": False,
    },
    {
        "slug": "kid-dinosaur-school-fit",
        "category": "child_question",
        "prompt": "If dinosaurs were alive today, could one fit inside my school?",
        "goals": ["Explain whether different dinosaurs could fit inside a school using understandable size comparisons."],
        "outcomes": [["information", "A conditional, age-appropriate comparison of dinosaur and school sizes."]],
        "constraints": [["content", "require", "Distinguish small and large dinosaurs and avoid assuming one school size.", ["small_dinosaurs", "large_dinosaurs", "school_dimensions", "child_accessible"]]],
        "ambiguity": "The dinosaur species and the school's room and doorway dimensions are not specified.",
        "unknowns": ["What school dimensions should be used for an illustrative comparison?"],
        "execution_authorized": False,
    },
]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> str:
    encoded = json_bytes(payload)
    path.write_bytes(encoded)
    return sha256_bytes(encoded)


def build_intent_ir(case_number: int, case: dict[str, Any]) -> dict[str, Any]:
    slug = case["slug"]
    prompt = case["prompt"]
    span = [[0, len(prompt)]]
    constraints = []
    for index, (category, operator, statement, values) in enumerate(case["constraints"], start=1):
        expression_operator = "contains_none" if operator == "prohibit" else "contains_all"
        constraints.append(
            {
                "constraint_id": f"C{index}",
                "category": category,
                "statement": statement,
                "expression": {
                    "op": expression_operator,
                    "args": [
                        {"ref": "requested_deliverable.content"},
                        {"set": values},
                    ],
                },
                "source_spans": span,
            }
        )

    ambiguity_rows = []
    if case["ambiguity"]:
        ambiguity_rows.append(
            {
                "ambiguity_id": "A1",
                "question": case["ambiguity"],
                "blocking": False,
                "source_spans": span,
            }
        )

    derived_from = ["G1"]
    if constraints:
        derived_from.append("C1")

    unknown_kind = "design_parameter" if case["category"] == "experiment" else "discoverable_fact"
    unknown_mode = "workflow_design" if case["category"] == "experiment" else "workflow_discovery"
    unknown_required_before = (
        "experiment_execution" if case["category"] == "experiment" else "requirement_completion"
    )

    return {
        "schema_version": "solar.intent_ir.v3",
        "artifact_role": "metadata_contract_example_not_live_execution",
        "intent_ir_id": f"intent-ir-fixture-{case_number:02d}-{slug}",
        "generation": 0,
        "raw_intent_ref": {
            "raw_intent_id": f"raw-intent-fixture-{case_number:02d}-{slug}",
            "raw_text_sha256": sha256_bytes(prompt.encode("utf-8")),
        },
        "producer": {
            "method": "model",
            "provider": "synthetic_fixture",
            "model": "codex-authored-intent-fixture-v1",
        },
        "goals": [
            {"goal_id": f"G{index}", "statement": statement, "source_spans": span}
            for index, statement in enumerate(case["goals"], start=1)
        ],
        "outcomes": [
            {
                "outcome_id": f"D{index}",
                "class": outcome_class,
                "description": description,
                "source_spans": span,
            }
            for index, (outcome_class, description) in enumerate(case["outcomes"], start=1)
        ],
        "constraints": constraints,
        "ambiguities": ambiguity_rows,
        "conflicts": [],
        "unknowns": [
            {
                "unknown_id": f"U{index}",
                "question": question,
                "kind": unknown_kind,
                "resolution": {
                    "mode": unknown_mode,
                    "required_before": unknown_required_before,
                },
                "derived_from": derived_from,
            }
            for index, question in enumerate(case["unknowns"], start=1)
        ],
    }


def main() -> None:
    catalog_cases = []
    for case_number, case in enumerate(CASES, start=1):
        case_id = f"{case_number:02d}-{case['slug']}"
        case_dir = ROOT / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        intent_ir = build_intent_ir(case_number, case)
        intent_digest = write_json(case_dir / "intent_ir.json", intent_ir)

        catalog_cases.append(
            {
                "case_id": case_id,
                "category": case["category"],
                "prompt": case["prompt"],
                "raw_intent_id": intent_ir["raw_intent_ref"]["raw_intent_id"],
                "raw_text_sha256": intent_ir["raw_intent_ref"]["raw_text_sha256"],
                "intent_ir_id": intent_ir["intent_ir_id"],
                "intent_ir_sha256": intent_digest,
                "bundle_path": case_id,
                "artifacts": ["intent_ir.json"],
                "expected_consumer": "requirement_compiler",
            }
        )

    write_json(
        ROOT / "fixture_catalog.json",
        {
            "schema_version": "solar.requirement_compiler_input_fixture_catalog.v1",
            "source_of_truth": "harness/metadata/2-intent compiler output",
            "producer": "intent_compiler",
            "consumer": "requirement_compiler",
            "case_count": len(catalog_cases),
            "cases": catalog_cases,
        },
    )


if __name__ == "__main__":
    main()
