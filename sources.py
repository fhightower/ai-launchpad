from data_models import WorkItem


class BaseSource:
    def get_work_items(self) -> list[WorkItem]:
        raise NotImplementedError("This should be implemented by each child class")


SOURCES: list[BaseSource] = []
