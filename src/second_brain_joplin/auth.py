"""GitHub sign-in for HTTP mode, limited to listed GitHub accounts.

Claude's custom connectors sign in with OAuth, registering themselves through
Dynamic Client Registration or a Client ID Metadata Document. GitHub does neither,
so FastMCP's :class:`OAuthProxy` stands in front of it: it presents DCR and CIMD to
Claude, sends the person to GitHub to sign in, and hands Claude a token of its own.

GitHub sign-in alone would admit **any** GitHub account, so every request's token
is checked against ``SBJ_ALLOWED_GITHUB_IDS``, a list of numeric GitHub user ids.
Ids, not logins: a login can be renamed and then registered by somebody else, an
id never changes. Anyone else gets 401 before any MCP message is read.

This builds the proxy the way FastMCP's ``GitHubProvider`` does, with one change:
the token verifier is our allowlisting subclass, which ``GitHubProvider`` gives no
way to pass in.
"""

import logging
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

import httpx2
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from fastmcp.utilities.authorization import AuthContext
from key_value.aio.protocols import AsyncKeyValue

from .remote import ServeConfigError

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
CALLBACK_PATH = "/auth/callback"
# Read the profile only. FastMCP's default, ``user``, also allows writing it.
GITHUB_SCOPES = ["read:user"]
# Each verified token is remembered this long, instead of two GitHub API calls per
# MCP request (FastMCP's default is no cache).
VERIFY_CACHE_SECONDS = 300
# claude.ai's OAuth callback, the only client allowed to register by default
# (https://claude.com/docs/connectors/building/authentication).
CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
MIN_SIGNING_KEY_LENGTH = 32

REQUIRED_VARIABLES = (
    "SBJ_GITHUB_CLIENT_ID",
    "SBJ_GITHUB_CLIENT_SECRET",
    "SBJ_JWT_SIGNING_KEY",
    "SBJ_ALLOWED_GITHUB_IDS",
)


@dataclass(frozen=True, repr=False)
class AuthSettings:
    """Sign-in configuration. ``repr`` is off so a secret never lands in a log."""

    client_id: str
    client_secret: str
    jwt_signing_key: str
    allowed_ids: frozenset[str]
    redirect_uris: tuple[str, ...] = (CLAUDE_CALLBACK,)

    def __repr__(self) -> str:
        return f"AuthSettings(allowed_ids={sorted(self.allowed_ids)})"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AuthSettings | None":
        """Read sign-in settings, or None when none of them is set.

        Some but not all set is a mistake, not "off": it is refused, naming what is
        missing and never printing a value.
        """
        env = os.environ if environ is None else environ
        values = {name: env.get(name, "").strip() for name in REQUIRED_VARIABLES}
        if not any(values.values()):
            return None
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ServeConfigError(f"sign-in is only partly configured: set {', '.join(missing)}")
        if len(values["SBJ_JWT_SIGNING_KEY"]) < MIN_SIGNING_KEY_LENGTH:
            raise ServeConfigError(
                f"SBJ_JWT_SIGNING_KEY must be at least {MIN_SIGNING_KEY_LENGTH} characters "
                "(for example: openssl rand -base64 32)"
            )
        redirect_raw = env.get("SBJ_OAUTH_REDIRECT_URIS", "").strip()
        redirect_uris = tuple(_split(redirect_raw)) if redirect_raw else (CLAUDE_CALLBACK,)
        for uri in redirect_uris:
            if not uri.startswith("https://"):
                raise ServeConfigError(f"SBJ_OAUTH_REDIRECT_URIS must be https URLs, got {uri!r}")
        return cls(
            client_id=values["SBJ_GITHUB_CLIENT_ID"],
            client_secret=values["SBJ_GITHUB_CLIENT_SECRET"],
            jwt_signing_key=values["SBJ_JWT_SIGNING_KEY"],
            allowed_ids=parse_github_ids(values["SBJ_ALLOWED_GITHUB_IDS"]),
            redirect_uris=redirect_uris,
        )


def _split(raw: str) -> list[str]:
    return [part for part in re.split(r"[\s,]+", raw) if part]


