'''
Ismatec Reglo Digital
=====================
Convenience functions for control of common Ismatec Reglo Digital peristaltic
pump functions

Author: Robert Pazdzior (2021) 

Contact: github.com/robertpazdzior rpazdzior@cemm.at

Licensed under Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)
'''

from datetime import datetime
import logging
from .. import serial_io as ser

dig_logger = logging.getLogger("ismatecDig")

REGLO_DIG = {
    'start'     :           '%sH\r',    # Start pump rotation
    'stop'      :           '%sI\r',    # Stop pump rotation
    'set_clockwise' :       '%sJ\r',    # Set rotation clockwise
    'set_counterclockwise': '%sK\r',    # Set rotation counter-clockwise
    'set_RPM'   :           '%sL\r',    # Set pump speed in RPM mode
    'set_mLmin' :           '%sM\r',    # Set pump speed in mL/min mode
    'set_flow'  :           '%sf%s\r',  # In ml/min, "1f0122-1" = 12.2 mL/min
    'get_flow'  :           '%sf\r',    # In mL/min, formated as above
    'set_cal_flow':         '%s!%s\r',  # Flow at max RPM, formated as above
    'get_cal_flow':         '%s!\r',    # Get cal. flow at max RPM

    'set_addr'  :           '%s@%s\r',  # Set pump address, "1@[i]" i = 1-8
    'set_disp_man':         '%sA\r',    # Set control panel, manual/normal
    'set_disp_rem':         '%sB\r',    # Set control panel, remote/disabled
    'set_display_txt':      '%sDA%s\r',  # Show txt[PumpAddr]DA[4-CharString][CR]
    'set_tube_id':          '%s+%s\r',  # Set tubing innner diameter

    'get_name'  :           '%s#\r',    # Return pump name, firmware version
    'get_run_state'   :     '%sE\r',    # Query pump, running (+) or not (-)
}


