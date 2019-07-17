from distutils.core import setup
import os
import setuptools

dir_path = os.path.dirname(os.path.realpath(__file__))
reqs_file = 'requirements.txt'.format(dir_path)
with open(reqs_file) as f:
    required = f.read().splitlines()

setup_required = list(required)

setup(
    # Application name:
    name="restylinchpin",

    # Version number (initial):
    version="0.1.0",

    # Application author details:
    author="Mansi Kulkarni",
    author_email="mankulka@redhat.com",

    # Packages
    packages=["app"],

    # Include additional files into the package
    include_package_data=True,

    # Details
    url="http://restylinchpin.readthedocs.io/",

    setup_requires=setup_required,
    tests_require=["flake8"],

    #
    # license="LICENSE",
    description="REST application for Linchpin project",

    # long_description=open("README.txt").read(),

    # Dependent packages (distributions)
    install_requires=[
        "flask",
        "linchpin"
    ],
)

