"""
Enhanced LiteLLM examples demonstrating advanced features:
- Caching
- Streaming
- Function calling / tool use
- Embeddings
- Router with fallbacks

NOTE: These examples require enabling the corresponding features in the resource config.
To use these examples, configure the LiteLLMResource with enable_cache=True, etc.
"""

from dagster import AssetExecutionContext, asset
from pydantic import BaseModel, Field

from defs.resources import LiteLLMResource


# ====== Example 1: Caching ======


class Summary(BaseModel):
    """Summary schema for caching example."""

    key_points: list[str]
    main_topic: str
    sentiment: str


@asset(
    description="Demonstrate LiteLLM caching - repeated calls are cached",
    compute_kind="llm_cached",
    group_name="examples",
)
def cached_summaries(context: AssetExecutionContext, litellm: LiteLLMResource) -> list[dict]:
    """
    Generate summaries with caching enabled.

    First call hits the API, subsequent identical calls return from cache.
    """
    client = litellm.get_client()

    documents = [
        {"id": "doc1", "text": "Climate change is a pressing global issue requiring immediate action..."},
        {"id": "doc1", "text": "Climate change is a pressing global issue requiring immediate action..."},  # Duplicate
        {"id": "doc2", "text": "Artificial intelligence is transforming industries across the world..."},
    ]

    results = []
    cache_hits = 0

    for doc in documents:
        summary, meta = client.chat_pydantic(
            messages=[{"role": "user", "content": f"Summarize: {doc['text']}"}],
            out_model=Summary,
            use_cache=True,  # Enable caching
            tags={"doc_id": doc["id"]},
        )

        if meta.get("cache_hit"):
            cache_hits += 1
            context.log.info(f"Cache HIT for {doc['id']}")
        else:
            context.log.info(f"Cache MISS for {doc['id']}")

        results.append({"doc_id": doc["id"], "summary": summary.model_dump(), "meta": meta})

    context.add_output_metadata(
        {
            "total_docs": len(documents),
            "cache_hits": cache_hits,
            "cache_hit_rate": f"{cache_hits / len(documents) * 100:.1f}%",
            "cost_saved": f"~{cache_hits * 0.001:.4f} USD",  # Rough estimate
        }
    )

    return results


# ====== Example 2: Streaming ======


@asset(
    description="Demonstrate streaming LLM responses",
    compute_kind="llm_streaming",
    group_name="examples",
)
def streaming_story(context: AssetExecutionContext, litellm: LiteLLMResource) -> dict:
    """
    Generate a story with streaming for better UX.

    In production, you'd stream chunks to a UI in real-time.
    """
    client = litellm.get_client()
    prompt = "Write a short story (3 paragraphs) about a robot learning to paint."

    full_story = ""
    chunks_received = 0

    context.log.info("Starting streaming story generation...")

    for chunk_text, chunk_meta in client.chat_streaming(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        tags={"type": "creative_writing"},
    ):
        full_story += chunk_text
        chunks_received += 1
        # In a real app, you'd push these chunks to a websocket or SSE endpoint
        context.log.info(f"Received chunk {chunks_received}: {len(chunk_text)} chars")

    context.add_output_metadata(
        {
            "story_length": len(full_story),
            "chunks_received": chunks_received,
            "avg_chunk_size": len(full_story) / chunks_received if chunks_received > 0 else 0,
        }
    )

    return {"story": full_story, "chunks": chunks_received}


# ====== Example 3: Function Calling / Tool Use ======


@asset(
    description="Demonstrate LLM function calling for agentic workflows",
    compute_kind="llm_tools",
    group_name="examples",
)
def agentic_tool_use(context: AssetExecutionContext, litellm: LiteLLMResource) -> dict:
    """
    Use function calling to let the LLM decide which tools to call.

    This is the foundation of agentic workflows.
    """
    client = litellm.get_client()

    # Define available tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "query_database",
                "description": "Query the customer database for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL query to execute"},
                        "limit": {"type": "integer", "description": "Max results to return"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "send_email",
                "description": "Send an email to a customer",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email"},
                        "subject": {"type": "string", "description": "Email subject"},
                        "body": {"type": "string", "description": "Email body"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        },
    ]

    user_request = "Find all customers who haven't logged in for 30 days and send them a re-engagement email."

    response, meta = client.chat_with_tools(
        messages=[
            {"role": "system", "content": "You are an AI assistant that helps with customer management."},
            {"role": "user", "content": user_request},
        ],
        tools=tools,
        tool_choice="auto",
        tags={"workflow": "customer_reengagement"},
    )

    # Extract tool calls
    tool_calls = response.get("tool_calls", [])

    context.log.info(f"LLM decided to call {len(tool_calls)} tools")
    for tc in tool_calls:
        context.log.info(f"Tool: {tc['function']['name']}, Args: {tc['function']['arguments']}")

    context.add_output_metadata(
        {
            "num_tool_calls": len(tool_calls),
            "tools_called": [tc["function"]["name"] for tc in tool_calls],
            "finish_reason": meta.get("finish_reason"),
            "total_tokens": meta.get("total_tokens"),
        }
    )

    return {"tool_calls": tool_calls, "meta": meta}


# ====== Example 4: Embeddings for Vector Search ======


