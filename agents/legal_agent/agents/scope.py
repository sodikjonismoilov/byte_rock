"""Offline routing only; model mode supplies its own validated research tasks."""
CATEGORIES = {
    'identity': ['identity', 'address', 'property'],
    'heat': ['heat', 'hot water', 'temperature'],
    'maintenance': ['mold', 'pest', 'mice', 'roach', 'leak', 'lead', 'maintenance', 'water', 'repair', 'habitability'],
    'construction': ['dob', 'construction', 'permit', 'occupancy', 'safety'],
    'eviction': ['eviction', 'warrant'],
    'litigation': ['litigation', 'lawsuit', 'housing court', 'nyscef', 'supreme court', 'webcivil'],
    'rent_regulation': ['rent regulation', 'rent stabilization', 'rent-regulat', 'regulated', 'overcharge'],
}
QUERIES = {
    'identity': 'property records building identity',
    'heat': 'heat hot water temperature',
    'maintenance': 'mold pests leaks lead repairs habitability',
    'construction': 'DOB construction permits certificate occupancy',
    'eviction': 'eviction warrant judgment executed',
    'litigation': 'housing court litigation NYSCEF WebCivil Supreme Court',
    'rent_regulation': 'rent stabilization regulation HCR',
}


def categories(task):
    text = ' '.join([task.question, *task.issue_types]).lower()
    if not task.issue_types and any(x in text for x in ['due diligence', 'due-diligence', 'before signing', 'investigate building']):
        return list(CATEGORIES)
    return [key for key, terms in CATEGORIES.items() if any(t in text for t in terms)] or ['maintenance']


def evidence_category(item):
    issue = str(item.metadata.get('issue', '')).lower()
    matches = [k for k, terms in CATEGORIES.items() if any(t in issue for t in terms)]
    if 'heat' in matches and 'maintenance' not in matches:
        matches.append('maintenance')
    return matches
