from setuptools import setup
from . import __version__


setup(name='standingsrequests',
      version=__version__,
      description='Alliance Auth compatible standings tool module for requesting alt character standings.',
      url='https://github.com/basraah/standingsrequests',
      author='Basraah',
      author_email='basraaheve@gmail.com',
      license='GPL-3.0',
      packages=['standingsrequests'],
      install_requires=[
          'future>=0.16.0',
          'requests>=2.18.4',
      ],
      zip_safe=False,
      classifiers=[
          'License :: OSI Approved :: GNU General Public License v3',
          'Natural Language :: English',
          'Programming Language :: Python :: 3.5',
          'Framework :: Django :: 1.10',
          'Framework :: Django :: 1.11',
      ],
)
