from src.agents.runtime.screen_eval import (
    CriticalFact,
    ScreenScenario,
    evaluate_corpus,
    evaluate_screen,
    reachable_component_ids,
)


def _spec(*components: dict, root: str = "root") -> dict:
    return {"root": root, "components": list(components)}


def test_reachability_follows_children_and_ignores_declared_orphans() -> None:
    spec = _spec(
        {"id": "root", "type": "Stack", "children": ["lead", "action"]},
        {"id": "lead", "type": "Text", "props": {"text": "Empieza"}},
        {"id": "action", "type": "FutureSimulation", "children": ["nested"]},
        {"id": "nested", "type": "Control"},
        {"id": "lost", "type": "CriticalWarning", "props": {"text": "Llama al 112"}},
    )

    assert reachable_component_ids(spec) == ("root", "lead", "action", "nested")


def test_screen_eval_measures_focus_orphans_redundancy_and_reachable_safety() -> None:
    scenario = ScreenScenario(
        id="extinguisher-a",
        objective="reconstruct-procedure",
        blueprint={
            "blocks": [
                {"id": "lead", "type": "Text", "intent": "enganchar"},
                {"id": "action", "type": "FutureSimulation", "intent": "concepto"},
                {"id": "check", "type": "FutureCheck", "intent": "verificar"},
            ]
        },
        ui_spec=_spec(
            {"id": "root", "type": "Stack", "children": ["lead", "action", "extra", "check"]},
            {"id": "lead", "type": "Text", "props": {"text": "Actúa ante un conato"}},
            {
                "id": "action",
                "type": "FutureSimulation",
                "props": {"text": "Evacúa y llama al 112 si supera tu cintura"},
            },
            {
                "id": "extra",
                "type": "AnyNewLibraryComponent",
                "props": {"text": "Evacúa y llama al 112 si supera tu cintura"},
            },
            {"id": "check", "type": "FutureCheck", "props": {"prompt": "¿Qué harías?"}},
            {"id": "lost", "type": "Warning", "props": {"text": "Dato invisible"}},
        ),
        critical_facts=(
            CriticalFact(id="emergency", any_of=("112", "emergencias")),
            CriticalFact(id="limit", any_of=("supera tu cintura",)),
        ),
    )

    metrics = evaluate_screen(scenario)

    assert metrics.reachable_count == 5
    assert metrics.unreachable_ids == ("lost",)
    assert metrics.planned_reachability == 1.0
    assert metrics.orphan_reachable_ids == ("extra",)
    assert metrics.central_mission_score == 1.0
    assert metrics.redundant_pairs == (("action", "extra"),)
    assert metrics.critical_preservation == 1.0


def test_missing_central_block_and_orphaned_fact_fail_the_relevant_scores() -> None:
    scenario = ScreenScenario(
        id="unsafe",
        objective="decide",
        blueprint={"blocks": [{"id": "concept", "type": "X", "intent": "concepto"}]},
        ui_spec=_spec(
            {"id": "root", "type": "Stack", "children": []},
            {"id": "concept", "type": "X", "props": {"text": "Llama al 112"}},
        ),
        critical_facts=(CriticalFact(id="emergency", any_of=("112",)),),
    )

    metrics = evaluate_screen(scenario)

    assert metrics.planned_reachability == 0.0
    assert metrics.central_mission_score == 0.0
    assert metrics.critical_fact_misses == ("emergency",)
    assert metrics.critical_preservation == 0.0


def test_ui_spec_without_blueprint_does_not_invent_orphans() -> None:
    metrics = evaluate_screen(
        ScreenScenario(
            id="observed-only",
            objective="unknown",
            ui_spec=_spec(
                {"id": "root", "type": "Stack", "children": ["action"]},
                {"id": "action", "type": "FutureSimulation"},
            ),
        )
    )

    assert metrics.planned_reachability is None
    assert metrics.orphan_reachable_ids == ()
    assert metrics.central_mission_score is None


def test_two_central_actions_are_penalized_without_knowing_component_catalogue() -> None:
    scenario = ScreenScenario(
        id="flat",
        objective="interpret",
        blueprint={
            "blocks": [
                {"id": "a", "type": "BrandNewChart", "intent": "concepto"},
                {"id": "b", "type": "AnotherWidget", "intent": "concepto"},
            ]
        },
        ui_spec=_spec(
            {"id": "root", "type": "Layout", "children": ["a", "b"]},
            {"id": "a", "type": "BrandNewChart"},
            {"id": "b", "type": "AnotherWidget"},
        ),
    )

    assert evaluate_screen(scenario).central_mission_score == 0.5


def test_corpus_separates_cross_objective_diversity_from_repeat_stability() -> None:
    def result(case_id: str, objective: str, component_type: str):
        return evaluate_screen(
            ScreenScenario(
                id=case_id,
                objective=objective,
                blueprint={"blocks": [{"id": "action", "intent": "concepto"}]},
                ui_spec=_spec(
                    {"id": "root", "type": "Stack", "children": ["action"]},
                    {"id": "action", "type": component_type},
                ),
            )
        )

    screens = [
        result("a1", "reconstruct", "Sequence"),
        result("a2", "reconstruct", "Sequence"),
        result("b1", "compare", "BeforeAfter"),
    ]

    corpus = evaluate_corpus(screens, ignore_types=("Stack",))

    assert corpus.distinct_signatures == 2
    assert corpus.same_objective_stability == 1.0
    assert corpus.cross_objective_diversity == 1.0
