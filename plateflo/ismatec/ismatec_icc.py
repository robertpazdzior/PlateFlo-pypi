'''
Ismatec Reglo ICC
=================
Convenience functions for control of common Ismatec Reglo ICC peristaltic pump
functions.

Author: Robert Pazdzior (2021)

Contact: github.com/robertpazdzior rpazdzior@cemm.at

Licensed under Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)
'''

from datetime import datetime
import logging
from .. import serial_io as ser

icc_logger = logging.getLogger("ismatecICC")

REGLO_ICC = {
    'start':                '%sH\r',     # [Pump Addr]H[CR]
    'stop':                 '%sI\r',     # [Pump Addr]I[CR]
    'start_chan':           '%sH%s\r',   # [Channel]H[Pump Addr][CR]
    'stop_chan':            '%sI%s\r',   # [Channel]I[Pump Addr][CR]
    'get_run_state':        '%sE\r',     # [Pump Addr]E[CR]
    'chan_mode':            '%s~%s\r',   # Address individual channels 1, or pump 0
    'set_RPM'   :           '%sL\r',     # Set pump speed in RPM mode
    'set_mLmin' :           '%sM\r',     # Set pump speed in mL/min mode
    'set_flow':             '%sf%s\r', 
    'get_flow':             '%sf\r',
    'set_clockwise':        '%sJ\r',     # [Pump Addr]J[CR]
    'set_counterclockwise': '%sK\r',     # [Pump Addr]K[CR]
    'get_chan_run_state':   '%sE%s\r',   # [Channel]E[Pump Addr][CR]
    'get_direction':        '%sxD\r',    # [Pump Addr]xD[CR]
    'get_chan_dir':         '%sxD%s\r',  # [Channel]xD[Pump Addr][CR]
    'set_chan_flow':        '%sf%s\r',   # [Channel]f[Flow-Rate][CR]
    'get_chan_flow':        '%sf\r',     # [Channel]f[CR]
    'set_chan_clockwise':   '%sJ%s\r',   # [Channel]J[Pump Addr][CR]
    'set_chan_cntr_clkws':  '%sK%s\r',   # [Channel]K[Pump Addr][CR]
    'get_calmaxflow':       '%s?\r',     # [Channel]
    'set_disp_man':         '%sA\r',    # Set control panel, manual/normal
    'set_disp_rem':         '%sB\r',    # Set control panel, remote/disabled
    'set_display_txt':      '%sDA%s\r'   # [Pump Addr]DA[string (<16 char)][CR]
}

