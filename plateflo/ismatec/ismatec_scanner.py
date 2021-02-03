'''
Ismatec Scanner
===============
Scan system serial ports for connected Ismatec Reglo peristaltic pumps.

'''

import logging
from .. import serial_io as ser

isma_logger = logging.getLogger('IsmatecScanner')

def scan_for_pumps() -> list:
    '''
    Scans system serial ports for connected Ismatec Reglo peristaltic pumps.

    Returns
    -------
    list [{'pump':str, 'port':str, 'addr':int}, ...]
        One `dict` per pump detected. [{'pump':str, 'port':str, 'addr':int}, ...]
        
        `pump` : str - Pump model, 'ICC' or 'Digital'.

        `port` : str - Serial port name.

        `addr` : int - Pump internal address.
    '''
    ports = ser.list_ports()
    pumps = []
    isma_logger.info('Scanning for Ismatec pumps...')
    for port in ports:
        isma_logger.debug('Scanning %s...', port)
        ser_device = ser.SerialDevice(port=port, timeout=0.1)
        ser_device.open()
        for i in range(1, 5):
            isma_logger.debug('\tAddress %i...', i)
            rsp = ser_device.write_cmd('%i#\r' % i, EOL='\n')['resp']
            if rsp == -1:
                isma_logger.debug('\t\t...None')
                continue
            if 'ICC' in rsp:
                pumps.append({'pump': 'ICC',
                              'port': port,
                              'addr': i})
                isma_logger.info('\t\tReglo ICC detected. Port %s; Addr %i.', 
                                port, i)
            elif 'Digital' in rsp:
                pumps.append({'pump': 'Digital',
                              'port': port,
                              'addr': i})
                isma_logger.info('\t\tReglo Dig. detected. Port %s; Addr %i.', 
                                port, i)
            else:
                isma_logger.debug('\t\t...no pump detected')
        ser_device.close()
        del ser_device
    return pumps
