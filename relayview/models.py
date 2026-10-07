from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Stream:
    name: str
    url: str
    group: str = ""
