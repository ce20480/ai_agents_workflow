# constants/api_keys.py
import os
from dotenv import load_dotenv
import logging

def load_environment(env_file=".env", override=False):
    """Load environment variables with optional override and debugging"""
    if override:
        # Clear existing env vars we care about
        for var in ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPEN_AI_API_KEY"]:
            if var in os.environ:
                logging.debug(f"Removing existing {var} from environment")
                del os.environ[var]
    
    # Load new variables
    load_dotenv(env_file, override=override)
    
    # Debug logging
    for var in ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPEN_AI_API_KEY"]:
        value = os.getenv(var)
        logging.debug(f"{var}: {'SET' if value else 'NOT SET'}")

# Load environment variables from a .env file
load_environment()

# Fetch specific API keys or environment variables
OPEN_AI_API_KEY = os.getenv("OPEN_AI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
# DB_URL = os.getenv("DB_URL")

# Optionally, raise an error if a required variable is missing
# REQUIRED_VARS = ["OPEN_AI_API_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_URL"]
# for var in REQUIRED_VARS:
#     if not os.getenv(var):
#         raise EnvironmentError(f"Missing required environment variable: {var}")
