"""Incident adapters. No agent receives a mutating adapter."""

import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


class TicketRejected(Exception):
    """No incident was created (validated rejection before or during POST)."""


class TicketOutcomeUnknown(Exception):
    """The POST may have reached ServiceNow; do not retry automatically."""


@dataclass(frozen=True)
class Incident:
    sys_id: str
    number: str
    status: str = "created"


def _connection_settings() -> tuple[str, str, list[str]]:
    base_url = os.getenv("SERVICENOW_BASE_URL", "").rstrip("/")
    parsed = urlparse(base_url)
    path = os.getenv("SERVICENOW_INCIDENT_TABLE_PATH", "/api/now/table/incident")
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise TicketRejected("Invalid ServiceNow base URL")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise TicketRejected("Invalid ServiceNow base URL")
    if not path.startswith("/") or path.startswith("//") or ".." in path or "?" in path:
        raise TicketRejected("Invalid incident path")
    if os.getenv("SERVICENOW_AUTH_MODE") != "oauth":
        raise TicketRejected("OAuth configuration required")
    names = (
        "SERVICENOW_CLIENT_ID",
        "SERVICENOW_CLIENT_SECRET",
        "SERVICENOW_USERNAME",
        "SERVICENOW_PASSWORD",
    )
    credentials = [os.getenv(name) for name in names]
    if not all(credentials):
        raise TicketRejected("OAuth configuration incomplete")
    return base_url, path, credentials


def _oauth_token(http: httpx.Client, base_url: str, credentials: list[str]) -> str:
    try:
        token_response = http.post(
            f"{base_url}/oauth_token.do",
            data={
                "grant_type": "password",
                "client_id": credentials[0],
                "client_secret": credentials[1],
                "username": credentials[2],
                "password": credentials[3],
            },
        )
        token_response.raise_for_status()
        token = token_response.json()["access_token"]
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Invalid OAuth token")
        return token
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise TicketRejected("OAuth token unavailable") from exc


def verify_servicenow_oauth(client: httpx.Client | None = None) -> None:
    base_url, _, credentials = _connection_settings()
    if client is not None:
        _oauth_token(client, base_url, credentials)
    else:
        with httpx.Client(timeout=10, follow_redirects=False) as http:
            _oauth_token(http, base_url, credentials)


def create_incident(
    payload: dict,
    agent_run_id: str,
    mode: str | None = None,
    client: httpx.Client | None = None,
) -> Incident:
    mode = mode or os.getenv("TICKET_ADAPTER_MODE", "mock")
    if mode == "mock":
        return Incident(
            sys_id=f"mock-{agent_run_id}",
            number=f"MOCK{agent_run_id.replace('-', '')[:8].upper()}",
        )
    if mode != "servicenow":
        raise TicketRejected("Adapter mode not supported")

    base_url, path, credentials = _connection_settings()
    if set(payload) != {
        "short_description",
        "description",
        "impact",
        "urgency",
        "category",
    }:
        raise TicketRejected("Invalid incident payload")
    if not all(str(value).strip() for value in payload.values()):
        raise TicketRejected("Empty incident field")
    if str(payload["impact"]) not in ("1", "2", "3") or str(payload["urgency"]) not in (
        "1",
        "2",
        "3",
    ):
        raise TicketRejected("Invalid severity")

    def send(http: httpx.Client) -> Incident:
        token = _oauth_token(http, base_url, credentials)
        try:
            response = http.post(
                f"{base_url}{path}",
                json={
                    **payload,
                    "impact": str(payload["impact"]),
                    "urgency": str(payload["urgency"]),
                },
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError as exc:
            raise TicketOutcomeUnknown("Incident response unavailable") from exc
        if 400 <= response.status_code < 500:
            raise TicketRejected("Incident rejected by ServiceNow")
        if response.status_code >= 500:
            raise TicketOutcomeUnknown("Incident server response uncertain")
        try:
            result = response.json()["result"]
            if any(
                not isinstance(result[field], str) or not result[field].strip()
                for field in ("sys_id", "number")
            ):
                raise ValueError("Missing incident identifiers")
            return Incident(sys_id=result["sys_id"], number=result["number"])
        except (KeyError, ValueError, TypeError) as exc:
            raise TicketOutcomeUnknown("Incident confirmation unavailable") from exc

    if client is not None:
        return send(client)
    with httpx.Client(timeout=10, follow_redirects=False) as http:
        return send(http)
