from typing import TypedDict


class WorkItem(TypedDict):
    title: str
    description: str
    link: str
    relevant_source_directories: list[str]
