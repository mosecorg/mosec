import os
import shutil
import subprocess
from io import open

from setuptools import Extension, find_packages, setup
from setuptools.command.build_ext import build_ext as _build_ext

here = os.path.abspath(os.path.dirname(__file__))
PACKAGE_NAME = "mosec"

with open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    readme = f.read()

with open(os.path.join(here, "requirements/dev.txt"), encoding="utf-8") as f:
    dev_requirements = f.read().splitlines()

with open(os.path.join(here, "requirements/doc.txt"), encoding="utf-8") as f:
    doc_requirements = f.read().splitlines()

with open(os.path.join(here, "requirements/plugin.txt"), encoding="utf-8") as f:
    plugin_requirements = f.read().splitlines()


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

        libpath = ext.name.replace(".", os.sep)
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
    author="Keming Yang",
    author_email="kemingy94@gmail.com",
    description="Model Serving made Efficient in the Cloud.",
    long_description=readme,
    long_description_content_type="text/markdown",
    url="https://github.com/mosecorg/mosec",
    license="Apache License 2.0",
    use_scm_version=True,
    packages=find_packages(exclude=["examples*", "tests*"]),
    include_package_data=True,
    python_requires=">=3.6",
    setup_requires=["setuptools_scm>=7.0"],
    extras_require={
        "dev": dev_requirements,
        "plugin": plugin_requirements,
        "doc": doc_requirements,
    },
    zip_safe=False,
    ext_modules=ext_modules,  # type: ignore
    cmdclass=dict(build_ext=RustBuildExt),  # type: ignore
)
