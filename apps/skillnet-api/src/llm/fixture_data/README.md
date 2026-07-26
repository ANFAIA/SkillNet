# LLM fixtures

Recorded `(prompt, response)` pairs served by `src/llm/fixtures.py` whenever the
resolved model id starts with `fixture/`. **No network call is ever made.**

These files live inside the package on purpose: `docker/api.Dockerfile` copies only
`.venv`, `src`, `alembic`, `alembic.ini` and `pyproject.toml`, so fixtures under
`tests/` would be missing from the image and the `fixtures` compose profile could
not work. `LLM_FIXTURE_DIR` defaults to this directory.

## How lookup works

```
key = sha256(f"{system_prompt}\x00{user_prompt}").hexdigest()[:16]
```

`index.json` maps that 16-hex key to an entry:

```json
{
  "3f2c1a90bb4d7e02": {
    "file": "genera_ui/openui_explanation.txt",
    "prompt_preview": "You are a UI author... || Node: return policy...",
    "use_case": "genera_ui"
  }
}
```

The file content is returned **verbatim** as the completion text — a `.json`
fixture holds exactly the JSON the model would emit, so `json_mode=True` needs no
post-processing. A miss raises `LLMError` naming the key and a prompt preview, never
an opaque `KeyError`.

## Adding a fixture

Preferred, with a real key available:

```
LLM_FIXTURE_MODE=record  # the real LLMService writes every pair into recorded/
```

From a test, for a prompt the test itself builds:

```python
from src.llm.fixtures import write_fixture

write_fixture(
    system_prompt=SYSTEM,
    user_prompt=user,
    response=raw,
    relative_path="genera_ui/openui_explanation.txt",
    use_case="genera_ui",
)
```

## Expected layout (§12.1 of `docs/design/v2-dynamic-courses.md`)

Owned by the batch that owns the prompt — B0 ships the mechanism and this layout,
not other batches' dialects.

| Path | Batch |
|---|---|
| `schema_design/returns_policy.json` | B2 |
| `decide_formato/{explanation,exercise,chart}.json` | B5 |
| `genera_ui/openui_explanation.txt` | B1/B5 |
| `genera_ui/openui_exercise.txt` | B1/B5 |
| `genera_ui/openui_table_nested.txt` | B1 |
| `genera_ui/malformed_unclosed_array.txt` | B1 |
| `genera_ui/malformed_unescaped_quote.txt` | B1 |
| `genera_ui/malformed_literal_newline.txt` | B1 |
| `genera_ui/invalid_unknown_component.txt` | B1 |
| `genera_ui/repaired_after_retry.txt` | B1 |
| `probe_generate/plazo_devolucion.json` | B4 |
| `explain/{mercurio_quimica,mercurio_planeta}.json` | B7 |

The three `malformed_*` files map one-to-one to the three escaping rules of the
frozen grammar in §5.4 — they are the mistakes an 8B model makes on day one, not
invented malformations.
