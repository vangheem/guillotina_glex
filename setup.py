from setuptools import find_packages
from setuptools import setup


try:
    README = open('README.rst').read()
except IOError:
    README = None

setup(
    name='guillotina_glex',
    version="1.0.0",
    description='Cloud video streaming',
    long_description=README,
    install_requires=[
        'guillotina',
        'guillotina_gcloudstorage',
        'lru-dict'
    ],
    author='Nathan Van Gheem',
    author_email='vangheem@gmail.com',
    url='',
    packages=find_packages(exclude=['demo']),
    include_package_data=True,
    tests_require=[
        'pytest',
    ],
    extras_require={
        'test': [
            'pytest'
        ]
    },
    classifiers=[],
    entry_points={
    }
)
