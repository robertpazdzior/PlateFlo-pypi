'''
PlateFlo FETbox Serial Control
==============================
Serial control of PlateFlo FETbox hardware controllers.

Copyright Robert Pazdzior 2020-2021

This file may be distributed under the terms of the GNU GPLv3+ license.
'''
import logging
from . import serial_io as ser

fetbox_logger = logging.getLogger('FETbox')

CMDS = {
    'get_id':       '@#\n',         # FETbox ID inquiry
    'heartbeat':    '@?\n',         # Always returns '*\r'
    'enable':       '@H%i\n',       # Enable channel i
    'disable':      '@I%i\n',       # Disable channel i
    'pwm':          '@S%i%s\n',     # PWM output channel i
    'hithold':      '@V%i%s\n',     # Hit and hold channel i
    'digread':      '@D%02i\n',     # Digital read pin i
    'digwrite':     '@E%02i%i\n',   # digitalWrite pin i
    'anaread':      '@A%02i\n',     # Analog read pin i
    'anawrite':     '@B%02i%03i\n'  # analogWrite pin i
}

def scan_for_fetbox(baud:int = 115200) -> list:
    '''
    Scans serial ports for any connected PlateFlo FETbox controllers.

    Parameters
    ---------
    baud : int, default=115200
        Serial baud rate.

    Returns
    -------
    list
        One dict per FETbox containing `port` (str) and `id` (int).
        Empty if none detected.
    '''
    mod_port = None
    mod_id = None
    ports = ser.list_ports()
    controllers = []
    fetbox_logger.info('Scanning for connected FETbox(es)...')
    for port in ports:
        fetbox_logger.debug('Scanning %s...', port)
        ser_device = ser.SerialDevice(port=port, timeout=0.1, baud=baud)
        ser_device.ser.dtr = False
        ser_device.open()
        rsp = ser_device.write_cmd(CMDS['get_id'], EOL='\n')['resp']
        try:
            if 'fetbox' in rsp:
                mod_id = int(rsp[6:])
                fetbox_logger.info("\t\tFETbox (ID %i) detected.", 
                    mod_id)
                mod_port = port
                controllers.append({'port':mod_port, 'id':mod_id})
            else:
                fetbox_logger.info("\t\t...not detected")
        finally:
            ser_device.close()
            del ser_device
    return controllers

def auto_connect_fetbox(baud:int = 115200) -> dict:
    '''
    Automatically connect to FETbox(es).

    Parameters
    ---------
    baud : int, default=115200
        Serial baud rate.

    Returns
    -------
    dict
        FETbox objects keyed by respective IDs

    Raises
    ------
    ConnectionError
        No connected FETbox detected
        
        Non-unique FETbox device IDs detected
    '''
    fetboxes = {}
    used_ids = []
    scan_result = scan_for_fetbox(baud)
    if not scan_result: raise ConnectionError('No connected FETboxes detected.')

    for box in scan_result:
        if box['id'] in used_ids:
            raise ConnectionError(('Multiple FETboxes detected with identical ' 
                                    'IDs. Change ID in firmware and reupload.'))

        _fetbox = {box['id'] : FETbox(box['port'], baud)}
        fetboxes.update(_fetbox)

    return fetboxes

