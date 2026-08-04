"""Seed demo data for trying out SkillNet.

Run from inside the API container:
    python -m src.seed_demo

Or from the host:
    docker compose exec api python -m src.seed_demo

Creates a demo employee, skill taxonomy (4 categories, 16 skills),
and assigns skills to both admin and employee at realistic levels.
Idempotent — safe to run multiple times.
"""

import asyncio

from sqlalchemy import select

from src.core.logging import configure_logging, get_logger
from src.deps.db import async_session_factory, engine
from src.models import (
    Organization,
    Skill,
    SkillCategory,
    SkillLevel,
    User,
    UserRole,
    UserSkill,
)

configure_logging("INFO")
logger = get_logger(__name__)

DEMO_EMPLOYEE_EMAIL = "empleado@demo.skillnet.dev"
DEMO_EMPLOYEE_PASSWORD = "demo1234"
DEMO_EMPLOYEE_NAME = "Maria Garcia"

TAXONOMY: dict[str, list[tuple[str, str]]] = {
    "Cocina": [
        ("manipulacion_alimentos", "Higiene y seguridad alimentaria"),
        ("preparacion_platos", "Elaboracion de platos"),
        ("control_temperaturas", "Control de temperaturas y conservacion"),
        ("gestion_alergenos", "Identificacion y gestion de alergenos"),
    ],
    "Atencion al cliente": [
        ("atencion_cliente", "Trato directo con el cliente"),
        ("gestion_quejas", "Resolucion de quejas y reclamaciones"),
        ("upselling", "Tecnicas de venta adicional"),
        ("idioma_ingles", "Atencion al cliente en ingles"),
    ],
    "Operaciones": [
        ("caja_tpv", "Manejo de caja registradora y TPV"),
        ("apertura_cierre", "Procedimientos de apertura y cierre"),
        ("limpieza_protocolo", "Protocolos de limpieza e higiene"),
        ("prevencion_riesgos", "Prevencion de riesgos laborales"),
    ],
    "Gestion": [
        ("gestion_turnos", "Planificacion y gestion de turnos"),
        ("formacion_equipo", "Capacidad para formar a nuevos empleados"),
        ("gestion_proveedores", "Relacion con proveedores y pedidos"),
        ("control_costes", "Control de costes y margenes"),
    ],
}

ADMIN_SKILLS: dict[str, SkillLevel] = {
    "gestion_turnos": SkillLevel.HIGH,
    "formacion_equipo": SkillLevel.HIGH,
    "gestion_proveedores": SkillLevel.HIGH,
    "control_costes": SkillLevel.HIGH,
    "apertura_cierre": SkillLevel.MEDIUM,
    "prevencion_riesgos": SkillLevel.MEDIUM,
    "caja_tpv": SkillLevel.MEDIUM,
}

EMPLOYEE_SKILLS: dict[str, SkillLevel] = {
    "caja_tpv": SkillLevel.MEDIUM,
    "apertura_cierre": SkillLevel.LOW,
    "limpieza_protocolo": SkillLevel.MEDIUM,
    "prevencion_riesgos": SkillLevel.LOW,
    "atencion_cliente": SkillLevel.MEDIUM,
    "gestion_quejas": SkillLevel.MEDIUM,
    "upselling": SkillLevel.LOW,
    "manipulacion_alimentos": SkillLevel.LOW,
}


async def seed() -> None:
    async with async_session_factory() as session:
        # Get org
        org = (await session.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            print("ERROR: No organization found. Start the app first.")
            return

        # Idempotency: skip if demo employee exists
        existing = await session.execute(
            select(User).where(User.email == DEMO_EMPLOYEE_EMAIL)
        )
        if existing.scalar_one_or_none() is not None:
            print("Demo data already exists. Nothing to do.")
            return

        # 1. Create demo employee
        from fastapi_users.password import PasswordHelper

        employee = User(
            email=DEMO_EMPLOYEE_EMAIL,
            hashed_password=PasswordHelper().hash(DEMO_EMPLOYEE_PASSWORD),
            org_id=org.id,
            full_name=DEMO_EMPLOYEE_NAME,
            role=UserRole.EMPLOYEE,
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(employee)
        await session.flush()
        print(f"  Created employee: {DEMO_EMPLOYEE_EMAIL} / {DEMO_EMPLOYEE_PASSWORD}")

        # 2. Create skill taxonomy
        skill_map: dict[str, Skill] = {}
        for position, (cat_name, skill_defs) in enumerate(TAXONOMY.items()):
            cat = (await session.execute(
                select(SkillCategory).where(
                    SkillCategory.org_id == org.id, SkillCategory.name == cat_name
                )
            )).scalar_one_or_none()
            if cat is None:
                cat = SkillCategory(org_id=org.id, name=cat_name, position=position)
                session.add(cat)
                await session.flush()

            for skill_name, skill_desc in skill_defs:
                skill = (await session.execute(
                    select(Skill).where(
                        Skill.org_id == org.id, Skill.name == skill_name
                    )
                )).scalar_one_or_none()
                if skill is None:
                    skill = Skill(
                        org_id=org.id,
                        category_id=cat.id,
                        name=skill_name,
                        description=skill_desc,
                    )
                    session.add(skill)
                    await session.flush()
                skill_map[skill_name] = skill

        print(f"  Created {len(TAXONOMY)} categories, {len(skill_map)} skills")

        # 3. Assign skills
        admin = (await session.execute(
            select(User).where(User.org_id == org.id, User.role == UserRole.ADMIN).limit(1)
        )).scalar_one_or_none()

        async def assign(user: User | None, assignments: dict[str, SkillLevel]) -> int:
            if user is None:
                return 0
            count = 0
            for s_name, level in assignments.items():
                skill = skill_map.get(s_name)
                if skill is None:
                    continue
                exists = (await session.execute(
                    select(UserSkill).where(
                        UserSkill.user_id == user.id, UserSkill.skill_id == skill.id
                    )
                )).scalar_one_or_none()
                if exists is not None:
                    continue
                session.add(UserSkill(
                    user_id=user.id, skill_id=skill.id, level=level, source="demo_seed",
                ))
                count += 1
            return count

        a_count = await assign(admin, ADMIN_SKILLS)
        e_count = await assign(employee, EMPLOYEE_SKILLS)

        await session.commit()
        print(f"  Assigned {a_count} skills to admin, {e_count} skills to employee")
        print()
        print("Done! Demo accounts:")
        print("  Admin:    admin (use the email/password from your .env)")
        print(f"  Employee: {DEMO_EMPLOYEE_EMAIL} / {DEMO_EMPLOYEE_PASSWORD}")

    await engine.dispose()


if __name__ == "__main__":
    print()
    print("SkillNet — Seeding demo data...")
    print()
    asyncio.run(seed())
