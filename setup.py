import os
import re
from setuptools import setup, find_packages
from distutils.version import StrictVersion
import acdcli


def read(fname: str) -> str:
    return open(os.path.join(os.path.dirname(__file__), fname), encoding='utf-8').read()

# replace GitHub external links
repl = ('`([^`]*?) <(docs/)?(.*?)\.rst>`_',
        '`\g<1> <https://acd-cli.readthedocs.org/en/latest/\g<3>.html>`_')

version = acdcli.__version__
StrictVersion(version)

dependencies = ['appdirs', 'colorama', 'fusepy', 'python_dateutil',
                'requests>=2.1.0,!=2.9.0,!=2.12.0', 'requests_toolbelt!=0.5.0']
doc_dependencies = ['sphinx_paramlinks']
test_dependencies = ['httpretty<0.8.11', 'mock']

if os.environ.get('READTHEDOCS') == 'True':
    dependencies = doc_dependencies

setup(
    name='acdcli',
    version=version,
    description='a command line interface and FUSE filesystem for Amazon Cloud Drive',
    long_description=re.sub(repl[0], repl[1], read('README.rst')),
    license='GPLv2+',
    author='yadayada',
    author_email='acd_cli@mail.com',
    keywords=['amazon cloud drive', 'clouddrive', 'FUSE'],
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
    install_requires=dependencies,
    tests_require=test_dependencies,
    extras_require={'docs': doc_dependencies},
    classifiers=[
        'Environment :: Console',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3 :: Only',
        'Development Status :: 4 - Beta',
        'Topic :: System :: Archiving :: Backup',
        'Topic :: System :: Filesystems'
    ]
)
