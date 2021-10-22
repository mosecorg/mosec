import json
import os
import re
import shutil
import subprocess
from io import open
from typing import Dict

from setuptools import Extension, find_packages, setup  # type: ignore
from setuptools.command.build_ext import build_ext as _build_ext  # type: ignore

here = os.path.abspath(os.path.dirname(__file__))
META_DATA: Dict[str, str] = {}

with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    readme = f.read()


def export_meta_data():
    """Use rust cargo package as the single source for meta data"""
    meta_str = (
        subprocess.check_output(["cargo", "metadata", "--no-deps"]).decode().strip()
    )
    pkg_meta = json.loads(meta_str)["packages"][0]
    info_to_get = ["name", "authors", "version", "license", "repository", "description"]
    for k in info_to_get:
        META_DATA[k] = pkg_meta[k]

    def clean(raw_str):
        return re.sub("[<>]", "", raw_str)

    META_DATA["author"], META_DATA["author_email"] = list(
        zip(*[clean(x).split(" ") for x in META_DATA["authors"]])
    )

    # update py version file
    version_str = '__version__ = "{}"'.format(META_DATA["version"])
    with open("mosec/_version.py", "w") as f:
        f.write(f"{version_str}\n")

    print(f"python setup meta data: {META_DATA}")


class RustExtension(Extension):
    """Custom Extension class for rust"""


ext_modules = []

if os.getenv("PRODUCTION_MODE"):
    ext_modules.append(RustExtension(name="mosec.bin", sources=["src/*"]))


class RustBuildExt(_build_ext):
    """Custom build extension class for rust"""

    def run(self):
        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext: Extension):
        if not isinstance(ext, RustExtension):
            return super().build_extension(ext)

        libpath = ext.name.replace(".", os.sep)  # type: ignore
        build_libpath = os.path.join(self.build_lib, libpath)

        rust_target = os.getenv("RUST_TARGET")
        build_cmd = ["cargo", "build", "--release"]
        if rust_target is not None:
            build_cmd += ["--target", rust_target]

        print(f"running rust cargo package build: {build_cmd}")
        errno = subprocess.call(build_cmd)

        assert errno == 0, "Error occurred while building rust binary"

        # package the binary
        if rust_target is not None:
            target_dir = os.path.join(
                "target", rust_target, "release", META_DATA["name"]
            )
        else:
            target_dir = os.path.join("target", "release", META_DATA["name"])
        os.makedirs(build_libpath, exist_ok=True)
        shutil.copy(target_dir, build_libpath)

        if self.inplace:
            os.makedirs(os.path.dirname(libpath), exist_ok=True)
            shutil.copy(build_libpath, libpath)


export_meta_data()
setup(
    name=META_DATA["name"],
    version=META_DATA["version"],
    author=META_DATA["author"][0],
    author_email=META_DATA["author_email"][0],
    maintainer=META_DATA["author"][1],
    maintainer_email=META_DATA["author_email"][1],
    url=META_DATA["repository"],
    license=META_DATA["license"],
    description=META_DATA["description"],
    long_description=readme,
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=["examples*", "tests*"]),
    classifiers=[
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.6",
    extras_require={
        "dev": [
            "pytest>=6",
            "pytest-mock>=3.5",
            "mypy>=0.910",
            "flake8>=3.8",
            "black>=20.8b1",
            "isort>=5.6",
            "autoflake>=1.4",
            "msgpack>=1.0.2",
            "pre-commit>=2.15.0",
            "httpx>=0.19.0",
        ],
        "doc": [
            "mkdocstrings>=0.16.0",
            "mkdocs-material>=7.3.0",
            "mkdocs-gen-files>=0.3.3",
        ],
    },
    zip_safe=False,
    entry_points={
        "console_scripts": [],
    },
    ext_modules=ext_modules,  # type: ignore
    cmdclass=dict(build_ext=RustBuildExt),
)
