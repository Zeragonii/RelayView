from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Stream:
    name: str
    url: str
    group: str = ""
    favorite: bool = False
    notes: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
