class AIError(Exception):
    """Base class. Messages are safe to show to users: they never contain credentials or raw prompts."""

    status_code = 502


class ProviderUnavailable(AIError):
    status_code = 503


class ProviderTimeout(AIError):
    status_code = 504


class ProviderAuthError(AIError):
    status_code = 502


class ProviderRateLimited(AIError):
    status_code = 429


class ProviderBadRequest(AIError):
    status_code = 502


class InvalidModelOutput(AIError):
    """The model answered, but not with valid, schema-conforming, evidence-grounded output."""

    status_code = 502


class NotConfigured(AIError):
    status_code = 409
