import os
import pathlib
import re
import shutil
import subprocess
from io import open
from os import path, sep

from setuptools import Extension, find_packages, setup  # type: ignore
from setuptools.command.build_ext import build_ext as _build_ext  # type: ignore

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md"), encoding="utf-8") as f:
    readme = f.read()

with open(path.join(here, "requirements.txt"), encoding="utf-8") as f:
    requires = [req.strip() for req in f if req]


def get_version():
    """Use rust package version as the single source for versioning"""
    version = (
        subprocess.check_output(["cargo", "pkgid"]).decode().strip().split("#")[-1]
    )

    version_str = '__version__ = "{}"'.format(version)

    # update py version
    init_path = pathlib.Path(here).joinpath("mosec/__init__.py")
    cont = init_path.open("r").read()
    p1 = "# do_not_modify_below\n"
    p2 = "\n# do_not_modify_above"
    cont = re.sub(
        "{}.*?{}".format(p1, p2), p1 + version_str + p2, cont, flags=re.DOTALL
    )
    init_path.write_text(cont)
    return version


class RustExtension(Extension):
    """Custom Extension class for rust"""


rust_controller_ext = RustExtension(name="mosec.bin", sources=["src/*"])


class RustBuildExt(_build_ext):
    """Custom build extension class for rust"""

    def run(self):
        for ext in self.extensions:
            self.build_extension(ext)

    def build_extension(self, ext: Extension):
        if not isinstance(ext, RustExtension):
            return super().build_extension(ext)

        libpath = ext.name.replace(".", sep)
        build_libpath = path.join(self.build_lib, libpath)
        build_cmd = [
            "cargo",
            "build",
            "--release",
            "--target-dir",
            path.join(build_libpath),
        ]
        if os.getenv("RUST_TARGET"):
            build_cmd += ["--target", os.getenv("RUST_TARGET")]

        print(f"running rust cargo package build: {build_cmd}")
        errno = subprocess.call(build_cmd)

        assert errno == 0, "Error occurred while building rust binary"

        # clean up
        if os.getenv("RUST_TARGET"):
            target_dir = path.join(build_libpath, os.getenv(
                "RUST_TARGET"), "release", "mosec")
            rm_dir = os.getenv("RUST_TARGET")
        else:
            target_dir = path.join(build_libpath, "release", "mosec")
            rm_dir = "release"
        shutil.copy(target_dir, build_libpath)
        shutil.rmtree(path.join(build_libpath, rm_dir))

        if self.inplace:
            os.makedirs(os.path.dirname(libpath), exist_ok=True)
            shutil.copy(build_libpath, libpath)


setup(
    name="mosec",
    version=get_version(),
    author="Keming Yang",
    author_email="kemingy94@gmail.com",
    description="Model Serving made Efficient in the Cloud.",
    long_description=readme,
    long_description_content_type="text/markdown",
    url="https://github.com/mosecorg/mosec",
    packages=find_packages(exclude=["examples*", "tests*"]),
    package_data={},
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
        ],
    },
    zip_safe=False,
    entry_points={
        "console_scripts": [],
    },
    ext_modules=[rust_controller_ext],
    cmdclass=dict(build_ext=RustBuildExt),
)
