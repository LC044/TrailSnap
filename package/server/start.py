import os
import sys
import subprocess
import csv
import json
import argparse
from urllib.parse import urlparse
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from dotenv import load_dotenv

from app.core.paths import DATA_DIR, ensure_rg_seed

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
load_dotenv(os.path.join(DATA_DIR, '.env'))
# 播种默认离线反向编码数据（CN.csv），在启动 uvicorn 前完成
ensure_rg_seed()

def import_scenes(database_url):
    print("Importing scenes data...")
    csv_path = os.path.join(os.path.dirname(__file__), 'resources', 'scenes_5A.csv')
    
    if not os.path.exists(csv_path):
        print(f"Warning: Scenes CSV not found at {csv_path}")
        return

    try:
        engine = create_engine(database_url)
        with engine.connect() as conn:
            # Read CSV
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                count = 0
                for row in reader:
                    # Check if scene exists by name
                    check_query = text("SELECT 1 FROM scenes WHERE name = :name")
                    exists = conn.execute(check_query, {"name": row['name']}).scalar()
                    
                    if not exists:
                        # Prepare data
                        try:
                            polygon_data = json.loads(row['polygon']) if row['polygon'] else None
                        except json.JSONDecodeError:
                            polygon_data = None
                            
                        insert_query = text("""
                            INSERT INTO scenes (id, name, description, level, address, latitude, longitude, radius, polygon, is_custom)
                            VALUES (:id, :name, :description, :level, :address, :latitude, :longitude, :radius, :polygon, :is_custom)
                        """)
                        
                        conn.execute(insert_query, {
                            "id": row['id'],
                            "name": row['name'],
                            "description": row['description'],
                            "level": int(row['level']) if row['level'] else None,
                            "address": row['address'],
                            "latitude": float(row['latitude']) if row['latitude'] else None,
                            "longitude": float(row['longitude']) if row['longitude'] else None,
                            "radius": int(row['radius']) if row['radius'] else 0,
                            "polygon": json.dumps(polygon_data) if polygon_data else None,
                            "is_custom": False
                        })
                        count += 1
                
                if count > 0:
                    conn.commit()
                    print(f"Successfully imported {count} scenes.")
                else:
                    print("No new scenes to import.")
                    
    except Exception as e:
        print(f"Error importing scenes: {e}")


def is_sqlite_url(database_url):
    return make_url(database_url).get_backend_name() == "sqlite"


def initialize_database(database_url):
    """Prepare prerequisites for the configured database dialect."""
    url = make_url(database_url)
    backend = url.get_backend_name()
    if backend == "sqlite":
        database_path = url.database
        if database_path and database_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
        print(f"Using SQLite database at {database_path or ':memory:'}.")
        return
    if backend != "postgresql":
        raise ValueError(f"Unsupported database backend: {backend}")

    db_name = url.database
    postgres_url = url.set(database="postgres")
    print(f"Connecting to database server at {url.host}...")
    engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        ).scalar()
        if not result:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
            print(f"Database '{db_name}' created successfully.")
    engine.dispose()

    target_engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
    with target_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    target_engine.dispose()


def run_migrations(database_url):
    command = ["alembic"]
    if is_sqlite_url(database_url):
        command.extend(["-c", "alembic_sqlite.ini"])
    command.extend(["upgrade", "head"])
    subprocess.run(command, check=True)

def main():
    parser = argparse.ArgumentParser(description="Start the TrailSnap server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
    args = parser.parse_args()

    print("Starting application initialization...")

    # 1. 检查数据库连接是否正常
    # 2. 检查数据库是否存在，不存在则创建（创建失败报错退出）
    database_url = os.environ.get("TS_DB_URL") or os.environ.get("DB_URL")
    if not database_url:
        print("Error: DB_URL or TS_DB_URL environment variable is not set.")
        print("Please set DB_URL (e.g., postgresql://user:password@host:5432/dbname)")
        sys.exit(1)

    try:
        initialize_database(database_url)
    except Exception as e:
        print(f"Error during database initialization: {e}")
        print("Ensure the database server is running and reachable.")
        sys.exit(1)

    # 4. 使用alembic迁移数据库（alembic upgrade head）
    print("Running Alembic migrations...")
    try:
        run_migrations(database_url)
        print("Alembic migrations completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Alembic migration failed with exit code {e.returncode}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: 'alembic' command not found. Ensure it is installed and in PATH.")
        sys.exit(1)

    # 4.1 导入景区数据
    import_scenes(database_url)

    # 6. from railway import start start.create_database() railway模块的功能先不修改，保持不变
    # Note: Placed here to ensure main DB is ready first, though railway might use its own DB.
    # User requested this be present.
    try:
        from railway import start
        start.create_database()
    except Exception as e:
        print(f"Warning: Railway database initialization failed: {e}")
        # Not exiting here as user said "railway模块的功能先不修改", assuming it's secondary or independent.
        # But if it's critical, we might want to exit. Given the prompt, I'll just log it.

    # 5. Start application (implied, though not explicitly numbered in the list as a separate step to modify, 
    # but usually part of a start script)
    # The user didn't explicitly ask to start the server in the numbered list, 
    # but the context is "perfecting the startup script". 
    # The previous start.py started uvicorn. I will keep it.
    
    print(f"Starting uvicorn on port {args.port}...")
    try:
        sys.stdout.flush()
        # Using python -m uvicorn to ensure it uses the same python environment
        os.execvp("python", ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(args.port)])
    except OSError as e:
        print(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
