"""Image analysis providers (OpenAI, Ollama, etc.)."""
from .ollama import OllamaAnalyzer
from .openai import OpenAIAnalyzer


def create_analyzer(
	provider: str = "openai",
	*,
	openai_api_key: str | None = None,
	openai_model: str | None = None,
	ollama_model: str | None = None,
	ollama_host: str | None = None,
	max_tokens: int | None = None,
):
	"""Create an analyzer instance from provider-specific options."""
	normalized = provider.strip().lower()

	if normalized == "openai":
		kwargs = {}
		if openai_api_key is not None:
			kwargs["api_key"] = openai_api_key
		if openai_model is not None:
			kwargs["model"] = openai_model
		if max_tokens is not None:
			kwargs["max_tokens"] = max_tokens
		return OpenAIAnalyzer(**kwargs)

	if normalized == "ollama":
		kwargs = {}
		if ollama_model is not None:
			kwargs["model"] = ollama_model
		if ollama_host is not None:
			kwargs["host"] = ollama_host
		if max_tokens is not None:
			kwargs["max_tokens"] = max_tokens
		return OllamaAnalyzer(**kwargs)

	raise ValueError(f"Unsupported analyzer provider: {provider}")


__all__ = ["OpenAIAnalyzer", "OllamaAnalyzer", "create_analyzer"]
