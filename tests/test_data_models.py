from data_models import WorkItem


class TestWorkItem:
    def test_create_work_item(self):
        item = WorkItem(
            title="Fix bug",
            description="A bug needs fixing",
            link="https://example.com/1",
            relevant_source_directories=["repo-a"],
        )
        assert item["title"] == "Fix bug"
        assert item["description"] == "A bug needs fixing"
        assert item["link"] == "https://example.com/1"
        assert item["relevant_source_directories"] == ["repo-a"]

    def test_work_item_is_dict(self):
        item = WorkItem(
            title="t", description="d", link="l", relevant_source_directories=[]
        )
        assert isinstance(item, dict)
