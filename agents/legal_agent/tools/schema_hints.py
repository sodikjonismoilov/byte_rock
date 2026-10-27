"""Prompt hints derived from a JSON schema: a minimal valid example and required-field notes. Never contains response values."""
SHOWN_OPTIONAL = {'evidence_ids', 'legal_conclusions', 'recommended_tool', 'claim_scope'}


def _node(node, defs):
    while True:
        if '$ref' in node:node = defs[node['$ref'].split('/')[-1]]
        elif 'allOf' in node:node = node['allOf'][0]
        elif 'anyOf' in node:node = next((n for n in node['anyOf'] if n.get('type') != 'null'), node['anyOf'][0])
        else:return node


def example_object(schema, known=None):
    """One object with every required field (and a few key optional ones) using obvious placeholders; enum fields show an allowed value."""
    defs, known = schema.get('$defs', {}), known or {}
    def build(node, name):
        node = _node(node, defs)
        if 'const' in node:return node['const']
        if 'enum' in node:return node['enum'][0]
        kind = node.get('type')
        if kind == 'object' or 'properties' in node:
            required = set(node.get('required', []))
            return {k: build(v, k) for k, v in node.get('properties', {}).items() if k in required or k in SHOWN_OPTIONAL}
        if kind == 'array':return [] if node.get('maxItems') == 0 else [build(node['items'], name)]
        if kind in ('integer', 'number'):return node.get('minimum', 0)
        if kind == 'boolean':return False
        return known.get(name, f'<{name}>'.ljust(node.get('minLength', 0), '_'))
    return build(schema, '')


def required_fields_note(schema, details):
    """Name the required fields and types of each failing object, from the schema only."""
    defs, notes = schema.get('$defs', {}), []
    for item in details:
        path = item['path'][:-1] if item['type'] == 'missing' else item['path']
        node = _node(schema, defs)
        for part in path:
            if part.isdigit() and 'items' in node:node = _node(node['items'], defs)
            elif part in node.get('properties', {}):node = _node(node['properties'][part], defs)
            if node.get('type') == 'array':node = _node(node['items'], defs)
        label = '.'.join(p for p in path if not p.isdigit()) or 'top-level object'
        fields = ', '.join(f"{k} ({_node(node['properties'][k], defs).get('type', 'enum')})" for k in node.get('required', []) if k in node.get('properties', {}))
        note = f'{label} requires: {fields}' if fields else ''
        if note and note not in notes:notes.append(note)
    return '; '.join(notes[:4])
