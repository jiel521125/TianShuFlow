import sqlite3, os, sys
db_path = os.path.join(os.path.dirname(__file__), 'data', 'tiansu.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = sorted([row[0] for row in cursor.fetchall()])
    wf_tables = [t for t in tables if 'workflow' in t.lower()]
    print(f"All tables ({len(tables)}):")
    for t in tables:
        print(f"  - {t}")
    print(f"\nWorkflow tables ({len(wf_tables)}):")
    for t in wf_tables:
        print(f"  - {t}")
    conn.close()
else:
    print(f"Database not found at: {db_path}")