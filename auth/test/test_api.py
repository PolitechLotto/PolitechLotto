import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest

from auth.connectors import get_broker, get_database
from auth.connectors.models import UserRole, UserStatus
from auth.handlers.security import hash_refresh_token
from auth.main import create_sub_app
from auth.routers.api_v1 import router
from auth.settings import get_settings

from .conftest import (
    ADMIN_ID,
    PASSWORD,
    TEST_SETTINGS,
    USER_ID,
    FakeBroker,
    FakeDatabase,
    make_user,
)

USER_KEYS = {
    "id",
    "email",
    "username",
    "role",
    "created_at",
    "last_login_at",
    "last_seen_at",
    "is_online",
    "deleted_at",
}
ADMIN_HEADERS = {"X-User-Id": str(ADMIN_ID), "X-User-Roles": "admin"}
PLAYER_HEADERS = {"X-User-Id": str(USER_ID), "X-User-Roles": "player"}


@pytest.fixture
async def client(
    fake_db: FakeDatabase, fake_broker: FakeBroker
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_sub_app(title="API", routers=[router])
    app.dependency_overrides[get_database] = lambda: fake_db
    app.dependency_overrides[get_broker] = lambda: fake_broker
    app.dependency_overrides[get_settings] = lambda: TEST_SETTINGS
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


# POST /v1/users


async def test_register_creates_player(
    client: httpx.AsyncClient, fake_db: FakeDatabase, fake_broker: FakeBroker
) -> None:
    response = await client.post(
        "/v1/users",
        json={"email": " Nowy@Example.com ", "username": "nowy", "password": PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == USER_KEYS
    assert body["email"] == "nowy@example.com"
    assert body["username"] == "nowy"
    assert body["role"] == "player"
    assert body["is_online"] is False
    assert "password" not in response.text
    assert [event for event, _ in fake_broker.published] == ["user.created"]
    assert uuid.UUID(body["id"]) in fake_db.users


@pytest.mark.parametrize(
    ("email", "username", "expected"),
    [
        ("gracz@example.com", "inny", "Email is already registered."),
        ("inny@example.com", "GRACZ", "Username is already taken."),
    ],
)
async def test_register_rejects_taken_email_or_username(
    client: httpx.AsyncClient,
    fake_db: FakeDatabase,
    email: str,
    username: str,
    expected: str,
) -> None:
    fake_db.users[USER_ID] = make_user()

    response = await client.post(
        "/v1/users",
        json={"email": email, "username": username, "password": PASSWORD},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": expected}


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "username": "nowy", "password": PASSWORD},
        {"email": "a@b.pl", "username": "ab", "password": PASSWORD},
        {"email": "a@b.pl", "username": "spacja w nazwie", "password": PASSWORD},
        {"email": "a@b.pl", "username": "x" * 33, "password": PASSWORD},
        {"email": "a@b.pl", "username": "nowy", "password": "short"},
        {"email": "a@b.pl", "username": "nowy"},
    ],
)
async def test_register_validates_body(
    client: httpx.AsyncClient, fake_db: FakeDatabase, body: dict[str, str]
) -> None:
    response = await client.post("/v1/users", json=body)

    assert response.status_code == 422
    assert fake_db.users == {}


# POST /v1/token


@pytest.mark.parametrize("login", ["gracz", "GRACZ", "gracz@example.com"])
async def test_login_returns_token_pair(
    client: httpx.AsyncClient, fake_db: FakeDatabase, login: str
) -> None:
    fake_db.users[USER_ID] = make_user()

    response = await client.post(
        "/v1/token", json={"login": login, "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["refresh_expires_in"] == 30 * 24 * 60 * 60
    claims = jwt.decode(
        body["access_token"], TEST_SETTINGS.jwt_secret, algorithms=["HS256"]
    )
    assert claims["sub"] == str(USER_ID)
    assert claims["role"] == "player"
    assert hash_refresh_token(body["refresh_token"]) in fake_db.tokens
    assert fake_db.users[USER_ID].last_login_at is not None


@pytest.mark.parametrize(
    "body",
    [
        {"login": "gracz", "password": "wrong-password"},
        {"login": "nobody", "password": PASSWORD},
    ],
)
async def test_login_rejects_invalid_credentials(
    client: httpx.AsyncClient, fake_db: FakeDatabase, body: dict[str, str]
) -> None:
    fake_db.users[USER_ID] = make_user()

    response = await client.post("/v1/token", json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid login or password."}
    assert fake_db.tokens == {}


# POST /v1/token:refresh


async def test_refresh_rotates_refresh_token(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user()
    fake_db.add_token(hash_refresh_token("old-token"))

    response = await client.post(
        "/v1/token:refresh", json={"refresh_token": "old-token"}
    )

    assert response.status_code == 200
    new_token = response.json()["refresh_token"]
    assert new_token != "old-token"
    assert fake_db.tokens[hash_refresh_token("old-token")].revoked_at is not None
    assert fake_db.tokens[hash_refresh_token(new_token)].revoked_at is None

    reused = await client.post("/v1/token:refresh", json={"refresh_token": "old-token"})
    assert reused.status_code == 401


async def test_refresh_rejects_expired_token(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user()
    fake_db.add_token(
        hash_refresh_token("expired"),
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    response = await client.post("/v1/token:refresh", json={"refresh_token": "expired"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Refresh token is invalid or expired."}


# POST /v1/token:revoke


async def test_revoke_revokes_refresh_token(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.add_token(hash_refresh_token("token"))

    response = await client.post("/v1/token:revoke", json={"refresh_token": "token"})

    assert response.status_code == 204
    assert response.content == b""
    assert fake_db.tokens[hash_refresh_token("token")].revoked_at is not None


async def test_revoke_of_unknown_token_succeeds(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/token:revoke", json={"refresh_token": "nope"})

    assert response.status_code == 204


# GET /v1/users/me


async def test_me_returns_current_user_and_marks_them_online(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user()

    response = await client.get("/v1/users/me", headers=PLAYER_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(USER_ID)
    assert body["is_online"] is True
    assert ("touch_last_seen", USER_ID) in fake_db.calls


@pytest.mark.parametrize("headers", [{}, {"X-User-Id": "not-a-uuid"}])
async def test_me_requires_identity(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/v1/users/me", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


async def test_me_returns_404_for_deleted_user(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user(deleted_at=datetime.now(UTC))

    response = await client.get("/v1/users/me", headers=PLAYER_HEADERS)

    assert response.status_code == 404


# Admin endpoints


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", "/v1/users"),
        ("GET", f"/v1/users:batchGet?ids={USER_ID}"),
        ("GET", f"/v1/users/{USER_ID}"),
        ("DELETE", f"/v1/users/{USER_ID}"),
    ],
)
async def test_admin_endpoints_require_admin(
    client: httpx.AsyncClient, method: str, url: str
) -> None:
    anonymous = await client.request(method, url)
    player = await client.request(method, url, headers=PLAYER_HEADERS)

    assert anonymous.status_code == 401
    assert player.status_code == 403
    assert player.json() == {"detail": "Admin role required."}


async def test_admin_role_is_also_read_from_x_user_role(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        "/v1/users", headers={"X-User-Id": str(ADMIN_ID), "X-User-Role": "admin"}
    )

    assert response.status_code == 200


# GET /v1/users


async def test_list_users_returns_page(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user(last_seen_at=datetime.now(UTC))

    response = await client.get("/v1/users", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert set(body["items"][0]) == USER_KEYS
    assert body["items"][0]["is_online"] is True


async def test_list_users_parses_query(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    response = await client.get(
        "/v1/users",
        params={"status": "offline", "limit": 200, "offset": 5},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    [(name, (status, _, limit, offset))] = fake_db.calls
    assert name == "list_users"
    assert (status, limit, offset) == (UserStatus.OFFLINE, 200, 5)


@pytest.mark.parametrize(
    "params", [{"status": "away"}, {"limit": 0}, {"limit": 201}, {"offset": -1}]
)
async def test_list_users_rejects_invalid_query(
    client: httpx.AsyncClient, fake_db: FakeDatabase, params: dict[str, str | int]
) -> None:
    response = await client.get("/v1/users", params=params, headers=ADMIN_HEADERS)

    assert response.status_code == 422
    assert fake_db.calls == []


# GET /v1/users:batchGet


async def test_batch_get_returns_known_users(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user()
    unknown = uuid.uuid4()

    response = await client.get(
        "/v1/users:batchGet",
        params=[("ids", str(USER_ID)), ("ids", str(unknown)), ("ids", str(USER_ID))],
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert [user["id"] for user in response.json()["items"]] == [str(USER_ID)]
    assert fake_db.calls == [("get_users", [USER_ID, unknown])]


@pytest.mark.parametrize(
    "params",
    [
        [],
        [("ids", "not-a-uuid")],
        [("ids", str(uuid.uuid4())) for _ in range(101)],
    ],
)
async def test_batch_get_validates_ids(
    client: httpx.AsyncClient, params: list[tuple[str, Any]]
) -> None:
    response = await client.get(
        "/v1/users:batchGet", params=params, headers=ADMIN_HEADERS
    )

    assert response.status_code == 422


# GET /v1/users/{user_id}


async def test_get_user_returns_user(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user(role=UserRole.ADMIN)

    response = await client.get(f"/v1/users/{USER_ID}", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_get_user_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/v1/users/{uuid.uuid4()}", headers=ADMIN_HEADERS)

    assert response.status_code == 404
    assert response.json() == {"detail": "User not found."}


async def test_get_user_rejects_invalid_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/users/abc", headers=ADMIN_HEADERS)

    assert response.status_code == 422


# DELETE /v1/users/{user_id}


async def test_delete_user_anonymizes_and_logs_out(
    client: httpx.AsyncClient, fake_db: FakeDatabase, fake_broker: FakeBroker
) -> None:
    fake_db.users[USER_ID] = make_user()
    fake_db.add_token(hash_refresh_token("token"))

    response = await client.delete(f"/v1/users/{USER_ID}", headers=ADMIN_HEADERS)

    assert response.status_code == 204
    user = fake_db.users[USER_ID]
    assert user.deleted_at is not None
    assert "gracz" not in user.email
    assert user.password_hash == ""
    assert fake_db.tokens[hash_refresh_token("token")].revoked_at is not None
    assert fake_broker.published[0][0] == "user.deleted"

    login = await client.post(
        "/v1/token", json={"login": "gracz", "password": PASSWORD}
    )
    assert login.status_code == 401


async def test_delete_user_returns_404_for_unknown_or_deleted_user(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[USER_ID] = make_user(deleted_at=datetime.now(UTC))

    deleted = await client.delete(f"/v1/users/{USER_ID}", headers=ADMIN_HEADERS)
    unknown = await client.delete(f"/v1/users/{uuid.uuid4()}", headers=ADMIN_HEADERS)

    assert deleted.status_code == 404
    assert unknown.status_code == 404


async def test_admin_cannot_delete_themselves(
    client: httpx.AsyncClient, fake_db: FakeDatabase
) -> None:
    fake_db.users[ADMIN_ID] = make_user(id=ADMIN_ID, role=UserRole.ADMIN)

    response = await client.delete(f"/v1/users/{ADMIN_ID}", headers=ADMIN_HEADERS)

    assert response.status_code == 409
    assert fake_db.users[ADMIN_ID].deleted_at is None
