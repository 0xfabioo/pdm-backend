import subprocess
from datetime import datetime

import pytest

from pdm.pep517.metadata import Metadata
from tests import FIXTURES


def test_parse_module():
    metadata = Metadata(FIXTURES / "projects/demo-module/pyproject.toml")
    assert metadata.name == "demo-module"
    assert metadata.version == "0.1.0"
    assert metadata.author == ""
    assert metadata.author_email == "frostming <mianghong@gmail.com>"
    paths = metadata.convert_package_paths()
    assert sorted(paths["py_modules"]) == ["bar_module", "foo_module"]
    assert paths["packages"] == []
    assert paths["package_dir"] == {}


def test_parse_package():
    metadata = Metadata(FIXTURES / "projects/demo-package-include/pyproject.toml")
    paths = metadata.convert_package_paths()
    assert paths["py_modules"] == []
    assert paths["packages"] == ["my_package"]
    assert paths["package_dir"] == {}
    assert paths["package_data"] == {"": ["*"]}


def test_parse_error_package():
    metadata = Metadata(FIXTURES / "projects/demo-package-include-error/pyproject.toml")
    with pytest.raises(ValueError):
        metadata.convert_package_paths()


def test_parse_src_package():
    metadata = Metadata(FIXTURES / "projects/demo-src-package/pyproject.toml")
    paths = metadata.convert_package_paths()
    assert paths["packages"] == ["my_package"]
    assert paths["py_modules"] == []
    assert paths["package_dir"] == {"": "src"}


def test_parse_src_package_by_include():
    metadata = Metadata(FIXTURES / "projects/demo-src-package-include/pyproject.toml")
    paths = metadata.convert_package_paths()
    assert paths["package_dir"] == {"": "sub"}
    assert paths["packages"] == ["my_package"]
    assert paths["py_modules"] == []


def test_parse_package_with_extras():
    metadata = Metadata(FIXTURES / "projects/demo-combined-extras/pyproject.toml")
    assert metadata.dependencies == ["urllib3"]
    assert metadata.optional_dependencies == {
        "be": ["idna"],
        "te": ["chardet"],
        "all": ["idna", "chardet"],
    }
    assert metadata.requires_extra == {
        "be": ['idna; extra == "be"'],
        "te": ['chardet; extra == "te"'],
        "all": ['idna; extra == "all"', 'chardet; extra == "all"'],
    }


def test_project_version_use_scm(project_with_scm):
    metadata = Metadata(project_with_scm / "pyproject.toml")
    assert metadata.version == "0.1.0"
    project_with_scm.joinpath("test.txt").write_text("hello\n")
    subprocess.check_call(["git", "add", "test.txt"])
    date = datetime.utcnow().strftime("%Y%m%d")
    assert metadata.version == f"0.1.0+d{date}"
    subprocess.check_call(["git", "commit", "-m", "add test.txt"])
    assert "0.1.1.dev1+g" in metadata.version


def test_convert_legacy_project():
    metadata = Metadata(FIXTURES / "projects/demo-legacy/pyproject.toml")
    assert metadata.version == "0.1.0"
    assert metadata.dependencies == ["flask"]
    assert metadata.author == ""
    assert metadata.author_email == "frostming <mianghong@gmail.com>"
