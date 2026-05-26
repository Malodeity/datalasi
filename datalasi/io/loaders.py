"""Contract loaders — read DataContracts from YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from datalasi.core.contract import DataContract


class YAMLLoader:
    """Load a :class:`~datalasi.core.contract.DataContract` from a YAML file."""

    @staticmethod
    def load(path: str) -> "DataContract":
        """Parse *path* as YAML and return the deserialized contract.

        Args:
            path: Path to a ``.yaml`` contract file.

        Returns:
            A fully-populated :class:`~datalasi.core.contract.DataContract`.

        Raises:
            FileNotFoundError: if *path* does not exist.
            ContractLoadError: if the YAML is malformed or missing required keys.
        """
        from datalasi.core.contract import DataContract
        from datalasi.errors import ContractLoadError

        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Contract file not found: {path}")

        try:
            with file_path.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ContractLoadError(f"Failed to parse YAML at {path}: {exc}") from exc

        if not isinstance(raw, dict):
            raise ContractLoadError(
                f"Expected a YAML mapping at the top level of {path}, got {type(raw).__name__}"
            )

        try:
            return DataContract.from_dict(raw)
        except (KeyError, ValueError, TypeError) as exc:
            raise ContractLoadError(
                f"Contract at {path} has invalid structure: {exc}"
            ) from exc
