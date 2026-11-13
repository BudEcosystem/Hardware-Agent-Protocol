# BHMS examples

Every file here is one JSON object with exactly three members:

```json
{
  "$comment": "what the example shows, or why it is invalid (citing the requirement)",
  "against": "#/$defs/<Definition>",
  "message": { "...": "the JSON value being tested" }
}
```

- `against` names the definition in [`../schema/bhms.schema.json`](../schema/bhms.schema.json)
  that `message` is checked against. Requests use `<Base>Request`, results
  `<Base>Response` (a full JSON-RPC envelope), notifications `<Base>Notification`,
  errors `JSONRPCErrorResponse`; other files target a domain definition directly
  (`Operation`, `GatewayPolicy`, agent-tool inputs).
- **Valid examples** are every file whose name does not start with `invalid-`.
  Each MUST validate against `against` and MUST round-trip through the pydantic
  model (`bhms.protocol.types.parse` then `dump`) to identical RFC 8785 canonical
  JSON.
- **Invalid examples** are named `invalid-<what>.json`. Each MUST fail validation
  against `against` (and the pydantic model MUST reject it). `$comment` says why,
  naming the requirement ID where one applies. An invalid example is invalid for
  exactly the stated reason: everything else in it is taken from a valid example.

File names:

| Pattern | Contents |
|---|---|
| `<method>.request.json`, `<method>.response.json` | One per method, `/` replaced by `.` (`actions.invoke.request.json`) |
| `notifications.<name>.json` | One per notification |
| `error.<code>.json` | One per BHMS error code (`error.out-of-range.json`), plus plain JSON-RPC errors |
| `agent.<tool>.input.json`, `agent.*.json` | Agent-surface inputs and results |
| `policy.*.json`, `operation.*.json` | Other definitions |
| `invalid-*.json` | Labelled invalid examples |

Digests inside examples are real: description digests are the sha256 over the
JCS form of the description without its `digest` member, and program digests are
over the program object. `sdk/python/tests/test_schema_examples.py` enforces all
of the above (BHMS-CNF-006).
