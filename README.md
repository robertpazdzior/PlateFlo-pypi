# PlateFlo
Python tools for the PlateFlo perfusion tissue culture system. Simplifies
serial control of FETbox hardware controller and Ismatec peristaltic pumps.

## Installation
Using `pip` package manager:
```bash
pip install plateflo
```
or
```bash
python3 -m pip install plateflo
```

## Description
The `plateflo` package includes the following modules and sub-package:
* `fetbox` - OmniPerf FETbox serial control
* `scheduler` - Scheduling/executing system commands, e.g. valve on/off every 5 min.
* `ismatec` - Package for basic serial control of Ismatec peristaltic pumps
    * `ismatec_dig` - Reglo Digital peristaltic pump
    * `ismatec_icc` - Reglo ICC peristaltic pump
    * `ismatec_scanner` - Find connected Reglo pumps
* `serial_io` - Underlying threaded serial I/O library. Built around `pyserial`

## Documentation
* Publication [coming soon]
* PlateFlo ReadTheDocs [coming soon]

## Source
Github - https://github.com/robertpazdzior/plateflo-pypi