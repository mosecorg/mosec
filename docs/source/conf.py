# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "mosec"
copyright = "2023, mosec maintainers"
author = "mosec maintainers"
release = "latest"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.viewcode",
    "sphinx.ext.autodoc",
    "sphinx.ext.githubpages",
    "sphinx.ext.napoleon",
    "myst_parser",
    "sphinx_copybutton",
    "sphinxcontrib.programoutput",
    "sphinx_autodoc_typehints",
    "sphinxext.opengraph",
]

templates_path = ["_templates"]
exclude_patterns = []
source_suffix = [".rst", ".md"]
master_doc = "index"
language = "en"

# Extension configuration
myst_heading_anchors = 3
autodoc_member_order = "bysource"
# https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html
napoleon_attr_annotations = True
napoleon_include_init_with_doc = True
napoleon_use_admonition_for_references = True
# https://sphinxext-opengraph.readthedocs.io/en/latest/
ogp_site_url = "https://mosecorg.github.io/mosec/"
ogp_image = "https://user-images.githubusercontent.com/38581401/134487662-49733d45-2ba0-4c19-aa07-1f43fd35c453.png"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_logo = "https://user-images.githubusercontent.com/38581401/134487662-49733d45-2ba0-4c19-aa07-1f43fd35c453.png"
html_static_path = ["_static"]
html_favicon = "https://user-images.githubusercontent.com/38581401/134798617-0104dc12-e0d4-4ed5-a79c-9e2435e99a14.png"

# Theme
html_theme_options = {
    "sidebar_hide_name": True,
    "navigation_with_keys": True,
}
