"""The Entra client secret from Azure Key Vault, read with the container app's managed identity.

    ENTRA_CLIENT_SECRET_KEYVAULT_URI   https://<vault>.vault.azure.net/secrets/<name>  (no version: the current one)
    AZURE_CLIENT_ID                    the client id of the user-assigned identity the container app runs as

When the URI is set, the server reads the secret from Key Vault and ENTRA_CLIENT_SECRET is not used; when it is not
set, everything works as before (ENTRA_CLIENT_SECRET from the container app's own secret). The secret is read on the
first on-behalf-of exchange, kept in memory for an hour, and read again at once when Entra says the secret is wrong or
expired (a rotation in Key Vault takes effect without a new revision). It is never logged and never leaves memory.

Two REST calls, no Azure SDK:
  - the managed identity endpoint Container Apps puts in IDENTITY_ENDPOINT / IDENTITY_HEADER (api-version 2019-08-01,
    resource https://vault.azure.net, client_id for a user-assigned identity);
  - Key Vault "Get Secret": GET {vault}/secrets/{name}?api-version=7.4 with the token; the identity needs the role
    "Key Vault Secrets User" on the vault (RBAC) or a get-secret access policy.
docs/OPERATIONS.md has the commands that set this up (deploy/azure_containerapp.py --key-vault).
"""
from __future__ import annotations

import os
import threading
import time
from urllib.parse import urlsplit

VAULT_RESOURCE = "https://vault.azure.net"
API_VERSION = "7.4"
IDENTITY_API_VERSION = "2019-08-01"
TTL = 3600


class KeyVaultError(RuntimeError):
    """The secret could not be read from Key Vault (no identity, no access, no such secret, network)."""


def check_uri(uri: str) -> str:
    """https://<vault>.vault.azure.net/secrets/<name>[/<version>] or ValueError (raised at startup, not at a call)."""
    parts = urlsplit((uri or "").strip())
    segments = [s for s in parts.path.split("/") if s]
    if (parts.scheme != "https" or not (parts.hostname or "").endswith(".vault.azure.net") or len(segments) not in (2, 3)
            or segments[0] != "secrets" or parts.query or parts.fragment):
        raise ValueError("ENTRA_CLIENT_SECRET_KEYVAULT_URI must look like https://<vault>.vault.azure.net/secrets/<name>")
    return f"https://{parts.hostname}/{'/'.join(segments)}"


class SecretReader:
    def __init__(self, uri: str, client_id: str | None = None, get=None, clock=time.time) -> None:
        self.uri = check_uri(uri)
        self.client_id = client_id if client_id is not None else os.environ.get("AZURE_CLIENT_ID", "")
        self._get = get                                   # tests pass a fake; production uses requests.get
        self.clock = clock
        self._value: str | None = None
        self._read_at = 0.0
        self._lock = threading.Lock()

    def __repr__(self) -> str:                            # the value never appears in a repr
        return f"SecretReader({self.uri!r})"

    def _http_get(self, url: str, headers: dict, params: dict | None = None):
        if self._get is not None:
            return self._get(url, headers=headers, params=params)
        import requests
        return requests.get(url, headers=headers, params=params, timeout=10)

    def _identity_token(self) -> str:
        endpoint, header = os.environ.get("IDENTITY_ENDPOINT"), os.environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise KeyVaultError("no managed identity on this container (IDENTITY_ENDPOINT is not set)")
        params = {"resource": VAULT_RESOURCE, "api-version": IDENTITY_API_VERSION}
        if self.client_id:
            params["client_id"] = self.client_id
        r = self._http_get(endpoint, {"X-IDENTITY-HEADER": header}, params)
        if getattr(r, "status_code", 0) != 200:
            raise KeyVaultError(f"the managed identity endpoint answered HTTP {getattr(r, 'status_code', '?')}")
        token = (r.json() or {}).get("access_token")
        if not token:
            raise KeyVaultError("the managed identity endpoint answered without an access token")
        return token

    def _read(self) -> str:
        r = self._http_get(self.uri, {"Authorization": f"Bearer {self._identity_token()}"}, {"api-version": API_VERSION})
        status = getattr(r, "status_code", 0)
        if status in (401, 403):
            raise KeyVaultError(f"Key Vault refused the managed identity (HTTP {status}): it needs the role 'Key Vault Secrets User' on the vault")
        if status == 404:
            raise KeyVaultError("Key Vault has no such secret (HTTP 404)")
        if status != 200:
            raise KeyVaultError(f"Key Vault answered HTTP {status}")
        value = (r.json() or {}).get("value")
        if not isinstance(value, str) or not value:
            raise KeyVaultError("the Key Vault secret is empty")
        return value

    def get(self, refresh: bool = False) -> str:
        with self._lock:
            if refresh or self._value is None or self.clock() - self._read_at > TTL:
                try:
                    self._value, self._read_at = self._read(), self.clock()
                except KeyVaultError:
                    raise
                except Exception as e:  # noqa: BLE001 — a network failure is reported without the request's headers
                    raise KeyVaultError(f"reading the secret failed: {type(e).__name__}") from None
            return self._value


def from_env() -> SecretReader | None:
    uri = os.environ.get("ENTRA_CLIENT_SECRET_KEYVAULT_URI", "").strip()
    return SecretReader(uri) if uri else None
