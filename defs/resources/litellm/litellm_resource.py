"""
LiteLLM Dagster resource for production-ready LLM integrations.

Single unified client with all features (basic + advanced) built-in.
"""

from dagster import ConfigurableResource
from pydantic import Field

from .litellm_client import (
    BudgetConfig,
    CacheConfig,
    CallbackConfig,
    LiteLLMClient,
    LiteLLMConfig,
    RouterConfig,
)


class LiteLLMResource(ConfigurableResource):
    """
    Dagster resource for LiteLLM integration.

    This resource provides a production-ready LiteLLM client with:

    Core features (always available):
    - Automatic retries with exponential backoff
    - Structured output (Pydantic models + JSON)
    - Model escalation ladder (try cheap models first, escalate on failure)
    - Rich metadata capture (tokens, cost, latency) attached to Dagster events
    - Provider portability (works with OpenAI, Anthropic, Azure, etc.)

    Advanced features (optional via config):
    - Caching (Redis or in-memory) to avoid redundant API calls
    - Callbacks for Langfuse, Weights & Biases, custom tracking
    - Streaming responses for better UX
    - Function calling / tool use for agentic workflows
    - Embeddings for vector operations
    - Router for load balancing and intelligent fallbacks
    - Budget management to enforce spend limits

    Example (basic usage):
        @asset
        def my_llm_asset(context, litellm: LiteLLMResource):
            client = litellm.get_client()
            result, meta = client.chat_pydantic(
                messages=[{"role": "user", "content": "Classify this..."}],
                out_model=MyPydanticModel,
            )
            context.add_output_metadata(meta)
            return result

    Example (with caching):
        litellm: LiteLLMResource(
            default_model="gpt-4o-mini",
            enable_cache=True,
            cache_type="in-memory",
        )

    Example (with router fallbacks):
        litellm: LiteLLMResource(
            default_model="gpt-4o-mini",
            enable_router=True,
            router_model_list=[
                {"model_name": "gpt-4o-mini", "litellm_params": {"model": "gpt-4o-mini"}},
                {"model_name": "claude-haiku", "litellm_params": {"model": "claude-3-5-haiku-20241022"}},
            ],
            router_fallback_models=["claude-haiku"],
        )
    """

    # ===== Basic Settings =====
    default_model: str = Field(
        description="LiteLLM model name (e.g. gpt-4o-mini, claude-3-5-haiku-20241022, etc.)"
    )
    timeout_s: float = Field(
        default=60.0,
        description="Timeout in seconds for LLM API calls",
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retries for transient failures",
    )
    initial_backoff_s: float = Field(
        default=1.0,
        description="Initial backoff delay in seconds (exponentially increases)",
    )
    max_backoff_s: float = Field(
        default=10.0,
        description="Maximum backoff delay in seconds",
    )
    escalate_models: list[str] = Field(
        default_factory=list,
        description=(
            "Optional escalation ladder: if default_model fails validation, "
            "try these models in order. Example: ['gpt-4o-mini', 'gpt-4o'] "
            "tries cheap model first, escalates to expensive model on failure."
        ),
    )
    api_base: str | None = Field(
        default=None,
        description="Optional API base URL (if using LiteLLM proxy or custom endpoint)",
    )
    api_key: str | None = Field(
        default=None,
        description="Optional API key (if not using environment variables)",
    )

    # ===== Caching (Optional) =====
    enable_cache: bool = Field(
        default=False,
        description="Enable caching to avoid redundant API calls (saves 50-90% cost for repeated queries)",
    )
    cache_type: str = Field(
        default="in-memory",
        description="Cache backend: 'in-memory' or 'redis'",
    )
    cache_ttl: int = Field(
        default=3600,
        description="Cache time-to-live in seconds (default: 1 hour)",
    )
    redis_host: str | None = Field(
        default=None,
        description="Redis host (required if cache_type='redis')",
    )
    redis_port: int = Field(
        default=6379,
        description="Redis port",
    )
    redis_password: str | None = Field(
        default=None,
        description="Redis password (if auth required)",
    )

    # ===== Callbacks / Observability (Optional) =====
    enable_callbacks: bool = Field(
        default=False,
        description="Enable callbacks for Langfuse, Weights & Biases, or custom tracking",
    )
    langfuse_public_key: str | None = Field(
        default=None,
        description="Langfuse public key for LLM observability",
    )
    langfuse_secret_key: str | None = Field(
        default=None,
        description="Langfuse secret key",
    )
    langfuse_host: str | None = Field(
        default=None,
        description="Langfuse host URL (default: cloud.langfuse.com)",
    )
    wandb_project: str | None = Field(
        default=None,
        description="Weights & Biases project name",
    )
    wandb_api_key: str | None = Field(
        default=None,
        description="Weights & Biases API key",
    )

    # ===== Router (Optional) =====
    enable_router: bool = Field(
        default=False,
        description="Enable router for load balancing and automatic fallbacks (99.99% uptime)",
    )
    router_model_list: list[dict] = Field(
        default_factory=list,
        description="List of model configs for router (e.g., [{'model_name': 'gpt-4o-mini', 'litellm_params': {...}}])",
    )
    router_fallback_models: list[str] = Field(
        default_factory=list,
        description="List of fallback model names (e.g., ['claude-haiku', 'azure-gpt-4o'])",
    )
    router_strategy: str = Field(
        default="simple-shuffle",
        description="Routing strategy: 'simple-shuffle', 'least-busy', 'latency-based-routing'",
    )

    # ===== Budget Management (Optional) =====
    enable_budget: bool = Field(
        default=False,
        description="Enable budget management to enforce spend limits",
    )
    max_budget_usd: float | None = Field(
        default=None,
        description="Maximum budget in USD (raises error when exceeded)",
    )
    budget_duration: str = Field(
        default="1d",
        description="Budget window: '1h', '1d', '1w', '1mo'",
    )

    def get_client(self) -> LiteLLMClient:
        """Get a configured LiteLLM client instance."""
        # Build cache config
        cache_config = None
        if self.enable_cache:
            cache_config = CacheConfig(
                enabled=True,
                type=self.cache_type,  # type: ignore
                ttl=self.cache_ttl,
                redis_host=self.redis_host,
                redis_port=self.redis_port,
                redis_password=self.redis_password,
            )

        # Build callback config
        callback_config = None
        if self.enable_callbacks:
            callback_config = CallbackConfig(
                enabled=True,
                langfuse_public_key=self.langfuse_public_key,
                langfuse_secret_key=self.langfuse_secret_key,
                langfuse_host=self.langfuse_host,
                wandb_project=self.wandb_project,
                wandb_api_key=self.wandb_api_key,
            )

        # Build router config
        router_config = None
        if self.enable_router:
            router_config = RouterConfig(
                enabled=True,
                model_list=self.router_model_list,
                fallback_models=self.router_fallback_models,
                routing_strategy=self.router_strategy,
            )

        # Build budget config
        budget_config = None
        if self.enable_budget:
            budget_config = BudgetConfig(
                enabled=True,
                max_budget_usd=self.max_budget_usd,
                budget_duration=self.budget_duration,
            )

        # Create unified client with all configs
        cfg = LiteLLMConfig(
            default_model=self.default_model,
            timeout_s=self.timeout_s,
            max_retries=self.max_retries,
            initial_backoff_s=self.initial_backoff_s,
            max_backoff_s=self.max_backoff_s,
            escalate_models=self.escalate_models,
            api_base=self.api_base,
            api_key=self.api_key,
            cache_config=cache_config,
            callback_config=callback_config,
            router_config=router_config,
            budget_config=budget_config,
        )
        return LiteLLMClient(cfg)


__all__ = ["LiteLLMResource"]
