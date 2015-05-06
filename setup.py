import os
from setuptools import setup

from acd_cli import _app_name, __version__


def read(fname: str) -> str:
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name=_app_name,
    version=__version__,
    description='a command line interface for Amazon Cloud Drive',
    long_description=read('README.rst'),
    license='GPLv2+',
    author='yadayada',
    author_email='acd_cli@mail.com',
    keywords='amazon cloud drive clouddrive',
    url='https://github.com/yadayada/acd_cli',
    zip_safe=False,
    packages=['cache', 'acd', 'utils'],
    package_data={'': ['README', '*.rst']},
    scripts=['acd_cli.py'],
    entry_points={'console_scripts': ['acd_cli = acd_cli:main', 'acdcli = acd_cli:main'],
                  # 'acd_cli.plugins': ['stream = plugins.stream',
                  # 'template = plugins.template']
                  },
    install_requires=['appdirs', 'python-dateutil', 'pycurl', 'requests>=1.0.0', 'sqlalchemy'],
    classifiers=[
        'Environment :: Console',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)'
        'Programming Language :: Python :: 3',
        'Development Status :: 3 - Alpha'
    ]
)