class RegloICC():
    '''
    Ismatec Reglo ICC pump object, for serial control of multi-channel pump.

    Parameters
    ----------
    port : str
        Serial port on which Relgo ICC is connected. E.g. 'COM3'
    
    channels : int, default=4
        Number of channels on ICC pump.

    timeout : float, default=0.5
        Time (seconds) to allow pump to respond before commands timeout/fail.

    Attributes
    ----------
    pump_ser : Serial
        Backend PySerial device object

    port : str
        Serial port name

    addr : str
        Pump internal address (for e.g. serial daisy-chaining)

    status : dict
        state, direction, and flow rate for all channels. Timestamp of last update.

    max_flow : float
        Pump maximum flow rate (mL/min)

    n_channels : int
        Number of independant channels on Reglo ICC pump.
    '''
    def __init__(self, port, addr, channels=4, timeout=0.5):
        self.pump_ser = ser.SerialDevice(port, timeout=timeout)
        self.pump_ser.open()
        self.port = port
        self.addr = addr
        self.status = None
        self.n_channels = channels

        self.set_per_chan_mode(1) # Disable per-channel addressing
        self.chan_mode = False
        self.max_flow = self.get_max_flowrate() # For flow-rate adjustment
        self.set_mode_flowrate() # Set put speed control for mL/min
        self.update_status()

    def send_cmd_pass_fail(self, cmd:str) -> int:
        '''
        Send command ,`cmd`, to pump. Resend if failure up to a total of three 
        attempts.

        See Reglo ICC manual (pp. 17-33) for command structure 
        documentation.
        http://www.ismatec.com/images/pdf/manuals/14-036_E_ISMATEC_REGLO_ICC_ENGLISH_REV.%20C.pdf

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
        cmd_string = cmd
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

    def send_cmd_string_resp(self, cmd_string:str, EOL='\n') -> str:
        '''
        Command/query the pump with `cmd`. Resend if failure up to a total of 
        three attempts.
        
        See Reglo ICC manual (pp. 17-33) for command structure 
        documentation.
        http://www.ismatec.com/images/pdf/manuals/14-036_E_ISMATEC_REGLO_ICC_ENGLISH_REV.%20C.pdf

        Parameters
        ----------
        cmd : str 
            Command string, CR-terminated.

        Returns
        -------
        str
            pump response string
        '''
        rsp_dict = self.pump_ser.write_cmd(cmd_string, EOL=EOL)
        rsp_cmd = rsp_dict['cmd']
        if rsp_cmd != cmd_string:
            icc_logger.error('%s Command/response queue out of sync!', self.port)
            return None
        return rsp_dict['resp']

    def get_max_flowrate(self) -> float:
        '''
        Query the maximum achievable flow rate in mL/min.
        
        Returns
        -------
        float
            Maximum pump flow rate (mL/min)
        '''
        cmd_str = REGLO_ICC['get_calmaxflow'] % self.addr
        rsp = self.send_cmd_string_resp(cmd_str)
        max_flow = float(rsp.strip(' ml/min\r\n'))
        return max_flow

    def start(self) -> int:
        '''
        Start/run pump, includes all channels with a non-zero flow rate.
        
        Returns
        -------
        int
            1 == pass

            0 == fail

            -1 == error
        '''
        if self.chan_mode:
            self.set_per_chan_mode(0)

        start_cmd = REGLO_ICC['start'] % (self.addr)
        rsp = self.send_cmd_pass_fail(start_cmd)
        if rsp == 1:
            icc_logger.info('%s Pump STARTED.', self.port)
        return rsp

    def stop(self) -> int:
        '''
        Stop pump. All channels.
        
        Returns
        -------
        int
            1 == pass

            0 == fail

            -1 == error
        '''
        if self.chan_mode:
            self.set_per_chan_mode(0)

        stop_cmd = REGLO_ICC['stop'] % (self.addr)
        rsp = self.send_cmd_pass_fail(stop_cmd)

        if rsp == 1:
            icc_logger.info('%s Pump STOPPED.', self.port)
        else:
            icc_logger.info('%s FAILED to confirm pump stop!', self.port)
        return rsp

    def update_status(self):
        'Update the pump `status` attribute. Must be called manually.'
        status = {}
        status['timestamp'] = datetime.now()
        for i in range(1, self.n_channels+1):
            chan_state = "Running" if self.get_chan_run_state(i) > 0 else "Idle"
            chan_dir = self.get_chan_dir(i)
            if chan_dir == 1:
                chan_dir = "CW"
            elif chan_dir == -1:
                chan_dir = "CCW"
            else:
                chan_dir = "ERR"

            chan_flow = self.get_chan_flow(i)
            status[i] = {
                'run_state': chan_state,
                'dir': chan_dir,
                'flow': chan_flow
            }
        self.status = status

    def set_mode_flowrate(self):
        '''
        Set pump to volumetric flowrate mode.
        
        Returns
        -------
        int
            1 == pass

            0 == fail

            -1 == error
        '''
        return self.send_cmd_pass_fail(REGLO_ICC['set_mLmin'] % self.addr)

    def set_flow(self, flow_rate:float) -> float:
        '''
        Set pump flow rate (mL/min). If requested flow rate is above pump limit,
        set to maximum achievable, `max_flow`.
        
        Returns
        -------
        int
            1 == pass

            0 == fail

            -1 == error
        '''
        # Format flow rate for pump command string
        flow_input = float(flow_rate)
        if flow_input == 0:
            return -1
        if flow_input > self.max_flow:
            flow_input = self.max_flow*0.9
            icc_logger.info('%s Flow set above maximum, setting to max %s mL/min',
                         self.port, flow_input)
        flow_string = format(flow_input*10, "09.2E")
        flow_string = flow_string.replace("E", '').replace('.', '')
        flow_string = flow_string[:5]+flow_string[6:]
        cmd_string = REGLO_ICC['set_flow'] % (self.addr, flow_string)
        if self.chan_mode:
            self.set_per_chan_mode(0)
        rsp_string = self.send_cmd_string_resp(cmd_string)
        try:
            rsp_flowrate = float(rsp_string.strip('\r'))/1000
        except ValueError:
            rsp_flowrate = '---'
        else:
            pcnt_diff = abs(flow_input-rsp_flowrate)/flow_input
            if pcnt_diff < 0.1:
                icc_logger.info("%s flowrate set to %.3fmL/min",
                             self.port,
                             rsp_flowrate)
                return rsp_flowrate # Pass
            return 0 # Fail
        return -1 # Something else. Bad response?

    def set_per_chan_mode(self, mode:int):
        '''
        Set mode for command addressing: channel(1), pump-wide(0)
        
        Parameters
        ----------
        mode : int {0, 1}
            Send pump-wide commands (0) or per-channel (1).

        Returns
        -------
        int
            1 == pass

            0 == fail

            -1 == error
        '''
        rsp = self.send_cmd_pass_fail(REGLO_ICC['chan_mode'] %
                                      (self.addr, mode))
        self.chan_mode = bool(mode)
        icc_logger.debug('%s ICC channel mode set to %s', self.addr, mode)
        return rsp

    def set_dir(self, direction:int) -> int:
        '''
        Set pump head direction: clockwise(+1), or counterclockwise(-1)
        
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
            cmd_str = REGLO_ICC['set_clockwise'] % (self.addr)
        elif direction == -1:
            log_str = 'counter-clockwise'
            cmd_str = REGLO_ICC['set_counterclockwise'] % (self.addr)
        rsp = self.send_cmd_pass_fail(cmd_str)
        if rsp == 1:
            icc_logger.info('%s Pump direction set to %s',
                         self.port, log_str.capitalize())
        else:
            icc_logger.error('%s FAILED to set pump direction to %s', 
                          self.port, log_str.capitalize())
        return rsp

    def get_dir(self) -> int:
        '''
        Query pump head direction.
        
        Returns
        -------
        int
            Pump head direction:

                +1 == clockwise

                -1 == counter-clockwise
                
                0 == unknown error
        '''
        cmd_str = REGLO_ICC['get_direction'] % self.addr
        rsp = self.send_cmd_string_resp(cmd_str)
        if rsp == 'J':
            return +1
        if rsp == 'K':
            return -1
        return 0

    def set_chan_dir(self, chan:int, direction:int) -> int:
        '''
        Set channel direction: clockwise(+1), or counterclockwise(-1).
        
        Parameters
        ----------
        chan : int
            Pump channel number
        direction : int {-1, +1}
            Channel direction: clockwise (+1) or counter-clockwise (-1)

        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        self.set_per_chan_mode(1)
        if direction == +1:
            log_str = 'clockwise'
            cmd_str = REGLO_ICC['set_chan_clockwise'] % (chan, self.addr)
        elif direction == -1:
            log_str = 'counter-clockwise'
            cmd_str = REGLO_ICC['set_chan_cntr_clkws'] % (chan, self.addr)
        rsp = self.send_cmd_pass_fail(cmd_str)
        self.set_per_chan_mode(0)
        if rsp == 1:
            icc_logger.info('%s Channel %i direction set to %s',
                         self.port, chan, log_str.capitalize())
        else:
            icc_logger.error('%s FAILED to set channel %i direction to %s',
                          self.port, chan, log_str.capitalize())
        return rsp

    def get_chan_dir(self, chan:int) -> int:
        '''
        Query pump channel head direction.
        
        Parameters
        ----------
        chan : int
            Pump channel number

        Returns
        -------
        int
           1 == clockwise
           
           -1 == counter-clockwise
           
           0 == error
        '''
        self.set_per_chan_mode(1)
        cmd_str = REGLO_ICC['get_chan_dir'] % (chan, self.addr)
        rsp = self.send_cmd_string_resp(cmd_str).strip('\r')
        self.set_per_chan_mode(0)
        if rsp == 'J':
            return +1
        if rsp == 'K':
            return -1
        return rsp

    def get_chan_run_state(self, chan:int) -> int:
        '''Query pump channel run state. 

        Parameters
        ----------
        chan : int
            Pump channel number

        Returns
        -------
        int
            1 == running,

            0 == stopped,

           -1 == error
        '''
        cmd_str = REGLO_ICC['get_chan_run_state'] % (chan, self.addr)
        self.set_per_chan_mode(1)
        chan_state = self.pump_ser.write_cmd(cmd_str, rsp_len=1)
        self.set_per_chan_mode(0)
        if '+' in chan_state['resp']:
            return 1
        if '-' in chan_state['resp']:
            return 0
        return -1

    def start_chan(self, chan:int) -> int:
        '''
        Start/run pump channel.
        
        Parameters
        ----------
        chan : int
            Pump channel number

        Returns
        -------
        int
            1 == Pass

            0 == Fail

            -1 == Other error
        '''
        icc_logger.info('%s Channel %i STARTED', self.port, chan)
        self.set_per_chan_mode(1)
        cmd_str = REGLO_ICC['start_chan'] % (chan, self.addr)
        rsp = self.send_cmd_pass_fail(cmd_str)
        self.set_per_chan_mode(0)
        return rsp

    def stop_chan(self, chan:int) -> int:
        '''
        Stop pump channel.

        Parameters
        ----------
        chan : int
            Pump channel number
        
        Returns
        -------
        int
            1 == Pass

            0 == Fail

            -1 == Other error
        '''
        icc_logger.info('%s Channel %i STOPPED', self.port, chan)
        self.set_per_chan_mode(1)
        cmd_str = REGLO_ICC['stop_chan'] % (chan, self.addr)
        rsp = self.send_cmd_pass_fail(cmd_str)
        self.set_per_chan_mode(0)
        return rsp

    def get_chan_flow(self, chan:int) -> float:
        '''
        Query channel set flow-rate. 
        
        *NB*: Not supported when daisy-chaining multiple pumps over single serial 
        interface.

        Parameters
        ----------
        chan : int
            Pump channel number

        Returns
        -------
        float
            channel set flow-rate; otherwise,
            
            -1.0 == error
        '''
        cmd_str = REGLO_ICC['get_chan_flow'] % (chan)
        self.set_per_chan_mode(1)
        rsp = self.send_cmd_string_resp(cmd_str)
        self.set_per_chan_mode(0)
        rsp_flowrate = None
        try:
            rsp_flowrate = float(rsp.strip(' ml/min\r\n'))/1000
        except ValueError:
            rsp_flowrate = -1.0
        except AttributeError:
            rsp_flowrate = -1.0

        return rsp_flowrate

    def set_chan_flow(self, flow_rate, chan):
        '''Set channel flow rate in mL/min.

        Parameters
        ----------
        chan : int
            Pump channel number
        flow_rate : float
            Flow rate in mL/min

        Returns
        -------
        int
            1 == Pass
            0 == Fail
            -1 == Error
        '''
        # Format flow rate for pump command string
        self.set_per_chan_mode(1)
        flow_input = float(flow_rate)
        if flow_input == 0:
            return -1
        if flow_input > self.max_flow:
            flow_input = self.max_flow*0.9
            icc_logger.info('%s Flow set above maximum, setting to max %s mL/min',
                         self.port, flow_input)
        flow_string = format(flow_input*10, "09.2E")
        flow_string = flow_string.replace("E", '').replace('.', '')
        flow_string = flow_string[:5]+flow_string[6:]
        cmd_string = REGLO_ICC['set_chan_flow'] % (chan, flow_string)
        rsp_string = self.send_cmd_string_resp(cmd_string)
        self.set_per_chan_mode(0)
        try:
            rsp_flowrate = float(rsp_string.strip('\r'))/1000
        except ValueError:
            rsp_flowrate = '---'
        except AttributeError:
            return -1
        else:
            pcnt_diff = abs(flow_input-rsp_flowrate)/flow_input if flow_input > 0 else 0
            if pcnt_diff < 0.1:
                icc_logger.info("%s Channel %i flowrate set to %.3fmL/min",
                             self.port, chan, rsp_flowrate)
                return rsp_flowrate # Pass
            return 0 # Fail
        return -1 # Something else. Bad response?

    def display_text(self, txt:str) -> int:
        '''
        Show text on the pump LCD. Maximum 15 character.
        
        Parameters
        ----------
        txt : str
            Text to display on pump LCD. Maximum 15 characters.

        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        # Set display panel to remote control mode
        cmd_str = REGLO_ICC['set_disp_rem'] % self.addr
        self.send_cmd_pass_fail(cmd_str)

        # Print txt to display
        disp_txt = txt
        if len(txt) > 15:
            icc_logger.warning('"%s" is too long to display, using 1st 15 char',
                                disp_txt)
            disp_txt = txt[:15]
        cmd_str = REGLO_ICC['set_display_txt'] %  (self.addr, disp_txt)
        return self.send_cmd_pass_fail(cmd_str)

    def restore_display(self) -> int:
        '''
        Return the LCD to normal display mode. 
        Used to reset the LCD after `display_text`, for example.
        
        Returns
        -------
        int
            1 == Pass

            0 == Fail
            
            -1 == Other error
        '''
        cmd_str = REGLO_ICC['set_disp_man'] % (self.addr)
        return self.send_cmd_pass_fail(cmd_str)

    def kill(self):
        '''Kill all threads and close the pump's serial port'''
        self.pump_ser.close()
        icc_logger.info('%s pump CLOSED', self.port)
