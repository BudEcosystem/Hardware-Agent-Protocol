"""Generate the Harness value-schema projection; Python remains full authority."""
from pathlib import Path
import argparse
import hashlib
import json


def project(node, defs, seen=()):
    if '$ref' in node:
        name = node['$ref'].removeprefix('#/$defs/')
        return {'type': 'json'} if name in seen else project(defs[name], defs, (*seen, name))
    variants = node.get('oneOf', node.get('anyOf'))
    if variants:
        projected = [project(branch, defs, seen) for branch in variants]
        # anyOf may overlap; only turn its disjoint primitive roots into oneOf.
        if 'anyOf' in node and len({branch.get('type') for branch in projected}) != len(projected):
            return {'type': 'json'}
        return {'oneOf': projected} if len(projected) > 1 else projected[0]
    kind = node.get('type')
    if isinstance(kind, list):
        return {'oneOf': [project({**node, 'type': item}, defs, seen) for item in kind]}
    if kind is None and ('const' in node or 'enum' in node):
        value = node.get('const', node.get('enum', [None])[0])
        kind = 'null' if value is None else 'boolean' if isinstance(value, bool) else 'string' if isinstance(value, str) else 'integer' if isinstance(value, int) else 'number'
    if kind is None:
        return {'type': 'json'}
    output = {'type': kind}
    for key in ('const', 'enum', 'description'):
        if key in node: output[key] = node[key]
    if kind == 'object':
        output['additionalProperties'] = node.get('additionalProperties', True) is not False
        if 'properties' in node:
            output['properties'] = {key: {**project(value, defs, seen), **({'required': True} if key in node.get('required', []) else {})} for key, value in node['properties'].items()}
    elif kind == 'array' and 'items' in node:
        output['items'] = project(node['items'], defs, seen)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('worktree', type=Path)
    args = parser.parse_args()
    schema_path = Path(__file__).resolve().parents[2] / 'schemas/local-api.schema.json'
    raw = schema_path.read_bytes()
    source = json.loads(raw)
    names = source['x-hms-method-results']
    results = {name: project(source['$defs'][name], source['$defs']) for name in sorted(set(names.values()))}
    text = '/** Generated projection of HMS local-api.schema.json; full bounds and semantics remain in the checked Python client. */\n'
    text += '// Source SHA-256: ' + hashlib.sha256(raw).hexdigest() + '\n'
    text += "import type { HardwareMethod } from '@budmh/experimental-hardware'\nimport type { ValueSchemaSpec } from '@budmh/tools'\n"
    text += 'const results = JSON.parse(String.raw`' + json.dumps(results, indent=2).replace('`', '\\u0060').replace('${', '\\u0024{') + '`) as Record<string, ValueSchemaSpec>\n'
    text += 'const methods = JSON.parse(String.raw`' + json.dumps(names, indent=2) + '`) as Record<HardwareMethod, string>\n'
    text += '''const attribution: ValueSchemaSpec = { type: 'object', additionalProperties: false, properties: {
  sessionId: { oneOf: [{ type: 'string' }, { type: 'null' }], required: true }, callId: { type: 'string', required: true },
} }
/** Closed carrier with method-specific identity, state, and evidence fields. */
export function hardwareOutputSchema(method: HardwareMethod): ValueSchemaSpec {
  const result = results[methods[method]]
  if (result === undefined) throw new Error('hardware output schema missing')
  return { oneOf: [
    { type: 'object', additionalProperties: false, properties: {
      ok: { type: 'boolean', const: true, required: true }, result: { ...result, required: true }, attribution: { ...attribution, required: true },
    } },
    { type: 'object', additionalProperties: false, properties: {
      ok: { type: 'boolean', const: false, required: true }, outcome: { type: 'string', const: 'unconfirmed', required: true },
      error: { type: 'object', additionalProperties: false, required: true, properties: { code: { type: 'string', required: true } } }, attribution: { ...attribution, required: true },
    } },
  ] }
}
'''
    target = args.worktree / 'packages/experimental/tool-hardware/src/output-schema.ts'
    target.write_text(text)
    print(f'Generated {target} from {hashlib.sha256(raw).hexdigest()}')


if __name__ == '__main__':
    main()
