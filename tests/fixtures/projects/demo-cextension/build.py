# build.py
from setuptools import Extension

ext_modules = [Extension("my_package.hello", ["my_package/hellomodule.c"])]


def build(setup_kwargs):
    setup_kwargs.update(ext_modules=ext_modules)