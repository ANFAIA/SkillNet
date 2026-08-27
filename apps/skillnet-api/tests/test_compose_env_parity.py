"""Los dos composes tienen que pasar las mismas variables a la API.

`docker-compose.dokploy.yml` repite el bloque `environment` de `api`, y no por descuido:
Dokploy parsea y reescribe el fichero antes de ejecutarlo, y en ese viaje pierde las
etiquetas YAML — `extends` no sobrevive, asi que no hay forma de compartir el bloque.

El coste de esa copia es la deriva, y la deriva aqui es el fallo mas repetido en la
historia de este repositorio: una variable que se anade en un sitio, no en el otro, y una
opcion que el operador rellena y no hace nada. Sin mensaje de error, porque `${VAR:-}`
resuelve a vacio igual de bien que a un valor.

Este test convierte eso en un build rojo. Si anades una clave, anadela en los dos.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
BASE = REPO / "docker-compose.yml"
DOKPLOY = REPO / "docker-compose.dokploy.yml"

#: Claves que existen solo en el fichero de Dokploy, con su motivo al lado. Vacio a
#: proposito: las dos listas son identicas hoy, y cada excepcion que se anada aqui es una
#: variable que solo se ejercita en un despliegue. Si tiene que haber una, que se justifique.
DOKPLOY_ONLY: set[str] = set()


def _env_keys(path: Path, service: str, stop_at: str) -> set[str]:
    """Claves de `environment` de un servicio, leidas del texto y no de yaml.safe_load.

    A proposito: `yaml.safe_load` se atraganta con la etiqueta `!override` que usan las
    overlays de exposicion, y este test tiene que poder leer cualquiera de los ficheros
    del repositorio sin depender de que ninguno la lleve o no.
    """
    text = path.read_text(encoding="utf-8")
    block = re.search(rf"\n  {re.escape(service)}:\n(.*?)\n  {stop_at}", text, re.S)
    assert block, f"no encontre el servicio {service} en {path.name}"
    env = re.search(r"    environment:\n(.*?)\n    [a-z_]+:", block.group(1), re.S)
    assert env, f"{service} en {path.name} no tiene bloque environment"
    return set(re.findall(r"^      ([A-Z_][A-Z0-9_]*):", env.group(1), re.M))


@pytest.fixture(scope="module")
def base_keys() -> set[str]:
    return _env_keys(BASE, "api", "# ── Keyless")


@pytest.fixture(scope="module")
def dokploy_keys() -> set[str]:
    return _env_keys(DOKPLOY, "skillnet-api", "# The front door")


def test_both_files_were_found():
    """Si alguien renombra o mueve un compose, este test lo dice antes que el despliegue."""
    assert BASE.is_file(), BASE
    assert DOKPLOY.is_file(), DOKPLOY


def test_no_key_is_missing_from_the_dokploy_file(base_keys, dokploy_keys):
    """El fallo caro: la opcion existe en local y en el PaaS no llega al contenedor."""
    missing = base_keys - dokploy_keys
    assert not missing, (
        "estas variables llegan a la API en docker-compose.yml pero NO en "
        f"docker-compose.dokploy.yml: {sorted(missing)}. En el PaaS se rellenarian sin "
        "efecto ninguno y sin ningun aviso."
    )


def test_the_dokploy_file_has_no_stray_keys(base_keys, dokploy_keys):
    """Al reves tambien importa: una clave que solo existe alli es una que nadie prueba."""
    extra = dokploy_keys - base_keys - DOKPLOY_ONLY
    assert not extra, (
        f"variables que solo existen en docker-compose.dokploy.yml: {sorted(extra)}. "
        "Si son deliberadas, anadelas a DOKPLOY_ONLY en este test con el motivo; si no, "
        "faltan en docker-compose.yml."
    )


def test_the_dokploy_file_publishes_no_ports():
    """Un puerto publicado aqui choca con Traefik y atraviesa el cortafuegos del host."""
    text = DOKPLOY.read_text(encoding="utf-8")
    offenders = [
        line for line in text.splitlines()
        if re.match(r"\s+ports:", line)
    ]
    assert not offenders, (
        "docker-compose.dokploy.yml no debe publicar puertos: Traefik llega por "
        f"dokploy-network. Encontrado: {offenders}"
    )


def test_the_dokploy_file_survives_a_yaml_round_trip():
    """Dokploy reescribe el YAML y pierde las etiquetas, asi que aqui no puede haber.

    Es el fallo que ya costo un despliegue: `depends_on: !override` volvio como un
    `depends_on` normal, se fusiono con el heredado, y murio en
    `depends on undefined service "db"`.
    """
    # Sin comentarios: la cabecera del fichero NOMBRA estas etiquetas para explicar por
    # que no se pueden usar, y eso no es usarlas.
    code = "\n".join(
        line for line in DOKPLOY.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    for tag in ("!override", "!reset", "extends:"):
        assert tag not in code, (
            f"{tag} no sobrevive al round-trip de YAML que hace Dokploy. "
            "Usa claves planas en este fichero."
        )
