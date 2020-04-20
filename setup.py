from setuptools import setup, find_packages
from standingsrequests import __version__


setup(
    name='standingsrequests',
    version=__version__,
    description=(
        'Alliance Auth compatible standings tool module for '
        'requesting alt character standings.'
    ),
    url='https://github.com/basraah/standingsrequests',
    author='Basraah',
    author_email='basraaheve@gmail.com',
    license='GPL-3.0',
    packages=find_packages(),
    python_requires='>=3.6',
    install_requires=[
        'future>=0.16.0',
        'requests>=2.18.4',
    ],
    zip_safe=False,
    include_package_data=True,
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3',
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 2.2',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
