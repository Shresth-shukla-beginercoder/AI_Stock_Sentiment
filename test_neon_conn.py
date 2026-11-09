import getpass
from sqlalchemy import create_engine, text

def test_connection(url, name):
    print(f"\n--- Testing {name} ---")
    try:
        # pool_pre_ping=True ensures we test the actual connection
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            # 1. SELECT 1
            result = conn.execute(text("SELECT 1"))
            print("Successfully executed SELECT 1")

            # 2. SELECT current_database(), current_user, version()
            result = conn.execute(text("SELECT current_database(), current_user, version();"))
            row = result.fetchone()
            print(f"Database: {row[0]}")
            print(f"User: {row[1]}")
            print(f"Version: {row[2]}")

            # 3. SSL Check (Neon requires SSL)
            result = conn.execute(text("SHOW ssl;"))
            ssl_status = result.scalar()
            print(f"SSL active: {ssl_status}")

    except Exception as e:
        print(f"Error testing {name}: {e}")

print("Please enter Pooled Neon connection string (will be hidden):")
pooled_url = getpass.getpass()
test_connection(pooled_url, "Pooled Neon")

print("\nPlease enter Direct Neon connection string (will be hidden):")
direct_url = getpass.getpass()
test_connection(direct_url, "Direct Neon")