class FETbox(object):
    '''
    FETbox serial control.

    Parameters
    ----------
    port : str
        Serial port name (e.g. 'COM3').
    baud : int, default=115200
        Serial baud rate (e.g. 9600).

    Returns
    -------
    FETbox object

    Attributes
    ----------
    mod_ser : Serial
        Backend PySerial `serial` object
    port : str
        Serial port name
    id : int
        Module ID number
    pin_table: dict
        Analog pin name to pin number mapping.

    Raises
    ------
    ValueError
        provided serial port is not connected to a FETbox device.
    '''
    def __init__(self, port:str, baud:int = 115200):
        self.mod_ser = ser.SerialDevice(port, baud=baud, timeout=0.3)
        self.mod_ser.ser.dtr = False
        self.mod_ser.open()
        self.port = port

        # Validate device connection
        if not self._validate_device():
            self.mod_ser.close()
            raise ValueError( ('Device on %s is not a FETbox, or improperly' 
                               'onfigured (e.g. baud).') % self.port)

        self.id = self.query_ID()
        fetbox_logger.info("%s FETbox (ID: %s) initialized",
                            port, self.id)

        # Available analog pins, A0-A7
        self.analog_pins = ['A%i' % _pin for _pin in range(8)]

        # Friendly pin name look up table, string to pin interger value
        self.pin_table = {}
        for i, __pin in enumerate(self.analog_pins):
            self.pin_table.update({__pin: range(14, 22)[i]})

    def send_cmd(self, cmd:str, attempts:int = 3) -> bool:
        '''
        Send arbitrary command strings. Expect pass/fail-type response from
        FETbox. Will retry a set number of times if the command fails to
        execute successfully. 

        Used internally for all `FETbox` commands.

        Parameters
        ---------
        cmd : str
            Command string, format varies depending on command.
        attempts : int, default=3
            Maximum number of retry attempts before command failure.

        Returns
        -------
        bool
            Command success/failure
        '''
        cmd_done = False
        retries = 0
        rsp = None
        while(retries <= attempts and not cmd_done):
            if retries > 1:
                fetbox_logger.warning('Resending command "%s" (%i/%i)',
                                cmd.strip("\n\r"), retries, attempts)
            elif retries > 0:
                fetbox_logger.debug('Resending command "%s" (%i/%i)',
                                cmd.strip("\n\r"), retries, attempts)
            rsp = self.mod_ser.write_cmd(cmd, EOL="\n")['resp']
            if '*' in rsp:
                cmd_done = True
            retries += 1
        if '*' in rsp:
            return True
        else:
            return False

    def send_query(self, cmd:str, attempts:int = 3) -> str:
        '''
        Send arbitrary query string. Expects a LF-terminated response. Will
        retry a set number of times if the query fails to yield a parsable
        response. 
        
        Used internally for all `FETbox` queries.
        
        Parameters
        ---------
        cmd : str
            Query string
        attempts : int 
            Maximum number of retry attempts before query failure.

        Returns
        -------
        str
            Query response string.
        '''
        cmd_done = False
        retries = 0
        rsp = None
        while(retries <= attempts and not cmd_done):
            if retries > 1:
                fetbox_logger.warning('Resending command "%s" (%i/%i)',
                                cmd.strip("\n\r"), retries, attempts)
            elif retries > 0:
                fetbox_logger.debug('Resending command "%s" (%i/%i)',
                                cmd.strip("\n\r"), retries, attempts)
            rsp = self.mod_ser.write_cmd(cmd, EOL="\n")['resp']

            if rsp == None:
                cmd_done = False
                retries += 1
            else:
                cmd_done = True
                return(rsp)
        return None

    def _validate_device(self) -> bool:
        '''
        Validate connected device is a FETbox.

        Returns
        -------
        bool
            Device is FETbox
        '''
        resp = self.send_query(CMDS["get_id"])
        if 'fetbox' in resp:
            return True
        return False

    def query_ID(self) -> int:
        '''
        Get the FETbox's unique ID, as defined in firmware.

        Returns
        -------
        int
            FETbox's interntal ID [0-9]
        '''
        fetbox_logger.debug("%s querying FETbox ID...", self.port)
        rsp = self.send_query(CMDS["get_id"])
        fetbox_logger.debug("\t\t Response: %s", rsp)
        return int(rsp[6:])

    def enable_chan(self, chan:int) -> bool:
        '''
        Set channel (int 1-5) output to HIGH.

        Parameters
        ---------
        chan : int {1-5}
            MOSFET output channel number [1-5]

        Returns
        -------
        bool
            Command success/failure
        '''
        if self.send_cmd(CMDS['enable'] % chan-1):
            fetbox_logger.info('%s Enabled chan. %i', self.port, chan)
            return True
        fetbox_logger.error('%s Failed to enable chan. %i', self.port, chan)
        return False

    def disable_chan(self, chan:int) -> bool:
        '''
        Set channel (int 1-5) output to LOW.

        Parameters
        ----------
        chan : int
            MOSFET output channel number [1-5]

        Returns
        -------
        bool
            Command success/failure
        '''
        if self.send_cmd(CMDS['disable'] % chan-1):
            fetbox_logger.info('%s Disabled chan. %i', self.port, chan)
            return True
        fetbox_logger.error('%s Failed to disable chan. %i', self.port, chan)
        return False
    
    def pwm_chan(self, chan: int, pwm: int) -> bool:
        '''
        Set given FETbox output channel PWM value.
        
        Parameters
        ----------
        chan : int {1-5}
            MOSFET output channel number [1-5]
        pwm : int {0-255}
            8-bit PWM value.

        Returns
        -------
        bool
            Command success/failure
        '''
        if(0 < pwm > 255):
            ValueError("PWM `pwm` must be an integer value 0-255")
        _pwm = "%03i" % pwm
        if self.send_cmd(CMDS['pwm'] % (chan, _pwm)):
            fetbox_logger.info('%s Channel %i PWM set to %i/255', self.port, 
                               chan, pwm)
            return True
        fetbox_logger.error('%s Failed to set chan. %i PWM', self.port, chan)
        return False

    def hit_hold_chan(self, chan: int, duty:float = 0.5) -> bool:
        '''
        Hit-and-hold for efficient solenoid operation. Sets output HIGH for
        short period then reduces effective output voltage via PWM.
        
        Parameters
        ----------
        chan : int {1-5}
            MOSFET output channel number [1-5]
        duty : float {0.0-1.0}, default=0.5
            Fraction of max PWM outpuyt after initial 'hit' delay.

        Returns
        -------
        bool
            Command success/failure
        '''
        if(0 > duty > 1):
            ValueError("Duty cycle `duty` must be a float, 0.0-1.0")
        _pwm = "%03i" % round(duty*255)
        if self.send_cmd(CMDS['hithold'] % (chan, _pwm)):
            fetbox_logger.info('%s Channel %i hit-and-hold enabled', self.port,
                               chan)
            return True
        fetbox_logger.error('%s Failed to set chan. %i hit-and-hold', self.port,
                            chan)
        return False

    def analog_read(self, pin: str) -> int:
        '''
        Read analog pin value directly from Arduino.

        Parameters
        ---------
        pin : str {'A0','A1','A2','A3','A4','A5','A6','A7'}
            Arduino analog pin name.

        Returns
        -------
        int or None
            10-bit analog pin reading (0-1023). None if query error.
        '''
        
        # Sanity check, valid analog pins: A0-A7
        if pin not in self.analog_pins:
            fetbox_logger.error("'%s' is not a valid analog pin. Enter a value from %s",
                                pin, self.analog_pins)
            return None
        
        # Send command, save response
        cmd_string = CMDS['anaread'] % self.pin_table[pin]
        rsp = self.send_query(cmd_string)
        
        # Attempt to convert to integer, log error & return None if not possible
        try:
            val = int(rsp.strip())
        except ValueError:
            fetbox_logger.error("%s Bad response from analog read pin '%s': '%s'",
                                self.port, pin, rsp.strip())
            return None
        except TypeError:
            fetbox_logger.error("%s No response from analog read, pin '%s'", 
                                self.port, pin)
            return None
        else:
            fetbox_logger.info("%s FETbox %i analogRead. Pin %s = %i",
            self.port, self.id, pin, val)
            return val

    def digital_read(self, pin) -> int:
        '''
        Read digital pin value directly from Arduino.

        Parameters
        ---------
        pin : int {0-13} or str {'A0','A1','A2','A3','A4','A5'}
            Arduino digital pin number (int) OR Arduino analog pin name (str)

        Returns
        -------
        int or None
            Pin reading:
            1 == HIGH,
            0 == LOW,
            None if error
        '''

        # Sanity check, valid digitally readable pin given [0-13, A0-A5]
        # A6, A7 are analog read-only
        digital_pins = [i for i in range(2,14)] + ['A%i' % _pin for _pin in range(6)] 
        if pin not in digital_pins:
            fetbox_logger.error("'%s' is not a valid digital pin. Enter a value from %s",
                                pin, digital_pins)
            return None

        # Look up analog pin if necessary
        if type(pin) == str:
            pin = self.pin_table[pin]

        # Send command, save response
        cmd_string = CMDS['digread'] % pin
        rsp = self.send_query(cmd_string)

        # Attempt to convert to integer, log error & return None if not possible
        try:
            val = int(rsp.strip())
        except ValueError:
            fetbox_logger.error("%s Bad response from digital read, pin '%s'",
                                self.port, pin)
            return None
        except TypeError:
            fetbox_logger.error("%s No response from digital read, pin '%s'",
                                self.port, pin)
            return None
        else:
            fetbox_logger.info("%s FETbox(%i) digitalRead: Pin %s = %i",
            self.port, self.id, pin, val)
            return val

    def analog_write(self, pin: int, pwm: int) -> bool:
        '''
        Arduino analog write function. Sets PWM value of pin. Arduino Nano PWM
        pins are 3,5,6,9,10,11. NB: only pin 11 is unrouted to MOSFET gates.

        Parameters
        ---------
        pin : int {3,5,6,9,10,11}
            PWM-capable Arduino pin number.

        pwm : int {0-255}
            8-bit PWM output value.

        Returns
        -------
        bool
            Command success/fail
        '''
        # Pin number sanity check
        pwm_pins = [3,5,6,9,10,11]
        if pin in pwm_pins:
            # Warn about writing to MOSFET pin
            if pin != 11:
                fetbox_logger.warning("analogWrite used a FETbox(%i) MOSFET output (Arduino pin %i)",
                self.id, pin)
            fetbox_logger.info("%s FETbox(%i) analogWrite: Pin %i - %i",
                                  self.port, self.id, pin, pwm)
            if self.send_cmd(CMDS['anawrite'] % (pin, pwm)):
                return True
        else:
            fetbox_logger.error("'%s' is not a PWM capable pin. Enter a value from %s",
            pin, pwm_pins)
        return False

    def digital_write(self, pin, val:int ) -> bool:
        '''
        Arduino digitalWrite functionality. Sets pin HIGH (1) or LOW (0).

        Parameters
        ---------
        pin : int {0-13} or,
              str {'A0'-'A5}
            Arduino digital pin number [0-13] or analog pin name [A0-A5]
            A6/A7 cannot are analog read only.
        val : int {0,1}
            Output pin state. 1 (digital HIGH) or 0 (digital LOW)

        Returns
        -------
        bool
            Command success/failure
        '''
        # Sanity check, valid digitally readable pin given [0-13, A0-A5]
        # A6, A7 are analog read-only
        digital_pins = [i for i in range(2,14)] + ['A%i' % _pin for _pin in range(6)] 
        if pin not in digital_pins:
            fetbox_logger.error("'%s' is not a digitalWrite-capable pin. Enter a value from %s",
                                  pin, digital_pins)
            return False

        # Sanity check digitalWrite value [0-1]
        if val not in [0,1]:
            fetbox_logger.error("'%s' is not a valid digitalWrite value. Enter 0 or 1",
                                  val)
            return False

        # Look up analog pin if necessary
        if type(pin) == str:
            pin = self.pin_table[pin]

        # Send command
        cmd_string = CMDS['digwrite'] % (pin, val)
        if self.send_query(cmd_string):
            fetbox_logger.info("%s FETbox (%i) digitalWrite: Pin %s = %i",
            self.port, self.id, pin, val)
            return True
        return False

    def heartbeat(self) -> bool:
        '''
        Ping FETbox, used to confirm active/responsive connection.
        
        Returns
        -------
        bool 
            Heartbeat found / ping acknowledged
        '''

        if self.send_cmd(CMDS['heartbeat']):
            fetbox_logger.debug('%s FETbox heartbeat found', self.port)
            return True
        return False

    def kill(self):
        '''Kill any threads and close the FETbox serial port'''
        self.mod_ser.close()
        fetbox_logger.info('%s FETbox CLOSED', self.port)

# If run as standalone script, will output scan results to terminal.
if __name__ == "__main__":
    result = scan_for_fetbox(baud=115200)
    if result:
        for ctrlr in result:
            print("FETbox (ID %i) detected on %s" %
                  (ctrlr['id'], ctrlr['port']))
    else:
        print("No FETbox detected.")
