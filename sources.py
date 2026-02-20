from argparse import ArgumentParser, Namespace
from pathlib import Path

from data_models import WorkItem


class BaseSource:
    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        pass

    @classmethod
    def from_args(cls, args: Namespace) -> list["BaseSource"]:
        return []

    def get_work_items(self) -> list[WorkItem]:
        raise NotImplementedError("This should be implemented by each child class")


class LocalTodoFileSource(BaseSource):
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

    @classmethod
    def add_arguments(cls, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--todo-file",
            action="append",
            default=None,
            help="Path to a local TODO text file (can be repeated)",
        )

    @classmethod
    def from_args(cls, args: Namespace) -> list["BaseSource"]:
        return [cls(path) for path in (args.todo_file or [])]

    def get_work_items(self) -> list[WorkItem]:
        lines = self.file_path.read_text(encoding="utf-8").splitlines()
        work_items: list[WorkItem] = []
        for line in lines:
            if line.startswith("- "):
                title = line[2:].strip()
                if title:
                    work_items.append(
                        WorkItem(
                            title=title,
                            description="",
                            link="",
                            relevant_source_directories=[],
                        )
                    )
        return work_items


SOURCE_TYPES: list[type[BaseSource]] = [
    LocalTodoFileSource,
]
