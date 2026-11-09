import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load variables directly from .env without printing them
load_dotenv()

def test_connection(env_var_name, connection_name):
    # Retrieve variable without printing
    url = os.getenv(env_var_name)
    if not url:
        print(f"{connection_name}: Variable {env_var_name} not found in environment.")
        return

    try:
        # Use pool_pre_ping=True to force a check
        engine = create_engine(url, pool_pre_ping=True, connect_args={"sslmode": "require"})
        with engine.connect() as conn:
            # 1. SELECT 1
            conn.execute(text("SELECT 1"))
            
            # 2. Diagnostics
            res = conn.execute(text("SELECT current_database(), current_user, version();"))
            row = res.fetchone()
            
            # 3. SSL verification
            ssl_res = conn.execute(text("SHOW ssl;"))
            ssl = ssl_res.scalar()
            
            print(f"{connection_name}: SUCCESS")
            print(f"  Database: {row[0]}")
            print(f"  User: {row[1]}")
            print(f"  Version: {row[2]}")
            print(f"  SSL Active: {ssl}")
            
    except Exception as e:
        print(f"{connection_name}: FAILED - {type(e).__name__}")

print("--- Starting Neon Connectivity Audit ---")
test_connection("POOLED_DATABASE_URL", "Neon Pooled Connection")
test_connection("DIRECT_DATABASE_URL", "Neon Direct Connection")