class RegloDigital():
    '''
    Ismatec Reglo Digital pump control serial control.

    Parameters
    ----------
    port : str
        Serial port on which Relgo Digital is connected. E.g. 'COM3'.

    timeout : float, default=0.5
        Time (seconds) to allow pump to respond before commands timeout/fail.

    Attributes
    ----------
    pump_ser : Serial
        Backend PySerial device object

    port : str
        Serial port name

    addr: int
        Pump address (for e.g. serial daisy-chaining)

    status : {'timestamp':datetime, 'run_state':str, 'dir':int, 'flow':float}
        Dictionary of last pump status update values

        `timestamp` - datetime object of last status update
        
        `run_state` - pump head state 'Running', 'Idle', or 'ERROR'

        `dir` - pump head direction. -1 (CCW); +1 (CW); 0 (ERROR)

        `flow` - current set flow rate (mL/min)

    max_flow : float
        Pump maximum flow rate

    last_dir : int
        Last set pump head direction. CW == +1; CCW == -1; ERROR == 0.
    '''
    def __init__(self, port:str, addr:int):
        self.pump_ser = ser.SerialDevice(port, timeout=0.2)
        self.pump_ser.open()
        self.port = port
        self.addr = addr
        self.status = None
        self.set_mode_flowrate() # Set put speed control for mL/min
        self.last_dir = None # Track direction setting, no way to query
        self.update_status()
        dig_logger.debug('%s Reglo Digital device initialized', port)

    def send_cmd_pass_fail(self, cmd: str) -> int:
        '''
        Send command ,`cmd`, to pump. Resend if failure up to a total of three 
        attempts.

        See Reglo Digital manual (pp. 33-38) for command structure 
        documentation.
        http://www.ismatec.com/images/pdf/manuals/Reglo_Digital_new.pdf

        Parameters
        ----------
        cmd : str 
            Command string, CR-terminated.

        Returns
        -------
        int 
            1 == pass

            0 == fail

            -1 == error

        '''
        cmd_string = cmd #% (self.addr)
        cmd_done = False
        rsp_dict = ''
        tries = 0
        while not cmd_done and tries <= 3:
            rsp_dict = self.pump_ser.write_cmd(cmd_string, 1)
            rsp_string = rsp_dict['resp']
            rsp_cmd = rsp_dict['cmd']
            if rsp_cmd != cmd_string:
                Warning('Command/response queue out of sync!')
                return -1
            if rsp_string == '*':
                return 1
            tries += 1

        if rsp_string == '#':
            return 0
        return -1

    def send_cmd_string_resp(self, cmd) -> str:
        '''
        Query the pump with `cmd`. Resend if failure up to a total of three 
        attempts.
        
        See Reglo Digital manual (pp. 33-38) for 
        command structure documentation.
        http://www.ismatec.com/images/pdf/manuals/Reglo_Digital_new.pdf

        Parameters
        ----------
        cmd : str 
            Command string, CR-terminated.

        Returns
        -------
        str
            pump response string

        '''
        cmd_string = cmd
        rsp_dict = self.pump_ser.write_cmd(cmd_string, EOL='\n')
        rsp_cmd = rsp_dict['cmd']
        if rsp_cmd != cmd_string:
            dig_logger.error('%s Command/response queue out of sync!', self.port)
            return None
        return rsp_dict['resp']

    def update_status(self):
        'Update the pump `status` attribute. Must be called manually.'

        dig_logger.debug("%s status updated.", self.port)
        self.status = {}
        self.status['timestamp'] = datetime.now()
        run_status = self.get_run_state()
        if run_status == 1:
            self.status['run_state'] = "Running"
        elif run_status == 0:
            self.status['run_state'] = "Idle"
        else:
            self.status['run_state'] = "ERROR"

        self.status['flow'] = self.get_flow()
        self.status['dir'] = self.get_dir()

    def start(self) -> int:
        '''
        Start/run the pump.
        
        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        dig_logger.debug('%s Pump "run" command sent.', self.port)
        resp = self.send_cmd_pass_fail(REGLO_DIG['start'] % self.addr)
        if resp == 1:
            dig_logger.info('%s Pump STARTED', self.port)
        elif resp == 0:
            dig_logger.error('%s Pump refused to start', self.port)
        else:
            dig_logger.error('%s Pump response, "%s", not recognized', 
                             self.port, resp)
            resp = -1

        return resp

    def stop(self) -> int:
        '''
        Stop the pump.
        
        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        dig_logger.debug('%s Pump "stop" command sent.', self.port)

        resp = self.send_cmd_pass_fail(REGLO_DIG['stop'] % self.addr)

        if resp == 1:
            dig_logger.info('%s Pump STOPPED', self.port)
        elif resp == 0:
            dig_logger.error('%s Pump refused to stop', self.port)
        else:
            dig_logger.error('%s Pump response, "%s", not recognized', 
                             self.port, resp)
            resp = -1

        return resp

    def set_flow(self, flow_rate:float) -> int:
        '''
        Set pump flow rate.
        
        Parameters
        ----------
        flow_rate : float
            Flow rate in mL/min.

        Returns
        -------
        int
            1 == Pass

            0 == Fail

            -1 == Other error
        '''
        # Format flow rate for pump command string
        flow_input = float(flow_rate)
        flow_string = format(flow_input/100, "09.2E") # Move decimal place
        flow_string = flow_string.replace("E", '').replace('.', '')
        flow_string = flow_string[:5]+flow_string[6:]
        cmd_string = REGLO_DIG['set_flow'] % (self.addr, flow_string)

        rsp_string = self.send_cmd_string_resp(cmd_string)
        try:
            rsp_flowrate = float(rsp_string.strip('\r'))
        except ValueError:
            rsp_flowrate = '---'
        else:
            pcnt_diff = abs(flow_input-rsp_flowrate)/flow_input
            if pcnt_diff < 0.1:
                dig_logger.info("%s FLOWRATE SET to %.3fmL/min",
                             self.port,
                             rsp_flowrate)
                return rsp_flowrate # Pass
            return 0 # Fail
        return -1 # Something else. Bad response?

    def get_flow(self) -> float:
        '''
        Query current pump flow rate.
        
        Returns
        -------
        float
            Flow rate in mL/min. OR `-1` if an error occured.
        '''
        cmd_string = REGLO_DIG['get_flow'] % (self.addr)
        rsp_string = self.send_cmd_string_resp(cmd_string)
        try:
            rsp_flowrate = float(rsp_string.strip('\r').replace("mL/min", ""))
        except ValueError or AttributeError:
            rsp_flowrate = -1.0

        return rsp_flowrate


    def get_run_state(self):
        '''
        Query pump current run status.
        
        Returns
        -------
        int
            1 == Running

            0 == Stopped

           -1 == Other error

           -2 == Stopped, motor overload
        '''
        cmd_string = REGLO_DIG['get_run_state'] % self.addr
        rsp_dict = self.pump_ser.write_cmd(cmd_string, 1)
        rsp_string = rsp_dict['resp']
        if '+' in rsp_string:
            return 1
        if '-' in rsp_string:
            return 0
        if rsp_string == "#": # Failure, check again
            rsp_dict = self.pump_ser.write_cmd(REGLO_DIG['get_name'], EOL='\r')
            rsp_string = rsp_dict['resp']
            if rsp_string == '#':
                # Failure again, pump probably in overload
                return -2
        return -1

    def set_dir(self, direction):
        '''
        Set pump head direction clockwise or counterclockwise.
        
        Parameters
        ----------
        direction : int {-1, +1}
            Pump head direction: clockwise (+1) or counter-clockwise (-1)

        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        if direction == +1:
            log_str = 'clockwise'
            cmd_str = REGLO_DIG['set_clockwise'] % self.addr
        else:
            log_str = 'counter-clockwise'
            cmd_str = REGLO_DIG['set_counterclockwise'] % self.addr
        rsp = self.send_cmd_pass_fail(cmd_str)
        if rsp == 1:
            dig_logger.info('%s Pump direction set to %s', 
                         self.port, log_str.upper())
            if 'counter' in log_str:
                self.last_dir = -1
            else:
                self.last_dir = 1
        else:
            dig_logger.error('%s FAILED to set pump direction to %s',
                          self.port, log_str.upper())
            self.last_dir = 0
        return rsp

    def get_dir(self):
        '''
        Returns the last direction set via control software. Note Reglo Digital
        lacks ability to query pump head direction. Tracked in software.
        
        Returns
        -------
        int
            Last set pump direction:
            
                +1 == clockwise

                -1 == counter-clockwise

                0 == unknown error
        '''
        return self.last_dir

    def set_mode_rpm(self):
        '''Change pump flow rate to RPM speed mode'''
        return self.send_cmd_pass_fail(REGLO_DIG['set_RPM'] % self.addr)

    def set_mode_flowrate(self):
        '''Change pump flow rate to mL/min mode'''
        return self.send_cmd_pass_fail(REGLO_DIG['set_mLmin'] % self.addr)

    def set_tube_diameter(self, diam_mm):
        '''
        Sets tubing inner diameter. Determines calibrated volumetric flow rate.

        0.13, 0.19, 0.25, 0.38, 0.44, 0.51, 0.57, 0.64, 0.76, 0.89, 0.95, 1.02,
        1.09, 1.14, 1.22, 1.30, 1.42, 1.52, 1.65, 1.75, 1.85, 2.06, 2.29, 2.54,
        2.79, 3.17

        Parameters
        ----------
        diam_mm : float {0.13, 0.19, 0.25, 0.38, 0.44, 0.51, 0.57, 0.64, 0.76, 0.89, 0.95, 1.02, 1.09, 1.14, 1.22, 1.30, 1.42, 1.52, 1.65, 1.75, 1.85, 2.06, 2.29, 2.54, 2.79, 3.17}
            Tubing inner diameter in millimeters
        
        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        # Valid tubing inner diameters from Ismatec
        tubing_ids = [0.13, 0.19, 0.25, 0.38, 0.44, 0.51, 0.57, 0.64, 0.76,
                      0.89, 0.95, 1.02, 1.09, 1.14, 1.22, 1.30, 1.42, 1.52,
                      1.65, 1.75, 1.85, 2.06, 2.29, 2.54, 2.79, 3.17]

        if diam_mm not in tubing_ids:
            dig_logger.info('%s Given tubing ID "%s" is not valid, setting to '
                         'nearest valid ID...', self.port, diam_mm)
            # Find the nearest valid tubing diameter
            diam_mm = min(tubing_ids, key=lambda x: abs(x-diam_mm))

        diam_form = '{0:04d}'.format(int(diam_mm*100))
        cmd_str = REGLO_DIG['set_tube_id'] % (self.addr, diam_form)
        if cmd_str == 1:
            dig_logger.info('%s Tubing ID set to %.2fmm', self.port, diam_mm)
        return self.send_cmd_pass_fail(cmd_str)

    def set_cal_flow(self, flow_rate=12.4):
        '''
        Set the calibrated volumetric flow rate at maximum pump speed.
        
        Parameters
        ----------
        flow_rate : float, default = 12.4
            Volumetric flow rate (mL/min) at maximum pump head speed. Default
            12.4 mL/min.

        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        
        '''
        # Format flow rate for pump command string
        flow_input = float(flow_rate)
        flow_string = format(flow_input/100, "09.2E")
        flow_string = flow_string.replace("E", '').replace('.', '')
        flow_string = flow_string[:5]+flow_string[6:]
        cmd_string = REGLO_DIG['set_cal_flow'] % (self.addr, flow_string)

        rsp_string = self.send_cmd_pass_fail(cmd_string)
        return rsp_string

    def display_text(self, txt):
        '''
        Show text on the pump LCD, 4 characters max.
        
        Parameters
        ----------
        txt : str
            Text to display on pump LCD. Maximum 4 characters.

        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        # Set display panel to remote control mode
        cmd_str = REGLO_DIG['set_disp_rem'] % self.addr
        self.send_cmd_pass_fail(cmd_str)

        # Print txt to display
        disp_txt = txt
        if len(txt) > 4:
            # Truncate to first 4 chars if too long
            dig_logger.warning('"%s" is too long to display, using 1st four',
                                disp_txt)
            disp_txt = txt[:4]
        cmd_str = REGLO_DIG['set_display_txt'] %  (self.addr, disp_txt)
        return self.send_cmd_pass_fail(cmd_str)

    def restore_display(self):
        '''
        Return the LCD to normal display mode. Used to clear text displayed
        using `display_text`.

        Returns
        -------
        int
            1 == Pass

            0 == Fail

            -1 == Other error

        '''
        cmd_str = REGLO_DIG['set_disp_man'] % (self.addr)
        return self.send_cmd_pass_fail(cmd_str)

    def kill(self):
        '''Kill all threads and close pump serial port'''
        dig_logger.info('%s pump CLOSED', self.port)
        self.pump_ser.close()
