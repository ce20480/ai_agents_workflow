import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from openai import AsyncOpenAI
from supabase import Client, create_client

from constants import (
    LLM_MODEL,
    OPEN_AI_API_KEY,
    SITEMAP,
    SUPABASE_SERVICE_KEY,
    SUPABASE_URL,
    SITEMAP_URLS,
)


class Sites(Enum):
    PYDANTIC = "pydanticai"
    ETSY = "etsy"
    FILECOIN = "filecoin"


@dataclass
class ProcessedChunk:
    site: str
    url: str
    chunk_number: int
    title: str
    summary: str
    content: str
    metadata: Dict[str, Any]
    embedding: List[float]


def chunk_text(text: str, chunk_size: int = 5000) -> List[str]:
    """Split text into chunks, respecting code blocks and paragraphs."""
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        # Calculate end position
        end = start + chunk_size

        # If we're at the end of the text, just take what's left
        if end >= text_length:
            chunks.append(text[start:].strip())
            break

        # Try to find a code block boundary first (```)
        chunk = text[start:end]
        code_block = chunk.rfind("```")
        if code_block != -1 and code_block > chunk_size * 0.3:
            end = start + code_block

        # If no code block, try to break at a paragraph
        elif "\n\n" in chunk:
            # Find the last paragraph break
            last_break = chunk.rfind("\n\n")
            if (
                last_break > chunk_size * 0.3
            ):  # Only break if we're past 30% of chunk_size
                end = start + last_break

        # If no paragraph break, try to break at a sentence
        elif ". " in chunk:
            # Find the last sentence break
            last_period = chunk.rfind(". ")
            if (
                last_period > chunk_size * 0.3
            ):  # Only break if we're past 30% of chunk_size
                end = start + last_period + 1

        # Extract chunk and clean it up
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start position for next chunk
        start = max(start + 1, end)

    return chunks


async def get_title_and_summary(chunk: str, url: str) -> Dict[str, str]:
    """Extract title and summary using GPT-4."""
    system_prompt = """You are an AI that extracts titles and summaries from documentation chunks.
    Return a JSON object with 'title' and 'summary' keys.
    For the title: If this seems like the start of a document, extract its title. If it's a middle chunk, derive a descriptive title.
    For the summary: Create a concise summary of the main points in this chunk.
    Keep both title and summary concise but informative."""

    try:
        response = await openai_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"URL: {url}\n\nContent:\n{chunk[:1000]}...",
                },  # Send first 1000 chars for context
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error getting title and summary: {e}")
        return {
            "title": "Error processing title",
            "summary": "Error processing summary",
        }


async def get_embedding(text: str) -> List[float]:
    """Get embedding vector from OpenAI."""
    try:
        response = await openai_client.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return [0] * 1536  # Return zero vector on error


async def process_chunk(chunk: str, chunk_number: int, url: str, site: str) -> ProcessedChunk:
    """Process a single chunk of text."""
    # Get title and summary
    extracted = await get_title_and_summary(chunk, url)

    # Get embedding
    embedding = await get_embedding(chunk)

    # Create metadata
    metadata = {
        "model": f"{LLM_MODEL}",
        "chunk_size": len(chunk),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "url_path": urlparse(url).path,
    }

    return ProcessedChunk(
        site=site,
        url=url,
        chunk_number=chunk_number,
        title=extracted["title"],
        summary=extracted["summary"],
        content=chunk,  # Store the original chunk content
        metadata=metadata,
        embedding=embedding,
    )


async def insert_chunk(chunk: ProcessedChunk):
    """Insert a processed chunk into Supabase."""
    try:
        # Update metadata to include site since we don't have a dedicated column
        metadata = chunk.metadata.copy()
        metadata["site"] = chunk.site  # Store site in metadata instead
        
        data = {
            # Remove site field since it doesn't exist in the table
            "url": chunk.url,
            "chunk_number": chunk.chunk_number,
            "title": chunk.title,
            "summary": chunk.summary,
            "content": chunk.content,
            "metadata": metadata,  # Updated metadata with site
            "embedding": chunk.embedding,
        }

        result = supabase.table("site_pages").insert(data).execute()
        print(f"Inserted chunk {chunk.chunk_number} for {chunk.url} from {chunk.site}")
        return result
    except Exception as e:
        print(f"Error inserting chunk: {e}")
        return None


async def process_and_store_document(url: str, markdown: str, site: str = Sites.PYDANTIC.value):
    """Process a document and store its chunks in parallel."""
    # Split into chunks
    chunks = chunk_text(markdown)

    # Process chunks in parallel
    tasks = [process_chunk(chunk, i, url, site) for i, chunk in enumerate(chunks)]
    processed_chunks = await asyncio.gather(*tasks)

    # Store chunks in parallel
    insert_tasks = [insert_chunk(chunk) for chunk in processed_chunks]
    await asyncio.gather(*insert_tasks)


async def crawl_parallel(urls: List[str], max_concurrent: int = 5, site: str = Sites.PYDANTIC.value):
    """Crawl multiple URLs in parallel with a concurrency limit."""
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
    )
    crawl_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    # Create the crawler instance
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.start()

    try:
        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_url(url: str):
            async with semaphore:
                result = await crawler.arun(
                    url=url, config=crawl_config, session_id="session1"
                )
                if result.success:
                    print(f"Successfully crawled: {url}")
                    await process_and_store_document(
                        url, result.markdown, site
                    )
                else:
                    print(f"Failed: {url} - Error: {result.error_message}")

        # Process all URLs in parallel with limited concurrency
        await asyncio.gather(*[process_url(url) for url in urls])
        # await process_url(urls[0])
    finally:
        await crawler.close()


def get_urls(site: str = Sites.PYDANTIC.value) -> List[str]:
    """Get URLs from documentation sitemap."""
    try:
        sitemap_url = SITEMAP_URLS[site]
        response = requests.get(sitemap_url)
        response.raise_for_status()

        # Parse the XML
        root = ElementTree.fromstring(response.content)

        # Extract all URLs from the sitemap
        namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [loc.text for loc in root.findall(".//ns:loc", namespace)]
        print(f"Found {len(urls)} URLs in {site} sitemap")

        return urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []


def get_urls_from_dict() -> List[str]:
    """Get URLs from SITEMAP dictionary."""
    urls = []
    if SITE == "all":
        for site in SITEMAP:
            for section in SITEMAP[site]:
                urls.extend(SITEMAP[site][section])
        return urls

    if SITE not in SITEMAP:
        return urls

    for section in SITEMAP[SITE]:
        urls.extend(SITEMAP[SITE][section])

    return urls


async def main(site: str = Sites.PYDANTIC.value):
    # Get URLs from Pydantic AI docs
    if site:
        urls = get_urls(site)
    else:
        urls = get_urls_from_dict()

    if not urls:
        print("No URLs found to crawl")
        return

    await crawl_parallel(urls, site=site)


if __name__ == "__main__":
    # Initialize OpenAI and Supabase clients
    openai_client = AsyncOpenAI(api_key=OPEN_AI_API_KEY)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # What do you want to crawl?
    SITE = Sites.FILECOIN.value

    asyncio.run(main(SITE))
