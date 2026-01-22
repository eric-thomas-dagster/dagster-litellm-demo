"""
Production-ready LiteLLM client for Dagster with all advanced features.

Features:
- Automatic retries with exponential backoff
- Structured output (Pydantic models)
- Model escalation ladder
- Rich metadata capture
- Caching (Redis/in-memory) [OPTIONAL]
- Callbacks for observability (Langfuse, W&B) [OPTIONAL]
- Streaming responses [OPTIONAL]
- Function calling / tool use [OPTIONAL]
- Embeddings [OPTIONAL]
- Router with fallbacks [OPTIONAL]
- Budget management [OPTIONAL]
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generator, Literal, Optional, Type, TypeVar

from dagster import get_dagster_logger
from pydantic import BaseModel, ValidationError

import litellm
from litellm import Router
from litellm.caching import Cache

T = TypeVar("T", bound=BaseModel)


# ===== Configuration Classes =====


@dataclass
class CacheConfig:
    """Configuration for LiteLLM caching."""

    enabled: bool = False
    type: Literal["redis", "in-memory"] = "in-memory"
    ttl: int = 3600  # Time to live in seconds

    # Redis config (only if type="redis")
    redis_host: Optional[str] = None
    redis_port: int = 6379
    redis_password: Optional[str] = None


@dataclass
class CallbackConfig:
    """Configuration for LiteLLM callbacks (observability)."""

    enabled: bool = False

    # Observability platforms
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: Optional[str] = None

    wandb_project: Optional[str] = None
    wandb_api_key: Optional[str] = None

    # Custom callback functions
    custom_callbacks: list[str] = field(default_factory=list)


@dataclass
class RouterConfig:
    """Configuration for LiteLLM Router (load balancing, fallbacks)."""

    enabled: bool = False
    # Model list with fallbacks
    # Example: [
    #     {"model_name": "gpt-4o-mini", "litellm_params": {"model": "gpt-4o-mini"}},
    #     {"model_name": "claude-haiku", "litellm_params": {"model": "claude-3-5-haiku-20241022"}},
    # ]
    model_list: list[dict[str, Any]] = field(default_factory=list)
    # Routing strategy: "simple-shuffle", "least-busy", "usage-based-routing", "latency-based-routing"
    routing_strategy: str = "simple-shuffle"
    num_retries: int = 3
    fallback_models: list[str] = field(default_factory=list)


@dataclass
class BudgetConfig:
    """Configuration for budget management."""

    enabled: bool = False
    max_budget_usd: Optional[float] = None
    budget_duration: str = "1d"  # "1h", "1d", "1w", "1mo"


@dataclass
class LiteLLMConfig:
    """Complete configuration for LiteLLM client with all features."""

    # Basic settings
    default_model: str
    timeout_s: float = 60.0
    max_retries: int = 3
    initial_backoff_s: float = 1.0
    max_backoff_s: float = 10.0

    # Model escalation ladder
    escalate_models: list[str] = field(default_factory=list)

    # API config
    api_base: Optional[str] = None
    api_key: Optional[str] = None

    # Advanced features (all optional)
    cache_config: Optional[CacheConfig] = None
    callback_config: Optional[CallbackConfig] = None
    router_config: Optional[RouterConfig] = None
    budget_config: Optional[BudgetConfig] = None


# ===== Main Client =====


class LiteLLMClient:
    """
    Production-ready LiteLLM client for Dagster.

    Core features (always available):
    - Automatic retries with exponential backoff
    - Structured output (Pydantic models)
    - Model escalation ladder (try cheap models first, escalate on failure)
    - Rich metadata capture (tokens, cost, latency)
    - JSON extraction and validation

    Advanced features (optional via config):
    - Caching (Redis or in-memory) to avoid redundant API calls
    - Callbacks for Langfuse, Weights & Biases, custom tracking
    - Streaming responses for better UX
    - Function calling / tool use for agentic workflows
    - Embeddings for vector operations
    - Router for load balancing and intelligent fallbacks
    - Budget management to enforce spend limits

    Example (basic):
        client = LiteLLMClient(
            LiteLLMConfig(default_model="gpt-4o-mini")
        )

    Example (with caching and callbacks):
        client = LiteLLMClient(
            LiteLLMConfig(
                default_model="gpt-4o-mini",
                cache_config=CacheConfig(enabled=True, type="in-memory"),
                callback_config=CallbackConfig(enabled=True, langfuse_public_key="..."),
            )
        )
    """

    def __init__(self, cfg: LiteLLMConfig):
        self.cfg = cfg
        self.log = get_dagster_logger()
        self.router: Optional[Router] = None

        # Configure API base/key
        if cfg.api_base:
            litellm.api_base = cfg.api_base
        if cfg.api_key:
            litellm.api_key = cfg.api_key

        # Setup optional features
        if cfg.cache_config and cfg.cache_config.enabled:
            self._setup_cache(cfg.cache_config)

        if cfg.callback_config and cfg.callback_config.enabled:
            self._setup_callbacks(cfg.callback_config)

        if cfg.router_config and cfg.router_config.enabled:
            self._setup_router(cfg.router_config)

        if cfg.budget_config and cfg.budget_config.enabled:
            self._setup_budget(cfg.budget_config)

    # ===== Setup Methods =====

    def _setup_cache(self, cache_cfg: CacheConfig) -> None:
        """Initialize LiteLLM caching."""
        if cache_cfg.type == "redis":
            if not cache_cfg.redis_host:
                raise ValueError("redis_host required when cache type is 'redis'")
            litellm.cache = Cache(
                type="redis",
                host=cache_cfg.redis_host,
                port=cache_cfg.redis_port,
                password=cache_cfg.redis_password,
                ttl=cache_cfg.ttl,
            )
            self.log.info(f"Initialized Redis cache at {cache_cfg.redis_host}:{cache_cfg.redis_port}")
        else:
            litellm.cache = Cache(type="local", ttl=cache_cfg.ttl)
            self.log.info("Initialized in-memory cache")

    def _setup_callbacks(self, callback_cfg: CallbackConfig) -> None:
        """Initialize LiteLLM callbacks."""
        callbacks = []

        if callback_cfg.langfuse_public_key:
            callbacks.append("langfuse")
            import os

            os.environ["LANGFUSE_PUBLIC_KEY"] = callback_cfg.langfuse_public_key
            os.environ["LANGFUSE_SECRET_KEY"] = callback_cfg.langfuse_secret_key or ""
            if callback_cfg.langfuse_host:
                os.environ["LANGFUSE_HOST"] = callback_cfg.langfuse_host
            self.log.info("Enabled Langfuse callbacks")

        if callback_cfg.wandb_project:
            callbacks.append("wandb")
            import os

            os.environ["WANDB_PROJECT"] = callback_cfg.wandb_project
            if callback_cfg.wandb_api_key:
                os.environ["WANDB_API_KEY"] = callback_cfg.wandb_api_key
            self.log.info("Enabled Weights & Biases callbacks")

        if callback_cfg.custom_callbacks:
            callbacks.extend(callback_cfg.custom_callbacks)

        if callbacks:
            litellm.success_callback = callbacks
            litellm.failure_callback = callbacks

    def _setup_router(self, router_cfg: RouterConfig) -> None:
        """Initialize LiteLLM Router for load balancing and fallbacks."""
        if not router_cfg.model_list:
            self.log.warning("Router enabled but model_list is empty")
            return

        self.router = Router(
            model_list=router_cfg.model_list,
            routing_strategy=router_cfg.routing_strategy,
            num_retries=router_cfg.num_retries,
            fallbacks=router_cfg.fallback_models if router_cfg.fallback_models else None,
        )
        self.log.info(
            f"Initialized Router with {len(router_cfg.model_list)} models "
            f"(strategy: {router_cfg.routing_strategy})"
        )

    def _setup_budget(self, budget_cfg: BudgetConfig) -> None:
        """Setup budget management."""
        if budget_cfg.max_budget_usd:
            litellm.max_budget = budget_cfg.max_budget_usd
            litellm.budget_duration = budget_cfg.budget_duration
            self.log.info(
                f"Enabled budget management: ${budget_cfg.max_budget_usd} per {budget_cfg.budget_duration}"
            )

    # ===== Helper Methods =====

    def _sleep_backoff(self, attempt: int) -> None:
        """Exponential backoff with max ceiling."""
        delay = min(self.cfg.max_backoff_s, self.cfg.initial_backoff_s * (2**attempt))
        self.log.info(f"Backing off for {delay:.2f}s before retry")
        time.sleep(delay)

    def _call_with_retries(self, fn: Callable[[], Any]) -> Any:
        """Execute a function with retry logic for transient failures."""
        last_err: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_err = e
                self.log.warning(f"LiteLLM call failed (attempt {attempt+1}/{self.cfg.max_retries+1}): {e}")
                if attempt < self.cfg.max_retries:
                    self._sleep_backoff(attempt)
                else:
                    self.log.error(f"LiteLLM call failed after {self.cfg.max_retries+1} attempts")
                    raise
        raise last_err  # unreachable

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Estimate cost based on common model pricing (as of Jan 2025).
        Returns cost in USD.
        """
        # Pricing per 1M tokens (prompt, completion)
        pricing = {
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4o-2024-11-20": (2.50, 10.00),
            "gpt-4o-2024-08-06": (2.50, 10.00),
            "gpt-4-turbo": (10.00, 30.00),
            "gpt-4": (30.00, 60.00),
            "gpt-3.5-turbo": (0.50, 1.50),
            "claude-3-5-sonnet-20241022": (3.00, 15.00),
            "claude-3-5-haiku-20241022": (1.00, 5.00),
            "claude-opus-4-5-20251101": (15.00, 75.00),
            "claude-3-opus-20240229": (15.00, 75.00),
            "claude-3-sonnet-20240229": (3.00, 15.00),
            "claude-3-haiku-20240307": (0.25, 1.25),
        }

        # Try exact match first
        if model in pricing:
            prompt_price, completion_price = pricing[model]
        else:
            # Fallback: try to match by model family
            model_lower = model.lower()
            if "gpt-4o-mini" in model_lower:
                prompt_price, completion_price = pricing["gpt-4o-mini"]
            elif "gpt-4o" in model_lower:
                prompt_price, completion_price = pricing["gpt-4o"]
            elif "gpt-4" in model_lower:
                prompt_price, completion_price = pricing["gpt-4"]
            elif "gpt-3.5" in model_lower or "gpt-35" in model_lower:
                prompt_price, completion_price = pricing["gpt-3.5-turbo"]
            elif "claude" in model_lower and "opus" in model_lower:
                prompt_price, completion_price = pricing["claude-opus-4-5-20251101"]
            elif "claude" in model_lower and "sonnet" in model_lower:
                prompt_price, completion_price = pricing["claude-3-5-sonnet-20241022"]
            elif "claude" in model_lower and "haiku" in model_lower:
                prompt_price, completion_price = pricing["claude-3-5-haiku-20241022"]
            else:
                # Unknown model, use conservative estimate
                self.log.warning(f"Unknown model '{model}' for cost estimation, using default pricing")
                prompt_price, completion_price = (1.00, 3.00)

        # Calculate cost
        prompt_cost = (prompt_tokens / 1_000_000) * prompt_price
        completion_cost = (completion_tokens / 1_000_000) * completion_price
        return prompt_cost + completion_cost

    # ===== Core Methods =====

    def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tags: Optional[dict[str, str]] = None,
        use_cache: bool = True,
        response_format: Optional[dict[str, str]] = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Standard chat completion that returns raw text + metadata.

        Args:
            messages: List of chat messages (role + content)
            model: Model to use (defaults to config default_model)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tags: Optional tags for metadata tracking
            use_cache: Whether to use caching (if enabled)
            response_format: Optional response format (e.g., {"type": "json_object"} for JSON mode)

        Returns:
            Tuple of (response text, usage metadata dict)
        """
        chosen_model = model or self.cfg.default_model
        started = time.time()

        def do_call():
            client = self.router if self.router else litellm
            call_kwargs = {
                "model": chosen_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": self.cfg.timeout_s,
                "caching": use_cache if self.cfg.cache_config and self.cfg.cache_config.enabled else False,
                "metadata": {"tags": tags or {}},
            }
            # Add response_format if specified (for JSON mode on supported providers)
            if response_format:
                call_kwargs["response_format"] = response_format

            return client.completion(**call_kwargs)

        resp = self._call_with_retries(do_call)
        elapsed_ms = int((time.time() - started) * 1000)

        choice0 = resp["choices"][0]
        content = choice0["message"]["content"]

        usage = resp.get("usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # Calculate cost (use litellm's cost calculation if available)
        cost_usd = 0.0
        try:
            # LiteLLM provides cost in response for some models
            cost_usd = resp.get("_hidden_params", {}).get("response_cost", 0.0)
            if not cost_usd and total_tokens > 0:
                # Fallback: use litellm's completion_cost function (already imported at top)
                cost_usd = litellm.completion_cost(completion_response=resp)
        except Exception:
            # If cost calculation fails, estimate based on common pricing
            cost_usd = self._estimate_cost(chosen_model, prompt_tokens, completion_tokens)

        cache_hit = resp.get("_hidden_params", {}).get("cache_hit", False)

        meta = {
            "model": chosen_model,
            "latency_ms": elapsed_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
            "cache_hit": cache_hit,
            "tokens_per_second": round(total_tokens / (elapsed_ms / 1000), 2) if elapsed_ms > 0 else 0,
            "tags": tags or {},
        }

        self.log.info(f"LiteLLM usage: {meta}")
        return content, meta

    def chat_json(
        self,
        *,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        tags: Optional[dict[str, str]] = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Call LiteLLM and return parsed JSON dict from the model.

        Returns:
            Dict with keys: "data" (parsed JSON) and "meta" (usage metadata)
        """
        content, meta = self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tags=tags,
            use_cache=use_cache,
            response_format={"type": "json_object"},  # Enable JSON mode for supported providers
        )

        # Parse JSON
        try:
            parsed = json.loads(content)
        except Exception as e:
            self.log.warning(f"Direct JSON parse failed: {e}. Attempting to extract JSON block.")
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1:
                raise ValueError(f"Could not extract JSON from response: {content[:200]}")
            parsed = json.loads(content[start : end + 1])

        return {"data": parsed, "meta": meta}

    def chat_pydantic(
        self,
        *,
        messages: list[dict[str, str]],
        out_model: Type[T],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        tags: Optional[dict[str, str]] = None,
        use_cache: bool = True,
    ) -> tuple[T, dict[str, Any]]:
        """
        Call LiteLLM and return strongly-typed Pydantic output + metadata.

        Uses an escalation ladder: tries default model first, then escalates
        to more powerful models if validation fails.

        Returns:
            Tuple of (validated Pydantic object, usage metadata dict)
        """
        ladder = (model or self.cfg.default_model,) + tuple(self.cfg.escalate_models)

        last_err: Exception | None = None
        for i, m in enumerate(ladder):
            try:
                # Give the model strong instructions for JSON-only output
                schema = out_model.model_json_schema()
                properties = schema.get("properties", {})
                required_fields = set(schema.get("required", []))

                # Build a clear description of expected fields
                field_descriptions = []
                for field_name, field_info in properties.items():
                    field_type = field_info.get("type", "any")
                    is_required = field_name in required_fields
                    req_marker = " (required)" if is_required else " (optional)"

                    # Handle enum/literal types - show allowed values
                    if "enum" in field_info:
                        enum_values = field_info["enum"]
                        field_type = f"enum (must be one of: {', '.join(repr(v) for v in enum_values)})"
                    # Handle array types
                    elif field_type == "array":
                        items_type = field_info.get("items", {}).get("type", "any")
                        field_type = f"array of {items_type}"
                    # Handle number types with constraints
                    elif field_type == "number":
                        constraints = []
                        if "minimum" in field_info:
                            constraints.append(f"min={field_info['minimum']}")
                        if "maximum" in field_info:
                            constraints.append(f"max={field_info['maximum']}")
                        if constraints:
                            field_type = f"number ({', '.join(constraints)})"

                    # Add field description if available
                    description = field_info.get("description", "")
                    desc_text = f" - {description}" if description else ""

                    field_descriptions.append(f"  - {field_name}: {field_type}{req_marker}{desc_text}")

                system = {
                    "role": "system",
                    "content": (
                        "You must respond with ONLY a valid JSON object containing these fields:\n"
                        f"{chr(10).join(field_descriptions)}\n\n"
                        "CRITICAL INSTRUCTIONS:\n"
                        "1. Return actual data values, NOT a schema definition or description\n"
                        "2. For enum fields, you MUST use EXACTLY one of the allowed values listed above\n"
                        "   - Do not use similar words or synonyms\n"
                        "   - Do not use capitalized versions\n"
                        "   - Use the exact lowercase string as shown\n"
                        "   - If a concept doesn't match any enum value, choose the closest match or 'other'\n"
                        "3. Do not include markdown code blocks, backticks, or explanatory text\n"
                        "4. Return only the raw JSON object\n\n"
                        "Example: If you see values like 'security' but the enum only allows "
                        "['bug', 'how_to', 'billing', 'access', 'feature_request', 'other'], "
                        "choose 'bug' or 'other' - do NOT use 'security'."
                    ),
                }
                payload = self.chat_json(
                    messages=[system, *messages],
                    model=m,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tags={**(tags or {}), "attempt": str(i), "escalation_model": m},
                    use_cache=use_cache,
                )

                # Auto-correct common enum mistakes before validation
                data = payload["data"]
                for field_name, field_info in properties.items():
                    if "enum" in field_info and field_name in data:
                        allowed_values = field_info["enum"]
                        actual_value = data[field_name]

                        # If the value is not in allowed values, try to fix it
                        if actual_value not in allowed_values:
                            # Try case-insensitive match
                            actual_lower = str(actual_value).lower()
                            matched = False
                            for allowed in allowed_values:
                                if str(allowed).lower() == actual_lower:
                                    data[field_name] = allowed
                                    matched = True
                                    self.log.warning(
                                        f"Auto-corrected {field_name}: '{actual_value}' -> '{allowed}' (case mismatch)"
                                    )
                                    break

                            # If still not matched and "other" is an option, use it
                            if not matched and "other" in allowed_values:
                                self.log.warning(
                                    f"Auto-corrected {field_name}: '{actual_value}' -> 'other' (invalid value)"
                                )
                                data[field_name] = "other"

                obj = out_model.model_validate(data)

                if i > 0:
                    self.log.info(f"Successfully escalated to model {m} after {i} failed attempts")

                return obj, payload["meta"]
            except (ValidationError, Exception) as e:
                last_err = e
                self.log.warning(f"Validation/model attempt {i+1} failed using {m}: {e}")
                continue

        raise last_err or RuntimeError("Failed to produce valid output after all escalation attempts")

    # ===== Advanced Methods (Optional Features) =====

    def chat_streaming(
        self,
        *,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> Generator[tuple[str, dict[str, Any]], None, None]:
        """
        Stream chat completion responses chunk by chunk.

        Yields:
            Tuples of (chunk_text, metadata)
        """
        chosen_model = model or self.cfg.default_model
        started = time.time()

        client = self.router if self.router else litellm
        response = client.completion(
            model=chosen_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=self.cfg.timeout_s,
            stream=True,
            metadata={"tags": tags or {}},
        )

        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                yield content, {
                    "model": chosen_model,
                    "chunk_length": len(content),
                    "tags": tags or {},
                }

        elapsed_ms = int((time.time() - started) * 1000)
        final_meta = {
            "model": chosen_model,
            "latency_ms": elapsed_ms,
            "total_length": len(full_response),
            "tags": tags or {},
        }
        self.log.info(f"Streaming completed: {final_meta}")

    def chat_with_tools(
        self,
        *,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict = "auto",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tags: Optional[dict[str, str]] = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Chat completion with function calling / tool use.

        Args:
            messages: Chat messages
            tools: List of tool definitions (OpenAI format)
            tool_choice: "auto", "none", or specific tool
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Max tokens
            tags: Metadata tags

        Returns:
            Tuple of (response_dict, metadata)
            response_dict contains either "content" or "tool_calls"
        """
        chosen_model = model or self.cfg.default_model
        started = time.time()

        def do_call():
            client = self.router if self.router else litellm
            return client.completion(
                model=chosen_model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=self.cfg.timeout_s,
                metadata={"tags": tags or {}},
            )

        resp = self._call_with_retries(do_call)
        elapsed_ms = int((time.time() - started) * 1000)

        choice0 = resp["choices"][0]
        message = choice0["message"]

        result = {}
        if message.get("content"):
            result["content"] = message["content"]
        if message.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message["tool_calls"]
            ]

        usage = resp.get("usage", {}) or {}
        meta = {
            "model": chosen_model,
            "latency_ms": elapsed_ms,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "finish_reason": choice0.get("finish_reason"),
            "tags": tags or {},
        }

        self.log.info(f"Tool use completed: {meta}")
        return result, meta

    def embeddings(
        self,
        *,
        input: str | list[str],
        model: Optional[str] = None,
        use_cache: bool = True,
        tags: Optional[dict[str, str]] = None,
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """
        Generate embeddings for text.

        Args:
            input: Single string or list of strings to embed
            model: Embedding model (e.g., "text-embedding-3-small")
            use_cache: Whether to use caching
            tags: Metadata tags

        Returns:
            Tuple of (embeddings list, metadata)
        """
        embedding_model = model or "text-embedding-3-small"
        started = time.time()

        def do_call():
            return litellm.embedding(
                model=embedding_model,
                input=input,
                caching=use_cache if self.cfg.cache_config and self.cfg.cache_config.enabled else False,
                metadata={"tags": tags or {}},
            )

        resp = self._call_with_retries(do_call)
        elapsed_ms = int((time.time() - started) * 1000)

        embeddings = [item["embedding"] for item in resp["data"]]

        usage = resp.get("usage", {}) or {}
        meta = {
            "model": embedding_model,
            "latency_ms": elapsed_ms,
            "total_tokens": usage.get("total_tokens"),
            "num_embeddings": len(embeddings),
            "embedding_dim": len(embeddings[0]) if embeddings else 0,
            "cache_hit": resp.get("_hidden_params", {}).get("cache_hit", False),
            "tags": tags or {},
        }

        self.log.info(f"Embeddings generated: {meta}")
        return embeddings, meta


__all__ = [
    "LiteLLMClient",
    "LiteLLMConfig",
    "CacheConfig",
    "CallbackConfig",
    "RouterConfig",
    "BudgetConfig",
]
