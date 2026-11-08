"""Conexão com o Neo4j do projeto. Recusa a porta 7687, que nesta máquina é de outro container."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlsplit

from neo4j import GraphDatabase, ManagedTransaction, NotificationMinimumSeverity
from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_PORT = 7687
DEFAULT_BOLT_PORT = 7687


class UnsafeTarget(RuntimeError):
    """O alvo pode ser um banco que não é do projeto. Nada é lido nem gravado."""


class GraphUnavailable(RuntimeError):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def refuse_user_instance(uri: str) -> None:
    port = urlsplit(uri).port or DEFAULT_BOLT_PORT
    if port == FORBIDDEN_PORT:
        raise UnsafeTarget(
            f"{uri} usa a porta {FORBIDDEN_PORT}, do container jota-context-neo4j. "
            "Use o Neo4j do projeto (NEO4J_URI no .env, porta 17687 nesta máquina)."
        )


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str = "neo4j"

    @classmethod
    def from_env(cls, env_file: Path = ROOT / ".env") -> Self:
        """Variáveis de ambiente valem sobre o .env."""
        values = {**read_env_file(env_file), **os.environ}
        missing = [k for k in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD") if not values.get(k)]
        if missing:
            raise GraphUnavailable(f"faltam {', '.join(missing)} no ambiente ou em {env_file}")
        return cls(values["NEO4J_URI"], values["NEO4J_USER"], values["NEO4J_PASSWORD"],
                   values.get("NEO4J_DATABASE") or "neo4j")


class Graph:
    """Toda leitura e escrita do pacote passa por aqui, então a recusa da porta vale para tudo."""

    def __init__(self, settings: Neo4jSettings):
        refuse_user_instance(settings.uri)
        self.settings = settings
        self._driver = GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password),
                                            notifications_min_severity=NotificationMinimumSeverity.OFF)
        try:
            self._driver.verify_connectivity()
            port = self._driver.get_server_info().address.port
            if port == FORBIDDEN_PORT:
                raise UnsafeTarget(f"o servidor respondeu pela porta {FORBIDDEN_PORT}")
        except (ServiceUnavailable, AuthError, OSError) as error:
            self._driver.close()
            raise GraphUnavailable(f"Neo4j inacessível em {settings.uri}: {error}") from None
        except ClientError as error:
            self._driver.close()
            if error.code and error.code.endswith("AuthenticationRateLimit"):
                raise GraphUnavailable(
                    f"Neo4j em {settings.uri} bloqueou a autenticação por excesso de senhas erradas. "
                    "Espere um minuto sem tentar e confira a senha do .env."
                ) from None
            raise
        except BaseException:
            self._driver.close()
            raise

    def read(self, work: Callable[[ManagedTransaction], Any]) -> Any:
        with self._driver.session(database=self.settings.database) as session:
            return session.execute_read(work)

    def write(self, work: Callable[[ManagedTransaction], Any]) -> Any:
        with self._driver.session(database=self.settings.database) as session:
            return session.execute_write(work)

    def rows(self, query: str, **params: Any) -> list[dict]:
        return self.read(lambda tx: rows(tx, query, **params))

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def rows(tx: ManagedTransaction, query: str, **params: Any) -> list[dict]:
    return [record.data() for record in tx.run(query, params)]
