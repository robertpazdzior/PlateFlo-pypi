# PlateFlo
Python tools for the PlateFlo perfusion tissue culture system. Simplifies
serial control of FETbox hardware controller and Ismatec peristaltic pumps.

See [publication DOI] for more details.

## Modules
The `plateflo` package includes the following modules and sub-package:
* `fetbox` - OmniPerf FETbox serial control
* `scheduler` - Scheduling/executing system commands, e.g. valve on/off
* Ismatec - Package for basic serial control of Ismatec peristaltic pumps
    * `ismatec_dig` - Reglo Digital peristaltic pump
    * `ismatec_icc` - Reglo ICC peristaltic pump
* `serial_io` - Underlying threaded serial I/O library. Built around `pyserial`

## Documentation
[ReadTheDocs](URL) for installation, usage guide, full API, and examples.

## Source
Github - https://github.com/robertpazdzior/plateflo-pypi
