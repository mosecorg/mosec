import os
import shutil
import subprocess
from io import open

from setuptools import Extension, find_packages, setup  # type: ignore
from setuptools.command.build_ext import build_ext as _build_ext  # type: ignore

here = os.path.abspath(os.path.dirname(__file__))
PACKAGE_NAME = "mosec"

with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    readme = f.read()

with open(os.path.join(here, "requirements.txt"), encoding="utf-8") as f:
    requires = [req.strip() for req in f if req]


def get_version():
    """Use rust package version as the single source for versioning"""
    version = (
        subprocess.check_output(["cargo", "pkgid"]).decode().strip().split("#")[-1]
    )

    version_str = '__version__ = "{}"'.format(version)

    # update py version
    with open("mosec/_version.py", "w") as f:
        f.write(f"{version_str}\n")
    return version


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
            target_dir = os.path.join("target", rust_target, "release", PACKAGE_NAME)
        else:
            target_dir = os.path.join("target", "release", PACKAGE_NAME)
        os.makedirs(build_libpath, exist_ok=True)
        shutil.copy(target_dir, build_libpath)

        if self.inplace:
            os.makedirs(os.path.dirname(libpath), exist_ok=True)
            shutil.copy(build_libpath, libpath)


setup(
    name=PACKAGE_NAME,
    version=get_version(),
    author="Keming Yang",
    author_email="kemingy94@gmail.com",
    description="Model Serving made Efficient in the Cloud.",
    long_description=readme,
    long_description_content_type="text/markdown",
    url="https://github.com/mosecorg/mosec",
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
    install_requires=requires,
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
