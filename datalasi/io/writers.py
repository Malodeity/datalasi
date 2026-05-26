"""Contract writers — persist DataContracts to YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from datalasi.core.contract import DataContract


class YAMLWriter:
    """Write a :class:`~datalasi.core.contract.DataContract` to a YAML file."""

    @staticmethod
    def write(contract: DataContract, path: str) -> None:
        """Serialize *contract* and write it to *path*.

        Parent directories are created automatically if they don't exist.

        Args:
            contract: The contract to persist.
            path: Destination file path (e.g. ``"contracts/transactions-v1.0.0.yaml"``).
        """
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("w", encoding="utf-8") as fh:
            yaml.dump(
                contract.to_dict(),
                fh,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
