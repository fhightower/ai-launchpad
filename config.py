import tomllib
from functools import lru_cache
from pathlib import Path


def _read_toml(path: Path) -> dict:
    with path.open("rb") as config_file:
        config = tomllib.load(config_file)
        return config


def _missing_required_fields(
    config: dict, required_fields: tuple[str, ...]
) -> list[str]:
    missing_fields = []
    for field in required_fields:
        if field not in config:
            missing_fields.append(field)
    return missing_fields


@lru_cache(maxsize=1)
def read_config() -> dict:
    config_path = Path(__file__).with_name("config.toml")
    config = _read_toml(config_path)

    if not config:
        raise ValueError(f"Config file at {config_path} is empty or invalid.")

    if missing_fields := _missing_required_fields(
        config, ("base_contexts_dir", "base_source_dir")
    ):
        raise ValueError(
            f"Config file at {config_path} is missing required fields: {', '.join(missing_fields)}",
        )

    return config
