from __future__ import annotations
# ...existing imports...
# from constants.api_keys import load_environment

import asyncio
import json
import os
from typing import Literal, TypedDict

import logfire
import streamlit as st
import httpx
from openai import AsyncOpenAI
from supabase import create_client

# Load environment variables

# Import all the message part classes
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from supabase import Client

from ai_expert import AIDeps, ai_expert, SUPABASE_SERVICE_KEY, SUPABASE_URL, OPENAI_API_KEY, LLM_MODEL
# from constants import OPEN_AI_API_KEY, SUPABASE_SERVICE_KEY, SUPABASE_URL
from crawl_docs import Sites

# Initialize clients
@st.cache_resource(ttl=3600)  # Cache for 1 hour
def init_clients():
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
    )
    
    # Register cleanup callback
    def cleanup():
        st.session_state['client_cleanup_done'] = False
        if not st.session_state.get('client_cleanup_done', False):
            st.cache_data.clear()
            asyncio.run(http_client.aclose())
            asyncio.run(openai_client.close())
            st.session_state['client_cleanup_done'] = True
    
    # st.experimental_singleton.clear()
    # st.runtime.legacy_caching.caching.clear_cache()
    st.session_state['cleanup'] = cleanup
    
    return supabase, openai_client, http_client

supabase, openai_client, http_client = init_clients()

# Initialize AI deps
deps = AIDeps(
    supabase=supabase,
    openai_client=openai_client,
    http_client=http_client
)

SITE = Sites.FILECOIN.value

# Configure logfire to suppress warnings (optional)
logfire.configure(send_to_logfire="never")


class ChatMessage(TypedDict):
    """Format of messages sent to the browser/API."""

    role: Literal["user", "model"]
    timestamp: str
    content: str


def display_message_part(part):
    """
    Display a single part of a message in the Streamlit UI.
    Customize how you display system prompts, user prompts,
    tool calls, tool returns, etc.
    """
    # system-prompt
    if part.part_kind == "system-prompt":
        with st.chat_message("system"):
            st.markdown(f"**System**: {part.content}")
    # user-prompt
    elif part.part_kind == "user-prompt":
        with st.chat_message("user"):
            st.markdown(part.content)
    # text
    elif part.part_kind == "text":
        with st.chat_message("assistant"):
            st.markdown(part.content)


async def run_agent_with_streaming(user_input: str):
    """
    Run the agent with streaming text for the user_input prompt,
    while maintaining the entire conversation in `st.session_state.messages`.
    """
    # Prepare dependencies
    deps = AIDeps(supabase=supabase, openai_client=openai_client)

    # Run the agent in a stream
    async with ai_expert.run_stream(
        user_input,
        deps=deps,
        message_history=st.session_state.messages[
            :-1
        ],  # pass entire conversation so far
    ) as result:
        # We'll gather partial text to show incrementally
        partial_text = ""
        message_placeholder = st.empty()

        # Render partial text as it arrives
        async for chunk in result.stream_text(delta=True):
            partial_text += chunk
            message_placeholder.markdown(partial_text)

        # Now that the stream is finished, we have a final result.
        # Add new messages from this run, excluding user-prompt messages
        filtered_messages = [
            msg
            for msg in result.new_messages()
            if not (
                hasattr(msg, "parts")
                and any(part.part_kind == "user-prompt" for part in msg.parts)
            )
        ]
        st.session_state.messages.extend(filtered_messages)

        # Add the final response to the messages
        st.session_state.messages.append(
            ModelResponse(parts=[TextPart(content=partial_text)])
        )


async def main():
    st.title("AI Agentic RAG")
    st.write(
        f"Ask any question about {SITE} API, the hidden truths of the beauty of this framework lie within."
    )

    # Initialize chat history in session state if not present
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display all messages from the conversation so far
    # Each message is either a ModelRequest or ModelResponse.
    # We iterate over their parts to decide how to display them.
    for msg in st.session_state.messages:
        if isinstance(msg, ModelRequest) or isinstance(msg, ModelResponse):
            for part in msg.parts:
                display_message_part(part)

    # Chat input for the user
    user_input = st.chat_input(f"What questions do you have about {SITE} API?")

    if user_input:
        # We append a new request to the conversation explicitly
        st.session_state.messages.append(
            ModelRequest(parts=[UserPromptPart(content=user_input)])
        )

        # Display user prompt in the UI
        with st.chat_message("user"):
            st.markdown(user_input)

        # Display the assistant's partial response while streaming
        with st.chat_message("assistant"):
            # Actually run the agent now, streaming the text
            await run_agent_with_streaming(user_input)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        if 'cleanup' in st.session_state:
            st.session_state['cleanup']()
