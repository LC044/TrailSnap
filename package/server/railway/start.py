import os
import sys

from sqlalchemy import text, make_url, create_engine

def create_database():
    """
    构建数据库，包括创建表、初始化数据
    """
    # 创建所有表
    print("Starting application initialization...")

    # 1. Check environment variable DATABASE_URL
    database_url = os.environ.get("RAILWAY_DB_URL")
    if not database_url:
        print("Error: RAILWAY_DB_URL environment variable is not set.")
        print("Please set RAILWAY_DB_URL (e.g., postgresql://user:password@host:5432/dbname)")
        sys.exit(1)

    is_db_exists = False
    # 2. Check connection and create DB if needed
    try:
        url = make_url(database_url)
        db_name = url.database

        if url.get_backend_name() == 'sqlite':
            if db_name and db_name != ':memory:':
                os.makedirs(os.path.dirname(os.path.abspath(db_name)), exist_ok=True)
                is_db_exists = os.path.exists(db_name)
            from railway.db.dependencies import init_db
            init_db()
            print("Railway SQLite tables are ready")
            if not is_db_exists:
                from railway import build_database
                with build_database.SessionLocal() as db:
                    build_database.build_database(db)
            return

        if url.get_backend_name() != 'postgresql':
            raise ValueError(f"Unsupported Railway database backend: {url.get_backend_name()}")

        # We need to connect to the 'postgres' database to check/create the target database
        # Create a copy of the URL but with 'postgres' as the database
        postgres_url = url.set(database='postgres')

        print(f"Connecting to database server at {url.host}...")

        # Connect to default 'postgres' database
        engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")

        with engine.connect() as conn:
            print("Successfully connected to database server.")

            # Check if target database exists
            # Use text() for raw SQL
            query = text("SELECT 1 FROM pg_database WHERE datname = :name")
            result = conn.execute(query, {"name": db_name}).scalar()

            if not result:
                print(f"Database '{db_name}' does not exist. Creating...")
                # Cannot use parameters for database name in CREATE DATABASE
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"Database '{db_name}' created successfully.")
            else:
                is_db_exists = True
                print(f"Database '{db_name}' already exists.")
        
        engine.dispose()
        
        # 3. Connect to the target database to enable vector extension
        print(f"Connecting to target database '{db_name}'...")
        target_engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
        with target_engine.connect() as conn:
             print("Enabling 'vector' extension if not exists...")
             conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
             print("'vector' extension enabled.")
        target_engine.dispose()
    except Exception as e:
        print(f"Error during database initialization: {e}")
        print("Ensure the database server is running and reachable.")
        sys.exit(1)
    print("数据库表已创建")
    if not is_db_exists:
        from railway import build_database
        build_database.rebuild_database()
