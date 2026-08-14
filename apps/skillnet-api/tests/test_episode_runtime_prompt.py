from src.llm.prompts.runtime import (
    ANSWER_KEY_SENTINEL,
    build_episode_repair_prompt,
    build_episode_ui_prompt,
    episode_ui_generator_system,
    episode_ui_repair_system,
)


def ticket_episode() -> dict:
    return {
        "dominant_action": {
            "verb": "recover_ticket",
            "target": "Solicitud del comprador en la plataforma correcta",
            "submission_kind": "case_transition_log",
            "instructions": "Recupera la entrada sin saltarte la verificacion de identidad.",
            "constraints": {
                "preserve_order": True,
                "oracle_ref": "ticket-oracle/private",
                "answer_key": "never expose",
            },
        },
        "assessment_mode": "summative",
        "evidence_gate_refs": ["complete-case"],
        "belief_snapshot": {
            "mastery": 0.35,
            "confidence": 0.6,
            "recent_error_kinds": ["wrong-platform"],
            "hints_used": 1,
            "experience_level": "novice",
            "state_digest": "private-state",
        },
        "budget": {
            "max_content_units": 4,
            "max_interaction_steps": 8,
            "max_words": 220,
            "max_media_seconds": 90,
            "latency_budget_ms": 2500,
        },
        "policy_trace": {"answer_key": "never expose", "oracle": "private"},
    }


def sql_episode() -> dict:
    return {
        "dominant_action": {
            "verb": "execute_query",
            "target": "Dataset congelado de pedidos",
            "submission_kind": "sql_text",
            "instructions": "Escribe y ejecuta una consulta agrupada por cliente.",
            "constraints": {"read_only": True, "network": False},
        },
        "assessment_mode": "formative",
        "belief_snapshot": {
            "mastery": 0.7,
            "confidence": 0.8,
            "recent_error_kinds": ["missing-group-by"],
            "hints_used": 0,
            "experience_level": "intermediate",
        },
        "budget": {
            "max_content_units": 2,
            "max_interaction_steps": 5,
            "max_words": 140,
            "latency_budget_ms": 900,
        },
    }


def assert_has_no_screen_formula(prompt: str) -> None:
    lowered = prompt.lower()
    forbidden = (
        "screen_scheme",
        "esquema de esta pantalla",
        "formato que debes producir",
        "lead + concepto + practica",
        "lead + concept + practice",
        "primer bloque siempre",
        "siempre acaba con quizitem",
        "table + quizitem",
        "assessment.py",
        "shape_hints",
    )
    for phrase in forbidden:
        assert phrase not in lowered


def test_episode_system_keeps_dialect_and_security_without_legacy_formula() -> None:
    system = episode_ui_generator_system()
    normalized = " ".join(system.split())

    assert "root = Stack" in system
    assert "## Component Signatures" in system
    assert "SkillNet 4" in system
    assert "SkillNet 14" in system
    assert "SkillNet 18" in system
    assert "SkillNet 20" in system
    assert "SkillNet 21" in system
    assert "SkillNet 19" not in system
    assert "la fuente publica son la unica verdad" in system
    assert "ni anadas una evaluacion por costumbre" in normalized
    assert ANSWER_KEY_SENTINEL in system
    assert '"true_false": {"correct": true|false' in system
    assert '"fill_blank": {"blanks":' in system
    assert '"order_steps": {"correct_order":' in system
    assert "## Examples" not in system
    assert 'variant: "body" | "lead"' not in system
    assert "SkillNet 8" not in system
    assert_has_no_screen_formula(system)


def test_episode_repair_system_uses_same_neutral_contract() -> None:
    system = episode_ui_repair_system()

    assert "corrigiendo solo los errores enumerados" in system
    assert "no alteres la mision" in system
    assert "## Component Signatures" in system
    assert "## Examples" not in system
    assert_has_no_screen_formula(system)


def test_tickets_and_sql_produce_materially_different_episode_prompts() -> None:
    tickets = build_episode_ui_prompt(
        episode=ticket_episode(),
        source_context=(
            "Si el correo no coincide, verifica la identidad antes de reenviar. "
            "Selecciona Crocantickets, Vivetix o Pretix segun el pedido."
        ),
    )
    sql = build_episode_ui_prompt(
        episode=sql_episode(),
        source_context=(
            "La tabla orders contiene customer_id y amount. La consulta debe agrupar "
            "por customer_id y calcular SUM(amount)."
        ),
    )

    assert "recover_ticket" in tickets
    assert "case_transition_log" in tickets
    assert "verificacion de identidad" in tickets
    assert "execute_query" not in tickets
    assert "execute_query" in sql
    assert "sql_text" in sql
    assert "SUM(amount)" in sql
    assert "recover_ticket" not in sql
    assert tickets != sql
    assert_has_no_screen_formula(tickets)
    assert_has_no_screen_formula(sql)


def test_builder_allowlist_does_not_leak_private_evaluation_material() -> None:
    prompt = build_episode_ui_prompt(
        episode=ticket_episode(),
        source_context="La fuente publica solo describe el proceso permitido.",
    )

    assert "ticket-oracle/private" not in prompt
    assert "never expose" not in prompt
    assert "private-state" not in prompt
    assert "complete-case" not in prompt
    assert "preserve_order" in prompt
    assert "No muestres el oraculo" in prompt


def test_unassessed_episode_does_not_demand_a_closing_question() -> None:
    episode = ticket_episode()
    episode["assessment_mode"] = "none"

    prompt = build_episode_ui_prompt(episode=episode, source_context="Proceso publico.")

    assert "no exige evidencia evaluada" in prompt
    assert "no anadas un cierre artificial" in prompt
    assert "Modo declarado" not in prompt


def test_episode_repair_restates_mission_source_and_errors_without_formula() -> None:
    prompt = build_episode_repair_prompt(
        episode=sql_episode(),
        source_context="orders(customer_id, amount)",
        previous='root = Stack([code], "md")',
        errors=("linea 1: referencia code sin definir",),
    )

    assert "execute_query" in prompt
    assert "orders(customer_id, amount)" in prompt
    assert "referencia code sin definir" in prompt
    assert 'root = Stack([code], "md")' in prompt
    assert_has_no_screen_formula(prompt)
