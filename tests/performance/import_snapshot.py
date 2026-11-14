"""Read-only correctness snapshot, executed inside the isolated server container."""
import json
import os

import psycopg2

with psycopg2.connect(os.environ["DB_URL"]) as conn, conn.cursor() as cur:
    cur.execute("SELECT type,status,count(*) FROM tasks GROUP BY type,status")
    tasks = [dict(type=t, status=s, count=n) for t, s, n in cur.fetchall()]
    cur.execute("SELECT file_type,processed_tasks,width,height FROM photos WHERE is_deleted=false")
    photos = [dict(file_type=t, processed=p or {}, width=w, height=h) for t, p, w, h in cur.fetchall()]
    print(json.dumps(dict(tasks=tasks, photos=photos)))
