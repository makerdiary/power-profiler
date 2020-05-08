# -*- coding: utf-8 -*-

from setuptools import setup


with open('README.md') as f:
    long_description = f.read()

requirements = []

setup_requirements = ['wheel']


setup(name='power-profiler',
      version='0.0.1',
      description='',
      long_description=long_description,
      long_description_content_type='text/markdown',
      author='Yihui Xiong',
      author_email='yihui.xiong@hotmail.com',
      url='https://github.com/makerdiary/power-profiler',
      entry_points={
          'console_scripts': [
              'power-profiler=power_profiler.power_profiler:main'
          ],
      },
      packages=['power_profiler'],
      include_package_data=True,
      install_requires=requirements,
      zip_safe=True)
