from __future__ import annotations

import glob
import os
import sys
from pathlib import Path
from typing import Any, TypeVar

from pdm.backend._vendor import tomli_w
from pdm.backend._vendor.pyproject_metadata import StandardMetadata
from pdm.backend._vendor.validate_pyproject import api, errors
from pdm.backend.exceptions import ConfigError, ValidationError
from pdm.backend.structures import Table
from pdm.backend.utils import find_packages_iter

if sys.version_info >= (3, 11):
    import tomllib
else:
    import pdm.backend._vendor.tomli as tomllib

T = TypeVar("T")


class Config:
    """The project config object for pdm backend."""

    def __init__(self, root: Path, data: dict[str, Any]) -> None:
        self.validate(data)
        self.root = root
        self.data = data
        self.metadata = Metadata(data["project"])
        self.build_config = BuildConfig(
            root, data.setdefault("tool", {}).get("pdm", {}).get("build", {})
        )

    def as_standard_metadata(self) -> StandardMetadata:
        """Return the metadata as a StandardMetadata object."""
        return StandardMetadata.from_pyproject(self.data, project_dir=self.root)

    @staticmethod
    def validate(data: dict[str, Any]) -> None:
        """Validate the pyproject.toml data."""
        validator = api.Validator()
        try:
            validator(data)
        except errors.ValidationError as e:
            raise ValidationError(e.summary, e.details) from e

    @classmethod
    def from_pyproject(cls, root: str | Path) -> Config:
        """Load the pyproject.toml file from the given project root."""
        root = Path(root)
        pyproject = root / "pyproject.toml"
        if not pyproject.exists():
            raise ConfigError("pyproject.toml not found")
        with pyproject.open("rb") as fp:
            try:
                data = tomllib.load(fp)
            except tomllib.TOMLDecodeError as e:
                raise ConfigError(f"Invalid pyproject.toml file: {e}") from e
        return cls(root, data)

    def write_to(self, path: str | Path) -> None:
        """Write the pyproject.toml file to the given path."""
        with open(path, "wb") as fp:
            tomli_w.dump(self.data, fp)

    def convert_package_paths(self) -> dict[str, list | dict]:
        """Return a {package_dir, packages, package_data, exclude_package_data} dict."""
        packages = []
        py_modules = []
        package_data = {"": ["*"]}
        exclude_package_data: dict[str, list[str]] = {}
        package_dir = self.build_config.package_dir
        includes = self.build_config.includes
        excludes = self.build_config.excludes

        src_dir = Path(package_dir or ".")
        if not includes:
            packages = list(
                find_packages_iter(
                    package_dir or ".",
                    exclude=["tests", "tests.*"],
                    src=str(src_dir),
                )
            )
            if not packages:
                py_modules = [path.name[:-3] for path in src_dir.glob("*.py")]
        else:
            packages_set = set()
            includes = includes[:]
            for include in includes[:]:
                if include.replace("\\", "/").endswith("/*"):
                    include = include[:-2]
                if "*" not in include and os.path.isdir(include):
                    dir_name = include.rstrip("/\\")
                    temp = list(find_packages_iter(dir_name, src=package_dir or "."))
                    if os.path.isfile(os.path.join(dir_name, "__init__.py")):
                        temp.insert(0, dir_name)
                    packages_set.update(temp)
                    includes.remove(include)
            packages[:] = list(packages_set)
            for include in includes:
                for path in glob.glob(include, recursive=True):
                    if "/" not in path.lstrip("./") and path.endswith(".py"):
                        # Only include top level py modules
                        py_modules.append(path.lstrip("./")[:-3])
                if include.endswith(".py"):
                    continue
                for package in packages:
                    relpath = os.path.relpath(include, package)
                    if not relpath.startswith(".."):
                        package_data.setdefault(package, []).append(relpath)
            for exclude in excludes:
                for package in packages:
                    relpath = os.path.relpath(exclude, package)
                    if not relpath.startswith(".."):
                        exclude_package_data.setdefault(package, []).append(relpath)
        if packages and py_modules:
            raise ConfigError("Can't specify packages and py_modules at the same time.")
        return {
            "package_dir": {"": package_dir} if package_dir else {},
            "packages": packages,
            "py_modules": py_modules,
            "package_data": package_data,
            "exclude_package_data": exclude_package_data,
        }


class Metadata(Table):
    @property
    def readme_file(self) -> str | None:
        readme = self.get("readme")
        if not readme:
            return None
        if isinstance(readme, str):
            return readme
        if isinstance(readme, dict) and "file" in readme:
            return readme["file"]
        return None

    @property
    def license_files(self) -> dict[str, list[str]]:
        subtable_files = None
        if (
            "license" in self
            and isinstance(self["license"], dict)
            and "files" in self["license"]
        ):
            subtable_files = self["license"]["files"]
        if "license-files" not in self:
            if subtable_files is not None:
                return {"paths": [self["license"]["file"]]}
            return {
                "globs": [
                    "LICENSES/*",
                    "LICEN[CS]E*",
                    "COPYING*",
                    "NOTICE*",
                    "AUTHORS*",
                ]
            }
        if subtable_files is not None:
            raise ValidationError(
                "license-files",
                "Can't specify both 'license.files' and 'license-files' fields",
            )
        rv = self["license-files"]
        valid_keys = {"globs", "paths"} & set(rv)
        if len(valid_keys) == 2:
            raise ValidationError(
                "license-files", "Can't specify both 'paths' and 'globs'"
            )
        if not valid_keys:
            raise ValidationError("license-files", "Must specify 'paths' or 'globs'")
        return rv

    @property
    def entry_points(self) -> dict[str, dict[str, str]]:
        pass


class BuildConfig(Table):
    """The [tool.pdm] table"""

    def __init__(self, root: Path, data: dict[str, Any]) -> None:
        self.root = root
        super().__init__(data)

    @property
    def custom_hook(self) -> str | None:
        script = self.get("custom-hook", "pdm_build.py")
        if (self.root / script).exists():
            return script
        return None

    @property
    def includes(self) -> list[str]:
        return self.get("includes", [])

    @property
    def source_includes(self) -> list[str]:
        return self.get("source-includes", [])

    @property
    def excludes(self) -> list[str]:
        return self.get("excludes", [])

    @property
    def run_setuptools(self) -> bool:
        return self.get("run-setuptools", False)

    @property
    def package_dir(self) -> str:
        """A directory that will be used to looking for packages."""
        default = "src" if self.root.joinpath("src").exists() else ""
        return self.get("package-dir", default)

    @property
    def is_purelib(self) -> bool:
        """If not explicitly set, the project is considered to be non-pure
        if `build` exists.
        """
        return self.get("is-purelib", not bool(self.run_setuptools))

    @property
    def editable_backend(self) -> str:
        """Currently only two backends are supported:
        - editables: Proxy modules via editables
        - path: the legacy .pth file method(default)
        """
        return self.get("editable-backend", "path")