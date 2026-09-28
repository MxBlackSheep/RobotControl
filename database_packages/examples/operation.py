"""Example operation for a DISPOSABLE DemoItems table, not a laboratory procedure.

Adapt both preview and run for your real operation. The host owns the transaction.
Do not commit in this script. Preview must only read data.
"""

TOOL = {
    'name': 'Delete demo item',
    'kind': 'operation',
    'confirm': 'item_id',
    'inputs': {'item_id': {'label': 'Item ID', 'type': 'integer'}},
}


def preview(context, inputs):
    with context.connection.cursor() as cursor:
        row = cursor.execute('SELECT id, label FROM dbo.DemoItems WHERE id = ?',
                             (inputs['item_id'],)).fetchone()
    if row is None:
        raise ValueError('Item no longer exists.')
    return {'summary': 'Delete this demo item.', 'details': {'ID': row[0], 'Name': row[1], 'Rows to delete': 1}}


def run(context, inputs):
    preview(context, inputs)
    with context.connection.cursor() as cursor:
        cursor.execute('DELETE FROM dbo.DemoItems WHERE id = ?', (inputs['item_id'],))
    return {'message': 'Demo item deleted.'}