@asset(
    description="Generate embeddings for semantic search",
    compute_kind="embeddings",
    group_name="examples",
)
def document_embeddings(context: AssetExecutionContext, litellm: LiteLLMResource) -> dict:
    """
    Generate embeddings for documents to enable semantic search.

    In production, you'd store these in a vector database (Pinecone, Weaviate, pgvector).
    """
    client = litellm.get_client()

    documents = [
        {"id": "doc1", "text": "Python is a high-level programming language known for its simplicity."},
        {"id": "doc2", "text": "Machine learning enables computers to learn from data without explicit programming."},
        {"id": "doc3", "text": "Docker containers provide a lightweight way to package and deploy applications."},
    ]

    # Extract text
    texts = [doc["text"] for doc in documents]

    # Generate embeddings in batch
    embeddings, meta = client.embeddings(
        input=texts,
        model="text-embedding-3-small",  # OpenAI's latest embedding model
        use_cache=True,
        tags={"batch": "documents"},
    )

    # Attach embeddings to documents
    embedded_docs = [
        {**doc, "embedding": emb, "embedding_dim": len(emb)} for doc, emb in zip(documents, embeddings)
    ]

    context.add_output_metadata(
        {
            "num_documents": len(documents),
            "embedding_model": meta["model"],
            "embedding_dim": meta["embedding_dim"],
            "total_tokens": meta.get("total_tokens"),
            "cache_hit": meta.get("cache_hit", False),
        }
    )

    # In production, you'd insert into vector DB here:
    # vector_db.insert(embedded_docs)

    return {"documents": embedded_docs, "meta": meta}


@asset(
    description="Semantic search using embeddings",
    compute_kind="vector_search",
    group_name="examples",
)
def semantic_search(
    context: AssetExecutionContext,
    litellm: LiteLLMResource,
    document_embeddings: dict,
) -> dict:
    """
    Perform semantic search by comparing query embedding to document embeddings.
    """
    client = litellm.get_client()
    query = "How do I write code?"

    # Get query embedding
    query_emb, meta = client.embeddings(
        input=query,
        model="text-embedding-3-small",
        use_cache=True,
        tags={"type": "query"},
    )
    query_vector = query_emb[0]

    # Compute cosine similarity with all documents
    import math

    def cosine_similarity(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b)

    docs = document_embeddings["documents"]
    results = []
    for doc in docs:
        similarity = cosine_similarity(query_vector, doc["embedding"])
        results.append(
            {
                "doc_id": doc["id"],
                "text": doc["text"],
                "similarity": similarity,
            }
        )

    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)

    context.log.info(f"Top result: {results[0]['text']} (similarity: {results[0]['similarity']:.4f})")

    context.add_output_metadata(
        {
            "query": query,
            "num_results": len(results),
            "top_similarity": results[0]["similarity"],
            "top_result": results[0]["text"],
        }
    )

    return {"query": query, "results": results}


# ====== Example 5: Multi-Step Agentic Workflow ======


class AgentDecision(BaseModel):
    """Agent's decision on what to do."""

    reasoning: str = Field(description="Why the agent chose this action")
    action: str = Field(description="Action to take: query_db, send_email, create_ticket, or done")
    params: dict = Field(description="Parameters for the action")


@asset(
    description="Multi-step agentic workflow with tool use",
    compute_kind="llm_agent",
    group_name="examples",
)
def multi_step_agent(context: AssetExecutionContext, litellm: LiteLLMResource) -> dict:
    """
    Demonstrate a multi-step agentic workflow where the LLM decides next steps.

    The agent can:
    1. Query database
    2. Send emails
    3. Create tickets
    4. Mark as done

    Each step is validated by Dagster (can't go off-script).
    """
    client = litellm.get_client()
    user_task = "A customer reported that their payment failed. Investigate and resolve."

    conversation_history = [
        {"role": "system", "content": "You are a customer support AI agent. Available actions: query_db, send_email, create_ticket, done."},
        {"role": "user", "content": user_task},
    ]

    steps_taken = []
    max_steps = 5

    for step in range(max_steps):
        context.log.info(f"Agent step {step + 1}")

        # Ask agent what to do next
        decision, meta = client.chat_pydantic(
            messages=conversation_history,
            out_model=AgentDecision,
            temperature=0.3,
            tags={"step": str(step)},
        )

        context.log.info(f"Agent decision: {decision.action} - {decision.reasoning}")

        steps_taken.append(
            {
                "step": step + 1,
                "action": decision.action,
                "reasoning": decision.reasoning,
                "params": decision.params,
            }
        )

        # Execute action (stubbed for demo)
        if decision.action == "query_db":
            result = f"[DB Query Result for: {decision.params.get('query', 'N/A')}]"
        elif decision.action == "send_email":
            result = f"[Email sent to: {decision.params.get('to', 'N/A')}]"
        elif decision.action == "create_ticket":
            result = f"[Ticket created: {decision.params.get('title', 'N/A')}]"
        elif decision.action == "done":
            context.log.info("Agent marked task as complete")
            break
        else:
            result = "[Unknown action]"

        # Add result to conversation
        conversation_history.append(
            {"role": "assistant", "content": f"Action: {decision.action}\nReasoning: {decision.reasoning}"}
        )
        conversation_history.append({"role": "user", "content": f"Result: {result}\nWhat's next?"})

    context.add_output_metadata(
        {
            "total_steps": len(steps_taken),
            "final_action": steps_taken[-1]["action"] if steps_taken else "none",
            "actions_taken": [s["action"] for s in steps_taken],
        }
    )

    return {"task": user_task, "steps": steps_taken}


# Export all enhanced examples
__all__ = [
    "cached_summaries",
    "streaming_story",
    "agentic_tool_use",
    "document_embeddings",
    "semantic_search",
    "multi_step_agent",
]
