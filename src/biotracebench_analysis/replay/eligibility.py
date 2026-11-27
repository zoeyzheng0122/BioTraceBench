"""Project source masks and optional answers through adjudicated identities."""


def exclusions(inventory, marking, case, dispositions=()):
    rows = {r['id']: r for r in inventory['rows']}
    selected = {(r['table'], r['row_index']): r for r in dispositions if r['case'] == case}
    pairs = {r['prediction_row']: r['reference_row'] for r in marking['records']
             if r.get('prediction_row') and r.get('reference_row')}
    row_marks = {r['prediction_row']: r for r in marking['records'] if r.get('prediction_row')}
    cell_marks = {m['prediction_cell']: m for m in marking['cells'] if m.get('prediction_cell')}

    def policy(row):
        reference = rows.get(pairs.get(row['id'])) if row['side'] == 'prediction' else row
        return selected.get((reference['table'], reference['row_index']), {}) if reference else {}

    excluded_cells = set()
    for cell in inventory['cells']:
        row = rows[cell['row']]
        item = policy(row)
        fields = item.get('field_exclusions', [])
        masked = cell['field'] in fields or '*' in fields
        if masked and row['side'] == 'prediction' and item.get('answer_policy') == 'optional_neutral':
            # Wrong values, wrong bindings and unmatched duplicates stay penalized.
            masked = (row_marks[row['id']]['verdict'] == 'matched'
                      and cell_marks[cell['id']]['verdict'] in ('correct', 'not_scored'))
        if masked:
            excluded_cells.add(cell['id'])

    excluded_rows = set()
    for row in inventory['rows']:
        item = policy(row)
        masked = item.get('main_record_scoring') == 'excluded'
        if masked and row['side'] == 'prediction' and item.get('answer_policy') == 'optional_neutral':
            masked = (row_marks[row['id']]['verdict'] == 'matched'
                      and all(c['id'] in excluded_cells for c in inventory['cells']
                              if c['row'] == row['id'] and c['role'] == 'scientific' and c['nonempty']))
        if masked:
            excluded_rows.add(row['id'])
    return rows, selected, excluded_cells, excluded_rows
