#!/usr/bin/env python

import os
import sys

import steamy

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()

packages = [
    'steamy',
]

with open('requirements.txt') as f:
    requires = f.readlines()

with open('README.md') as f:
    readme = f.read()

setup(
    name='steamy',
    version=steamy.__version__,
    description='a library for interacting with the steam API and marketplace',
    long_description=readme + '\n\n',
    author='Andrei',
    author_email='andrei.zbikowski@gmail.com',
    url='http://github.com/b1naryth1ef/steamy',
    packages=packages,
    package_data={},
    package_dir={'steamy': 'steamy'},
    include_package_data=True,
    install_requires=requires,
    license='Apache 2.0',
    zip_safe=False,
    classifiers=(
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
    ),
)
