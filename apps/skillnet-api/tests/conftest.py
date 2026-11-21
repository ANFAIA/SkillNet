"""Minimal pytest setup. Unit tests here need no DB or network."""

import os

# litellm downloads its model registry from GitHub on import unless told otherwise, so
# capability checks such as ``supports_reasoning`` would follow whatever that remote file
# says today. Pin the tests to the registry bundled with the locked litellm version.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
