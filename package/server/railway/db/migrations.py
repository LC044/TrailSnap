"""Independent Alembic history for the separate railway database."""
from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(dialect):
    root = Path(__file__).resolve().parents[2]
    config = Config()
    config.set_main_option('script_location', str(root/'railway'/'migrations'))
    directory = 'alembic_sqlite' if dialect == 'sqlite' else 'alembic'
    config.set_main_option('version_locations', str(root/directory/'railway_versions'))
    return config


def upgrade_railway_schema(engine):
    if engine.dialect.name not in {'sqlite','postgresql'}:
        raise ValueError('Unsupported railway database dialect')
    config = migration_config(engine.dialect.name)
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
