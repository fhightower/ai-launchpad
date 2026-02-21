import pytest
from pathlib import Path
from unittest.mock import patch

from config import _read_toml, _missing_required_fields, read_config


class TestReadToml:
    def test_reads_valid_toml(self, tmp_path):
        toml_file = tmp_path / "test.toml"
        toml_file.write_text('[section]\nkey = "value"\n')
        result = _read_toml(toml_file)
        assert result == {"section": {"key": "value"}}

    def test_empty_toml(self, tmp_path):
        toml_file = tmp_path / "empty.toml"
        toml_file.write_text("")
        result = _read_toml(toml_file)
        assert result == {}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _read_toml(tmp_path / "nonexistent.toml")


class TestMissingRequiredFields:
    def test_no_missing_fields(self):
        config = {"a": 1, "b": 2}
        assert _missing_required_fields(config, ("a", "b")) == []

    def test_all_missing(self):
        assert _missing_required_fields({}, ("a", "b")) == ["a", "b"]

    def test_partial_missing(self):
        config = {"a": 1}
        assert _missing_required_fields(config, ("a", "b")) == ["b"]

    def test_empty_required(self):
        assert _missing_required_fields({"a": 1}, ()) == []


class TestReadConfig:
    def setup_method(self):
        read_config.cache_clear()

    def test_valid_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'base_contexts_dir = "/tmp/ctx"\nbase_source_dir = "/tmp/src"\n'
        )
        with patch("config.Path") as mock_path_cls:
            # Path(__file__) is called, then .with_name("config.toml")
            mock_path_cls.return_value.with_name.return_value = config_file
            result = read_config()
        assert result["base_contexts_dir"] == "/tmp/ctx"
        assert result["base_source_dir"] == "/tmp/src"

    def test_empty_config_raises(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        with patch("config.Path") as mock_path_cls:
            mock_path_cls.return_value.with_name.return_value = config_file
            with pytest.raises(ValueError, match="empty or invalid"):
                read_config()

    def test_missing_required_fields_raises(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('base_contexts_dir = "/tmp/ctx"\n')
        with patch("config.Path") as mock_path_cls:
            mock_path_cls.return_value.with_name.return_value = config_file
            with pytest.raises(ValueError, match="base_source_dir"):
                read_config()
