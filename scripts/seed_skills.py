#!/usr/bin/env python3
"""Seed the database with realistic skill categories, skills, and user-skill assignments.

Usage:
    # From the repo root, with the API running:
    python scripts/seed_skills.py [--api-url http://localhost:8000] [--api-key KEY]

    # Or directly against the DB (requires DATABASE_URL env var):
    python scripts/seed_skills.py --direct

This script creates a realistic skill taxonomy for a restaurant/retail PYME
and assigns skills to existing users at varied levels.
"""

import argparse
import asyncio
import hashlib
import os
import random
import uuid

# ---------------------------------------------------------------------------
# Skill taxonomy — realistic for restaurant/retail PYMEs
# ---------------------------------------------------------------------------

TAXONOMY = {
    "Cocina": [
        ("manipulacion_alimentos", "Higiene y seguridad alimentaria"),
        ("preparacion_sushi", "Tecnicas de preparacion de sushi y makis"),
        ("cocina_caliente", "Elaboracion de platos calientes"),
        ("reposteria", "Postres y reposteria basica"),
        ("gestion_stock_cocina", "Control de inventario y pedidos de cocina"),
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

# Skill assignments: (skill_name, level, probability)
# Higher probability = more employees have it
ASSIGNMENT_PROFILES = {
    "admin": {
        # Admins tend to have management skills
        "gestion_turnos": ("high", 0.9),
        "formacion_equipo": ("high", 0.8),
        "control_costes": ("high", 0.7),
        "gestion_proveedores": ("medium", 0.7),
        "atencion_cliente": ("high", 0.6),
        "apertura_cierre": ("high", 0.8),
        "caja_tpv": ("medium", 0.5),
    },
    "employee": {
        # Employees have varied operational skills
        "manipulacion_alimentos": ("medium", 0.8),
        "atencion_cliente": ("medium", 0.7),
        "caja_tpv": ("low", 0.6),
        "limpieza_protocolo": ("medium", 0.7),
        "apertura_cierre": ("low", 0.4),
        "cocina_caliente": ("low", 0.5),
        "preparacion_sushi": ("low", 0.3),
        "upselling": ("low", 0.4),
        "prevencion_riesgos": ("low", 0.5),
        "gestion_quejas": ("low", 0.3),
        "idioma_ingles": ("low", 0.2),
        "reposteria": ("low", 0.2),
    },
}


async def seed_direct() -> None:
    """Seed directly via SQLAlchemy (requires DB access)."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://skillnet:skillnet@localhost:5432/skillnet",
    )

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # Get org
        result = await session.execute(text("SELECT id FROM organizations LIMIT 1"))
        row = result.first()
        if row is None:
            print("ERROR: No organization found. Run the app first.")
            return
        org_id = row[0]
        print(f"Organization: {org_id}")

        # Get users
        result = await session.execute(
            text("SELECT id, role, full_name FROM users WHERE org_id = :org_id"),
            {"org_id": org_id},
        )
        users = result.all()
        if not users:
            print("ERROR: No users found. Create users first.")
            return
        print(f"Found {len(users)} users")

        # Check if skills already exist
        result = await session.execute(
            text("SELECT COUNT(*) FROM skills WHERE org_id = :org_id"),
            {"org_id": org_id},
        )
        existing_count = result.scalar()
        if existing_count and existing_count > 0:
            print(f"WARNING: {existing_count} skills already exist. Skipping seed.")
            return

        # Create categories and skills
        skill_ids: dict[str, uuid.UUID] = {}

        for cat_name, skills in TAXONOMY.items():
            cat_id = uuid.uuid4()
            position = list(TAXONOMY.keys()).index(cat_name)
            await session.execute(
                text(
                    "INSERT INTO skill_categories (id, org_id, name, position) "
                    "VALUES (:id, :org_id, :name, :position)"
                ),
                {"id": cat_id, "org_id": org_id, "name": cat_name, "position": position},
            )
            print(f"  Category: {cat_name}")

            for skill_name, description in skills:
                s_id = uuid.uuid4()
                skill_ids[skill_name] = s_id
                await session.execute(
                    text(
                        "INSERT INTO skills (id, org_id, category_id, name, description) "
                        "VALUES (:id, :org_id, :cat_id, :name, :desc)"
                    ),
                    {
                        "id": s_id,
                        "org_id": org_id,
                        "cat_id": cat_id,
                        "name": skill_name,
                        "desc": description,
                    },
                )
                print(f"    Skill: {skill_name}")

        # Assign skills to users
        assignments = 0
        for user_id, role, full_name in users:
            role_str = role if isinstance(role, str) else role.value
            profile = ASSIGNMENT_PROFILES.get(role_str, ASSIGNMENT_PROFILES["employee"])

            for skill_name, (level, prob) in profile.items():
                if random.random() > prob:
                    continue
                if skill_name not in skill_ids:
                    continue

                # Vary levels slightly for realism
                levels = ["low", "medium", "high"]
                level_idx = levels.index(level)
                # 30% chance to be one level different
                if random.random() < 0.3:
                    level_idx = max(0, min(2, level_idx + random.choice([-1, 1])))
                final_level = levels[level_idx]

                us_id = uuid.uuid4()
                await session.execute(
                    text(
                        "INSERT INTO user_skills (id, user_id, skill_id, level, source) "
                        "VALUES (:id, :uid, :sid, :level, 'seed') "
                        "ON CONFLICT (user_id, skill_id) DO NOTHING"
                    ),
                    {
                        "id": us_id,
                        "uid": user_id,
                        "sid": skill_ids[skill_name],
                        "level": final_level,
                    },
                )
                assignments += 1

            print(f"  User: {full_name} ({role_str})")

        await session.commit()

        print(f"\nDone! Created {len(skill_ids)} skills in {len(TAXONOMY)} categories.")
        print(f"Assigned {assignments} user-skill records.")

    await engine.dispose()


async def seed_via_api(api_url: str, api_key: str) -> None:
    """Seed via the external API (requires API key)."""
    import httpx

    headers = {"Authorization": f"Bearer {api_key}"}
    base = api_url.rstrip("/")

    async with httpx.AsyncClient(base_url=base, headers=headers, timeout=30.0) as client:
        # Check connectivity
        resp = await client.get("/ext/v1/skills")
        if resp.status_code == 403:
            print("ERROR: Invalid API key. Set --api-key or A2A_INTERNAL_API_KEY.")
            return
        resp.raise_for_status()

        existing = resp.json()
        if existing:
            print(f"Skills already exist ({len(existing)} categories). Skipping.")
            return

        print("API seed mode — creating skills via verify endpoint...")
        # We can only create skills via verify_skill (which auto-creates)
        # This is limited without direct DB access, so we just create skills
        # by verifying a dummy user. Better to use --direct mode.
        print("NOTE: Use --direct mode for full seeding (categories + assignments).")
        print("API mode can only create skills, not categories or assignments.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed skills data for SkillNet")
    parser.add_argument("--direct", action="store_true", help="Seed directly via DB")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--api-key", default="", help="API key for external API")
    args = parser.parse_args()

    if args.direct:
        asyncio.run(seed_direct())
    elif args.api_key:
        asyncio.run(seed_via_api(args.api_url, args.api_key))
    else:
        # Default to direct
        print("Using direct DB mode (set DATABASE_URL if needed)...")
        asyncio.run(seed_direct())


if __name__ == "__main__":
    main()
