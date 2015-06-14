import os
import re
from setuptools import setup, find_packages
from distutils.version import StrictVersion


def read(fname: str) -> str:
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()


version = re.search(r'^__version__\s*=\s*[\'"]([^\'"]*)[\'"]',
                    read('acd_cli.py'), re.MULTILINE).group(1)
StrictVersion(version)

setup(
    name='acdcli',
    version=version,
    description='a command line interface for Amazon Cloud Drive',
    long_description=read('README.rst').replace('✅', '✓'),
    license='GPLv2+',
    author='yadayada',
    author_email='acd_cli@mail.com',
    keywords='amazon cloud drive clouddrive',
    url='https://github.com/yadayada/acd_cli',
    download_url='https://github.com/yadayada/acd_cli/tarball/' + version,
    zip_safe=False,
    packages=find_packages(exclude=['tests']),
    test_suite='tests.get_suite',
    scripts=['acd_cli.py'],
    entry_points={'console_scripts': ['acd_cli = acd_cli:main', 'acdcli = acd_cli:main'],
                  # 'acd_cli.plugins': ['stream = plugins.stream',
                  # 'template = plugins.template']
                  },
    install_requires=['appdirs', 'python_dateutil', 'requests>=2.1.0', 'requests_toolbelt',
                      'sqlalchemy'],
    tests_require=['httpretty', 'mock'],
    classifiers=[
        'Environment :: Console',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3 :: Only',
        'Development Status :: 4 - Beta',
        'Topic :: System :: Archiving :: Backup',
        'Topic :: System :: Filesystems'
    ]
)
