"""Git-backed contract versioning using GitPython."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datalasi.core.contract import DataContract


class GitBackend:
    """Commit contract files to a Git repository and query their history.

    Requires the ``git`` optional dependency::

        pip install "datalasi[git]"

    Example::

        from datalasi.io.git_backend import GitBackend

        backend = GitBackend(".")
        sha = backend.commit_contract(contract, "contracts/orders.yaml")
        print(backend.history("contracts/orders.yaml"))
    """

    def __init__(self, repo_path: str = ".") -> None:
        try:
            from git import InvalidGitRepositoryError, Repo
        except ImportError as exc:
            raise ImportError(
                "GitBackend requires gitpython. Install with: pip install 'datalasi[git]'"
            ) from exc

        try:
            self.repo = Repo(repo_path, search_parent_directories=True)
        except InvalidGitRepositoryError:
            raise ValueError(f"Not a git repository: {repo_path}")

        self.root = Path(self.repo.working_dir)

    def commit_contract(
        self,
        contract: DataContract,
        path: str,
        message: str | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Write *contract* to *path*, stage it, and create a commit.

        Args:
            contract: The contract to persist.
            path: File path (relative to repo root, or absolute).
            message: Commit message. Defaults to a conventional-commits style
                message describing the contract name and version.
            author_name: Optional commit author name (overrides git config).
            author_email: Optional commit author email.

        Returns:
            The full SHA-1 hex string of the new commit.
        """
        from datalasi.io.writers import YAMLWriter

        abs_path = Path(path) if Path(path).is_absolute() else self.root / path
        YAMLWriter.write(contract, str(abs_path))

        rel_path = abs_path.relative_to(self.root)
        self.repo.index.add([str(rel_path)])

        if message is None:
            message = f"chore(contracts): update {contract.name} to v{contract.version}"

        commit_kwargs: dict[str, Any] = {}
        if author_name and author_email:
            from git import Actor

            commit_kwargs["author"] = Actor(author_name, author_email)

        commit = self.repo.index.commit(message, **commit_kwargs)
        return commit.hexsha

    def history(self, path: str, max_count: int = 20) -> list[dict[str, Any]]:
        """Return the commit history for the contract file at *path*.

        Each entry is a dict with keys ``sha`` (8-char short hash),
        ``message``, ``author``, and ``date`` (ISO 8601).
        """
        abs_path = Path(path) if Path(path).is_absolute() else self.root / path
        rel_path = abs_path.relative_to(self.root)

        commits = list(self.repo.iter_commits(paths=str(rel_path), max_count=max_count))
        return [
            {
                "sha": c.hexsha[:8],
                "message": c.message.strip(),
                "author": str(c.author),
                "date": c.committed_datetime.isoformat(),
            }
            for c in commits
        ]

    def get_at_commit(self, path: str, commit_sha: str) -> DataContract:
        """Load the contract file as it existed at a specific commit.

        Args:
            path: Path to the contract file (relative to repo root or absolute).
            commit_sha: Full or abbreviated commit SHA.

        Returns:
            A :class:`~datalasi.core.contract.DataContract` from that commit.
        """
        import yaml

        from datalasi.core.contract import DataContract

        abs_path = Path(path) if Path(path).is_absolute() else self.root / path
        rel_path = abs_path.relative_to(self.root)

        commit = self.repo.commit(commit_sha)
        blob = commit.tree[str(rel_path)]
        data = yaml.safe_load(blob.data_stream.read())
        return DataContract.from_dict(data)

    def __repr__(self) -> str:
        return f"GitBackend(root={self.root!r})"