def parse_github_ids(raw: str) -> frozenset[str]:
    """Parse ``SBJ_ALLOWED_GITHUB_IDS``: numeric ids, comma- or space-separated."""
    ids = _split(raw)
    bad = [part for part in ids if not part.isdigit()]
    if bad:
        raise ServeConfigError(
            "SBJ_ALLOWED_GITHUB_IDS takes numeric GitHub user ids, not logins "
            f"(find yours at https://api.github.com/users/<login>), got {', '.join(bad)}"
        )
    if not ids:
        raise ServeConfigError("SBJ_ALLOWED_GITHUB_IDS lists no ids")
    return frozenset(str(int(part)) for part in ids)


class AllowlistGitHubTokenVerifier(GitHubTokenVerifier):
    """A GitHub token verifier that accepts listed GitHub user ids only.

    The parent verifies the token with GitHub and puts the numeric user id in the
    ``sub`` claim. Anyone not listed is treated like an invalid token: the request
    gets 401 and no tool runs. GitHub being unreachable still raises the parent's
    ``TokenVerificationError``, which FastMCP answers as a temporary failure rather
    than a sign-out.
    """

    def __init__(
        self,
        *,
        allowed_ids: frozenset[str],
        required_scopes: list[str] | None = None,
        cache_ttl_seconds: int | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            required_scopes=required_scopes,
            cache_ttl_seconds=cache_ttl_seconds,
            http_client=http_client,
        )
        if not allowed_ids:
            raise ValueError("allowed_ids must not be empty")
        self.allowed_ids = frozenset(allowed_ids)

    async def verify_token(self, token: str) -> AccessToken | None:
        result = await super().verify_token(token)
        if result is None:
            return None
        if not is_allowed(result, self.allowed_ids):
            logger.warning(
                "refused GitHub account %s (id %s): not in SBJ_ALLOWED_GITHUB_IDS",
                result.claims.get("login"),
                result.claims.get("sub"),
            )
            return None
        return result


def is_allowed(token: AccessToken | None, allowed_ids: frozenset[str]) -> bool:
    """True if ``token`` belongs to a listed GitHub user id."""
    if token is None:
        return False
    user_id = token.claims.get("sub")
    return isinstance(user_id, str) and user_id in allowed_ids


def allowlist_check(allowed_ids: frozenset[str]) -> "AllowlistCheck":
    """An ``AuthMiddleware`` check: the second layer behind the verifier."""
    return AllowlistCheck(allowed_ids)


@dataclass(frozen=True)
class AllowlistCheck:
    """Per-component check that the caller is a listed GitHub user.

    The verifier already refuses everyone else at the HTTP layer; this runs again
    for every tool, so a future change to how tokens are verified can't open the
    tools by accident. FastMCP skips component checks on stdio, where there is no
    sign-in.
    """

    allowed_ids: frozenset[str]

    def __call__(self, ctx: AuthContext) -> bool:
        return is_allowed(ctx.token, self.allowed_ids)


def build_auth(
    settings: AuthSettings,
    public_url: str,
    *,
    client_storage: AsyncKeyValue | None = None,
    github_http_client: httpx2.AsyncClient | None = None,
) -> OAuthProxy:
    """The OAuth proxy for HTTP mode: GitHub upstream, allowlisted verifier.

    ``client_storage`` and ``github_http_client`` exist for tests; in production
    FastMCP's encrypted disk store and a real GitHub client are used.
    """
    verifier = AllowlistGitHubTokenVerifier(
        allowed_ids=settings.allowed_ids,
        required_scopes=GITHUB_SCOPES,
        cache_ttl_seconds=VERIFY_CACHE_SECONDS,
        http_client=github_http_client,
    )
    base_url = public_url.rstrip("/")
    return OAuthProxy(
        upstream_authorization_endpoint=GITHUB_AUTHORIZE_URL,
        upstream_token_endpoint=GITHUB_TOKEN_URL,
        upstream_client_id=settings.client_id,
        upstream_client_secret=settings.client_secret,
        token_verifier=verifier,
        base_url=base_url,
        issuer_url=base_url,
        redirect_path=CALLBACK_PATH,
        allowed_client_redirect_uris=list(settings.redirect_uris),
        # An explicit key: the proxy's signing and storage keys derive from it, so
        # rotating the GitHub client secret doesn't sign Claude out. FastMCP keeps
        # registered clients in its own encrypted store on disk.
        jwt_signing_key=settings.jwt_signing_key,
        client_storage=client_storage,
        require_authorization_consent=True,
    )
