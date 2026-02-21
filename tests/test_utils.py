import pytest

from utils import slugify


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_special_characters(self):
        assert slugify("Hello World!") == "hello-world"

    def test_multiple_spaces(self):
        assert slugify("hello   world") == "hello-world"

    def test_leading_trailing_special(self):
        assert slugify("--hello--") == "hello"

    def test_numbers_preserved(self):
        assert slugify("issue 42") == "issue-42"

    def test_already_slug(self):
        assert slugify("already-a-slug") == "already-a-slug"

    def test_uppercase(self):
        assert slugify("ALL CAPS") == "all-caps"

    def test_empty_string(self):
        assert slugify("") == ""

    def test_only_special_characters(self):
        assert slugify("!!!") == ""

    def test_mixed(self):
        assert slugify("octocat/Hello-World#42: Fix the bug!") == "octocat-hello-world-42-fix-the-bug"
