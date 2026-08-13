"""Who may generate course-level media artifacts."""

import uuid

from src.services.artifact_access import can_generate_artifacts


ADMIN = uuid.UUID("11111111-1111-1111-1111-111111111111")
EMPLOYEE = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER = uuid.UUID("33333333-3333-3333-3333-333333333333")


def test_admin_can_always_generate() -> None:
    assert can_generate_artifacts(
        role="admin", user_id=ADMIN, policy="admin", generator_ids=[]
    )
    assert can_generate_artifacts(
        role="admin", user_id=ADMIN, policy="selected", generator_ids=[]
    )


def test_everyone_lets_an_employee_generate() -> None:
    assert can_generate_artifacts(
        role="employee", user_id=EMPLOYEE, policy="everyone", generator_ids=[]
    )


def test_admin_policy_blocks_employees() -> None:
    assert not can_generate_artifacts(
        role="employee", user_id=EMPLOYEE, policy="admin", generator_ids=[]
    )


def test_selected_policy_is_an_allow_list() -> None:
    assert can_generate_artifacts(
        role="employee",
        user_id=EMPLOYEE,
        policy="selected",
        generator_ids=[EMPLOYEE],
    )
    assert not can_generate_artifacts(
        role="employee",
        user_id=OTHER,
        policy="selected",
        generator_ids=[EMPLOYEE],
    )
