from sqlalchemy.dialects import postgresql


class Result(list):
    def tuples(self):
        return self

    def scalars(self):
        return self

    def all(self):
        return list(self)


class RecordingSession:
    """Записывает реальные SQL-выражения, не имитируя исполнение SQL."""

    def __init__(self, rows=(), scalar=None):
        self.rows = rows
        self.scalar_result = scalar
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return Result(self.rows)

    async def scalars(self, statement):
        self.statements.append(statement)
        return Result(self.rows)

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_result

    @property
    def compiled(self):
        return self.statements[-1].compile(dialect=postgresql.dialect())

    @property
    def sql(self):
        return str(self.compiled)
