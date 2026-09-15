#!/usr/bin/env python

from distutils.core import setup

setup(name='gravity_firmware',
      version='0.1',
      description='Gravity Linux firmware tools',
      author='Hector Martin',
      author_email='marcan@marcan.st',
      url='https://github.com/GravityLinux/installer/',
      packages=['gravity_firmware'],
      entry_points={"console_scripts": ["gravity-fwextract = gravity_firmware.update:main"]}
     )
