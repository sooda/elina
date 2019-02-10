elina the extractor
===================

A gpu register spec / memory format parser and processor for a particular hobby project.

This small tool was conceived on a certain_ rainy Sunday, hence the name.

.. _certain: https://www.nordicnames.de/wiki/Finnish_Name_Days#February

what
----

* NVIDIA Tegra GPU driver: https://nv-tegra.nvidia.com/gitweb/?p=linux-nvgpu.git
* ``$ git clone git://nv-tegra.nvidia.com/linux-nvgpu.git``
* Look in ``drivers/gpu/nvgpu/include/nvgpu/hw/<chip>``
* The provided ``rustify`` tool provides a `tock`_-ish register spec

.. _tock: https://github.com/tock/tock/tree/master/libraries/tock-register-interface

see also
--------

* envytools_ (docs_) from the cool Nouveau folks

.. _envytools: https://github.com/envytools/envytools
.. _docs: https://envytools.readthedocs.io/en/latest/hw/mmio.html
