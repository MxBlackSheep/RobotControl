"""SQL Server 2008 R2 persistence for Champions propagation plans.

Callers own the connection transaction. No legacy mutating procedure is invoked.

RobotControl package: only ``query`` is vendored (plate_export imports nothing else).
The plan persistence functions and the ``.database`` import are left out; the report
receives RobotControl's read-only connection instead.
"""


def query(cursor, sql, params=()):
    cursor.execute(sql, tuple(params))
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]
