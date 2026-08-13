import uuid
from types import SimpleNamespace

import pytest

from src.models import MediaArtifactStatus
from src.services.activity_ports import PortDeclined
from src.services.media.activity_assets import ActivityAssetResolver, make_activity_asset_ref


def artifact(**overrides):
    values = {
        "id": uuid.uuid4(),
        "org_id": uuid.uuid4(),
        "course_id": uuid.uuid4(),
        "node_id": uuid.uuid4(),
        "status": MediaArtifactStatus.DONE,
        "asset_path": "/private/media/never-public.png",
        "spec_json": {
            "mime_type": "image/png",
            "alt": "Plano accesible",
            "long_description": "Plano completo con zonas descritas.",
            "width": 1200,
            "height": 800,
            "grounded_geometry": {"verified": True, "region_ids": ["region-1"]},
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class Repository:
    def __init__(self, row):
        self.row = row

    async def get_scoped(self, artifact_id, org_id):
        if self.row.id == artifact_id and self.row.org_id == org_id:
            return self.row
        return None


@pytest.mark.asyncio
async def test_asset_resolution_is_org_course_node_and_activity_definition_scoped():
    row = artifact()
    ref = make_activity_asset_ref(row)
    activity = SimpleNamespace(
        org_id=row.org_id,
        course_id=row.course_id,
        node_id=row.node_id,
        public_definition={"assetRef": ref},
    )
    resolver = ActivityAssetResolver(Repository(row))

    resolved = await resolver.resolve(activity, ref)
    assert not isinstance(resolved, PortDeclined)
    payload = resolved.as_payload()
    assert payload["mime_type"] == "image/png"
    assert payload["alt"] == "Plano accesible"
    assert payload["width"] == 1200
    assert row.asset_path not in str(payload)
    assert "content_hash" not in payload

    copied_activity = SimpleNamespace(
        org_id=row.org_id,
        course_id=uuid.uuid4(),
        node_id=row.node_id,
        public_definition={"assetRef": ref},
    )
    declined = await resolver.resolve(copied_activity, ref)
    assert isinstance(declined, PortDeclined)
    assert declined.reason == "asset_scope_mismatch"

    undeclared = SimpleNamespace(
        org_id=row.org_id,
        course_id=row.course_id,
        node_id=row.node_id,
        public_definition={},
    )
    declined = await resolver.resolve(undeclared, ref)
    assert isinstance(declined, PortDeclined)
    assert declined.reason == "asset_not_declared_by_activity"


@pytest.mark.asyncio
async def test_asset_resolution_declines_missing_accessibility_metadata():
    row = artifact(spec_json={"mime_type": "image/png"})
    ref = make_activity_asset_ref(row)
    activity = SimpleNamespace(
        org_id=row.org_id,
        course_id=row.course_id,
        node_id=row.node_id,
        public_definition={"assetRef": ref},
    )
    result = await ActivityAssetResolver(Repository(row)).resolve(activity, ref)
    assert isinstance(result, PortDeclined)
    assert result.reason == "asset_missing_alt"


def test_opaque_ref_contains_no_path_or_storage_name():
    row = artifact()
    ref = make_activity_asset_ref(row)
    assert ref.startswith("skasset_")
    assert row.asset_path not in ref
    assert ".png" not in ref
