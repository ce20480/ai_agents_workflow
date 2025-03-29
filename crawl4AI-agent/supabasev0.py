from dotenv import load_dotenv
import os
import asyncio
import logging
from supabase import create_client
from ai_expert import get_embedding, Sites, LLM_MODEL
from openai import AsyncOpenAI

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(".env_agents", override=True)

# Initialize clients
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
site = Sites.FILECOIN.value

async def test_supabase_connection():
    """Test the Supabase connection"""
    try:
        result = supabase.table("site_pages").select("count", count="exact").execute()
        logger.info(f"Successfully connected to Supabase. Count: {result.count}")
    except Exception as e:
        raise ConnectionError(f"Unable to connect to Supabase: {e}")

async def query_documentation(user_query: str):
    """Query the documentation using embeddings"""
    try:
        # Get the embedding for the query
        query_embedding = await get_embedding(user_query, openai_client)

        # Query Supabase
        result = supabase.rpc(
            "match_site_pages",
            {
                "query_embedding": query_embedding,
                "match_count": 5,
                "filter": {"model": f"{LLM_MODEL}"},
                "site_filter": site
            },
        ).execute()

        if not result.data:
            return "No relevant documentation found."

        # Format results
        formatted_chunks = [
            f"# {doc['title']}\n\n{doc['content']}"
            for doc in result.data
        ]

        return "\n\n---\n\n".join(formatted_chunks)

    except Exception as e:
        logger.error(f"Error querying documentation: {e}")
        raise

async def main():
    """Main async function"""
    try:
        # Test connection
        await test_supabase_connection()

        # Example query
        user_query = "How do I use the Filecoin JSON-RPC class?"
        result = await query_documentation(user_query)
        print("\nQuery Results:")
        print(result)

    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        # Cleanup
        await openai_client.close()

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())