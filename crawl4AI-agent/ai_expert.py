from __future__ import annotations as _annotations

import asyncio
import os
from dataclasses import dataclass
from typing import List
import socket
import logging
from dotenv import load_dotenv

import httpx
import logfire
from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.openai import OpenAIModel
from supabase import Client, create_client

# Load environment with override
load_dotenv(".env_agents", override=True)

# from constants import LLM_MODEL, OPEN_AI_API_KEY, SUPABASE_SERVICE_KEY, SUPABASE_URL
from crawl_docs import Sites

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

model = OpenAIModel(LLM_MODEL)
SITE = Sites.FILECOIN.value

logfire.configure(send_to_logfire="if-token-present")



@dataclass
class AIDeps:
    """
    Dependencies for the AI expert agent.
    """
    openai_client: AsyncOpenAI
    supabase: Client
    http_client: httpx.AsyncClient = None  # Add HTTP client to dependencies

    def __post_init__(self):
        # Initialize HTTP client with timeouts
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )


system_prompt = f"""
You are an AI expert specifically trained to assist with the {SITE} developer documentation. 
You have access to all the relevant documentation, including examples, reference pages, 
and other resources to help answer technical questions about {SITE}'s APIs and development 
guidelines.

Your workflow always starts with RAG (Retrieval-Augmented Generation):
1. Whenever a user question comes in, first retrieve the relevant documentation chunks from 
   the knowledge base (Supabase) using your `retrieve_relevant_documentation` tool.
2. If necessary, check the list of available documentation pages using your `list_documentation_pages` tool, 
   and retrieve the content of specific pages with `get_page_content`.
3. Use the retrieved information to formulate your answer or the next step.

Only answer queries about {SITE} developer documentation, and if you cannot find the answer 
in the provided resources, honestly state that the relevant documentation was not found. 

Always ensure the user is aware if you did not find an answer in your knowledge base or 
if the URL or topic they mention is not recognized in the docs. 
Never respond with content outside your scope as an {SITE} documentation assistant.
"""

ai_expert = Agent(model, system_prompt=system_prompt, deps_type=AIDeps, retries=2)


async def get_embedding(text: str, openai_client: AsyncOpenAI) -> List[float]:
    """Get embedding vector from OpenAI."""
    try:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return response.data[0].embedding
    except httpx.ConnectError as e:
        logging.error(f"Connection error while getting embedding: {e}")
        raise ConnectionError(f"Unable to connect to OpenAI API: {e}")
    except Exception as e:
        logging.error(f"Error getting embedding: {e}")
        return [0] * 1536  # Return zero vector on error


@ai_expert.tool
async def retrieve_relevant_documentation(
    ctx: RunContext[AIDeps], 
    user_query: str,
    site: str = SITE  # Add default site parameter
) -> str:
    """
    Retrieve relevant documentation chunks based on the query with RAG.

    Args:
        ctx: The context including the Supabase client and OpenAI client
        user_query: The user's question or query
        site: The documentation site to search (defaults to SITE constant)

    Returns:
        A formatted string containing the top 5 most relevant documentation chunks
    """
    try:
        # Test connection to Supabase
        try:
            await ctx.deps.supabase.table("site_pages").select("count", count="exact").execute()
        except Exception as e:
            raise ConnectionError(f"Unable to connect to Supabase: {e}")

        # Get the embedding for the query
        query_embedding = await get_embedding(user_query, ctx.deps.openai_client)

        # Query Supabase for relevant documents using the new site_filter parameter
        result = ctx.deps.supabase.rpc(
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

        # Format the results
        formatted_chunks = []
        for doc in result.data:
            chunk_text = f"""
# {doc['title']}

{doc['content']}
"""
            formatted_chunks.append(chunk_text)

        # Join all chunks with a separator
        return "\n\n---\n\n".join(formatted_chunks)

    except ConnectionError as e:
        logging.error(f"Connection error: {e}")
        return f"Connection error occurred: {str(e)}. Please check your network connection and credentials."
    except Exception as e:
        logging.error(f"Error retrieving documentation: {e}")
        return f"Error retrieving documentation: {str(e)}"


@ai_expert.tool
async def list_documentation_pages(
    ctx: RunContext[AIDeps],
    site: str = SITE  # Add default site parameter
) -> List[str]:
    """
    Retrieve a list of all available documentation pages for a specific site.

    Args:
        ctx: The context including the Supabase client
        site: The documentation site to list pages for (defaults to SITE constant)

    Returns:
        List[str]: List of unique URLs for all documentation pages
    """
    try:
        # Query Supabase for unique URLs using the site column
        result = (
            ctx.deps.supabase.from_("site_pages")
            .select("url")
            .eq("site", site)
            .eq("metadata->>model", f"{LLM_MODEL}")
            .execute()
        )

        if not result.data:
            return []

        # Extract unique URLs
        urls = sorted(set(doc["url"] for doc in result.data))
        return urls

    except Exception as e:
        print(f"Error retrieving documentation pages: {e}")
        return []


@ai_expert.tool
async def get_page_content(
    ctx: RunContext[AIDeps], 
    url: str,
    site: str = SITE  # Add default site parameter
) -> str:
    """
    Retrieve the full content of a specific documentation page by combining all its chunks.

    Args:
        ctx: The context including the Supabase client
        url: The URL of the page to retrieve
        site: The documentation site the page belongs to (defaults to SITE constant)

    Returns:
        str: The complete page content with all chunks combined in order
    """
    try:
        # Query Supabase for all chunks of this URL, using the site column
        result = (
            ctx.deps.supabase.from_("site_pages")
            .select("title, content, chunk_number")
            .eq("url", url)
            .eq("site", site)
            .eq("metadata->>model", f"{LLM_MODEL}")
            .order("chunk_number")
            .execute()
        )

        if not result.data:
            return f"No content found for URL: {url}"

        # Format the page with its title and all chunks
        page_title = result.data[0]["title"].split(" - ")[0]  # Get the main title
        formatted_content = [f"# {page_title}\n"]

        # Add each chunk's content
        for chunk in result.data:
            formatted_content.append(chunk["content"])

        # Join everything together
        return "\n\n".join(formatted_content)

    except Exception as e:
        print(f"Error retrieving page content: {e}")
        return f"Error retrieving page content: {str(e)}"
