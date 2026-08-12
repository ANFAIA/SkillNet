"""Course-level skill suggestions emitted with the pre-generation schema."""

from src.routes.ai import _skill_names_from_response


def test_skill_suggestions_are_normalized_deduplicated_and_bounded() -> None:
    parsed = {
        "skills": [
            "  Configurar   una taquilla  ",
            "configurar una TAQUILLA",
            None,
            "Resolver incidencias de acceso",
            "Interpretar pagos rechazados",
            "Gestionar invitaciones",
            "Preparar terminales",
            "Cerrar un evento",
            "Esta sugerencia debe quedar fuera del limite",
        ]
    }

    assert _skill_names_from_response(parsed) == [
        "Configurar una taquilla",
        "Resolver incidencias de acceso",
        "Interpretar pagos rechazados",
        "Gestionar invitaciones",
        "Preparar terminales",
        "Cerrar un evento",
    ]


def test_skill_suggestions_fail_closed_for_unexpected_model_output() -> None:
    assert _skill_names_from_response([]) == []
    assert _skill_names_from_response({"skills": "Configurar una taquilla"}) == []
