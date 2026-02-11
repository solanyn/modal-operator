import os
from dataclasses import dataclass, field


@dataclass
class OperatorConfig:
    modal_token_id: str = ""
    modal_token_secret: str = ""
    watch_namespaces: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "OperatorConfig":
        return cls(
            modal_token_id=os.environ.get("MODAL_TOKEN_ID", ""),
            modal_token_secret=os.environ.get("MODAL_TOKEN_SECRET", ""),
            watch_namespaces=[ns.strip() for ns in os.getenv("WATCH_NAMESPACES", "").split(",") if ns.strip()],
        )
