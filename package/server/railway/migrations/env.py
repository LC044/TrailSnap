"""Uses the caller's railway connection, never the application's DB_URL."""
from alembic import context
from railway.db.models.models import Base

config = context.config


def include_object(obj, name, type_, reflected, compare_to):
    # The first railway revision upgrades existing reference tables only.
    return name == 'station' if type_ == 'table' else True


def configure(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      version_table='alembic_version_railway', compare_type=True,
                      include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


configure(config.attributes['connection'])
