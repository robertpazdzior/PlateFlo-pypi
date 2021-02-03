'''
Serial IO
=========
Library for basic threaded serial command/response handling, avoids blocking
the main script thread during operation.

Author: Robert Pazdzior (2021) 

Contact: github.com/robertpazdzior - rpazdzior@cemm.at

Licensed under Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)
'''

from queue import Queue, Empty
from threading import Lock, Event, Thread
from datetime import datetime
import logging
import serial
from serial.tools import list_ports as ser_list_ports

serialio_logger = logging.getLogger('serialIO')

class CmdExecThread(object):
    '''
    Command queue monitoring thread.
    
    Executes commands from queue and queues the response.

    Parameters
    ----------
    master : SerialDevice
        The SerialDevice instance over which to send/recieve serial commands.
    '''
    def __init__(self, master):
        if not isinstance(master, SerialDevice):
            raise TypeError('CmdExec requires type SerialDevice as master.')
        self.thread = None
        self.device = master
        self.ser = self.device.ser
        self.ser_lock = self.device.ser_lock
        self.stop_thread = Event()
        self.cmd_Q = self.device.cmd_Q
        self.rsp_Q = self.device.rsp_Q
        serialio_logger.debug('%s Command queue instantiated', self.device.port)

    def execution_loop(self):
        '''
        Sends commands to the `Serial` device and listens for a defined
        response.

        Command queue objects are dicts containing the string command and EITHER
        a command length or command EOL character.

        Examples
        --------
        {cmd: "1H", respLen: 1} # A single character response

        {cmd: "1#", respEOL: '\\n'} # Multiple chars, LF-terminated


        '''
        serialio_logger.debug('%s Cmd exec loop started', self.device.port)
        while not self.stop_thread.is_set():
            # Check command buffer
            cmd = None
            elapsed = None
            timeout_us = self.device.timeout*1E6
            try:
                cmd = self.cmd_Q.get(block=True, timeout=0.01)
            except Empty:
                pass
            else:
                serialio_logger.debug('%s write command popped', self.device.port)

            if cmd is not None:
                serialio_logger.debug('%s writing command "%s"',
                              self.device.port, repr(cmd))
                byte_cmd = cmd['cmd'].encode()
                keys = cmd.keys()
                use_EOL = 'respEOL' in keys
                use_len = 'respLen' in keys
                timed_out = False # Flag variable for timeout on response read

                if use_EOL + use_len != 1:
                    # Verify only one of length or EOL are given
                    raise ValueError(('Provide one of response'
                                     'length OR end.'))
                
                # Clear buffer and send command to the device
                self.ser_lock.acquire()
                self.ser.reset_input_buffer()
                self.ser.write(byte_cmd)
                timeout_start = datetime.now()

                # Read in expected response length, or until timed out
                if use_len:
                    rsp = None
                    resp_done = False
                    rsp_len = cmd['respLen']
                    while not resp_done:
                        resp = self.ser.read(rsp_len)
                        if isinstance(resp, bytes):
                            resp = resp.decode('utf-8')
                            serialio_logger.debug('%s buffer read %s',
                                            self.device.port,
                                            repr(resp))
                        if resp != '':
                            resp_done = True

                        elapsed = datetime.now()-timeout_start
                        if elapsed.microseconds > timeout_us:
                            timed_out = True
                            resp_done = True
                
                # Read in until EOL character recieved, or until timed out
                elif use_EOL:
                    resp = ""
                    resp_done = False
                    while not resp_done:
                        # Check timeout exceeded
                        elapsed = datetime.now() - timeout_start
                        if elapsed.microseconds > timeout_us:
                            resp_done = True
                            timed_out = True
                            break
                        if self.ser.in_waiting > 0:
                            timeout_start = datetime.now()
                            in_char = self.ser.read(1)
                            in_char = in_char.decode('utf-8')
                            # if in_char == bytes('', 'utf-8'):
                            #     in_char = in_char.decode('utf-8')
                            serialio_logger.debug('%s buffer read: %s',
                                          self.device.port,
                                          repr(in_char))

                            if in_char == cmd['respEOL']:
                                resp_done = True
                            else:
                                resp += in_char if isinstance(in_char, str) else in_char.decode('utf-8')

                # Timed out, returned empty string(s)
                if not resp:
                    serialio_logger.debug('%s command %s gave no response, timed out '
                                  'after %0.1fms', self.device.port, 
                                  repr(cmd['cmd']), (elapsed.microseconds/1000))
                    err_rsp = {'resp': "", 'cmd': cmd['cmd']}
                    self.rsp_Q.put(err_rsp)
                # Timed out, recieved partial or unexpected response
                elif timed_out:
                    serialio_logger.debug('%s command %s timed out before expected'
                                  ' response recieved. Recieved: %s', 
                                  self.device.port, repr(cmd['cmd']), 
                                  repr(resp))
                    err_rsp = {'resp': resp, 'cmd': cmd['cmd']}
                    self.rsp_Q.put(err_rsp)
                # Success
                else:
                    serialio_logger.debug('%s response success: %s',
                                  self.device.port,
                                  resp)
                    resp_Q = {'resp': resp, 'cmd': cmd['cmd']}
                    self.rsp_Q.put(resp_Q)
                self.ser_lock.release()
                self.cmd_Q.task_done()
            cmd = None
        serialio_logger.debug("%s cmd exec thread stopped.", self.device.port)

    def run(self):
        'Start `execution_loop` thread'
        self.stop_thread.clear()
        self.thread = Thread(target=self.execution_loop, args=())
        self.thread.start()

    def is_running(self):
        '''
        `execution_loop` run state.

        Returns
        -------
        bool
            Running
        '''
        return(not self.stop_thread.is_set())

    def stop(self):
        'Stop/join the `execution_loop` thread.'
        serialio_logger.debug("%s stopping cmd exec loop thread", self.device.port)
        self.stop_thread.set()
        self.thread.join()
        self.thread = None


class SerialDevice(object):
    '''
    Handles writing of commands and reading back of responses. 

    Parameters
    ----------
    port : str
        Serial device port name. E.g. "COM4".

    baud : int, default=9600
        Serial device baud rate

    timeout : float, default=0.2
        Time (seconds) to allow device to respond before commands timeout/fail.

    Attributes
    ----------
    port : str
        Serial device port name.

    baud : int
        Serial device baud rate.

    timeout : float
        Time (seconds) to allow device to respond before commands timeout/fail.
    
    isOpen : bool
        Serial device connection open.
    '''
    def __init__(self, port, baud=9600, timeout=0.2):
        self.baud = baud
        self.port = port
        self.timeout = timeout
        self.ser = serial.Serial(port=None, baudrate=baud)
        self.ser_lock = Lock()
        self.cmd_Q = Queue(maxsize=100)
        self.rsp_Q = Queue(maxsize=100)
        self.cmd_thread = CmdExecThread(self)
        self.isOpen = False
        serialio_logger.debug('Serial device initialized on %s' % port)

    def open(self):
        'Open the device serial port'
        self.ser_lock.acquire()
        self.ser.port = self.port
        self.ser.timeout = self.timeout
        try:
            self.ser.open()
        except serial.SerialException:
            raise ConnectionError('Could not open port %s' % self.port)
        self.ser_lock.release()
        self.cmd_thread.run()
        self.isOpen = True

    def close(self):
        'Close the device serial port'
        serialio_logger.debug('%s CLOSING. acquiring lock', self.port)
        self.ser_lock.acquire()
        serialio_logger.debug('%s CLOSING. Stopping thread', self.port)
        self.cmd_thread.stop()
        serialio_logger.debug('%s CLOSING. Closing serial', self.port)
        self.ser.close()
        self.ser_lock.release()
        self.isOpen = False
        serialio_logger.debug('%s CLOSED.', self.port)

    def write_cmd(self, cmd, rsp_len=None, EOL=None):
        r'''
        Send command to serial device, expect either a defined response length
        (`rsp_len`) **--OR--** a terminating character (`EOL`).

        Parameters
        ----------
        cmd : str
            String to send to serial device.
        rsp_len : int
            Number of characters to expect in response.
        EOL : str
            Expected response terminating character (E.g. LF or CR)

        Returns
        -------
        str
            Device response string. Empty string in case of response timeout.

        Raises
        ------
        ValueError
            if both `rsp_len` and `EOL` parameters are provided, or if neither
            is provided
        '''
        use_len = rsp_len is not None
        use_eol = EOL is not None

        if use_eol + use_len != 1:
            raise ValueError('Please one of EITHER rsp_len or EOL')

        cmd_dict = {'cmd': cmd, 'respEOL': EOL} if use_eol else {'cmd': cmd,
                                                            'respLen': rsp_len}
        # cmd_dict = {'cmd': cmd, 'respLen': rsp_len}
        self.cmd_Q.put(cmd_dict)
        self.cmd_Q.join()
        rsp = None

        try:
            rsp = self.rsp_Q.get(True, self.timeout*1.1)
        except TimeoutError:
            serialio_logger.warning("%s response Q timed out!", self.port)
        else:
            self.rsp_Q.task_done()

        if rsp == 'timeout':
            return ""
        return rsp

def list_ports():
    '''
    List available system serial ports.

    Returns
    -------
    list
        Serial port names
    '''

    ports_infos = ser_list_ports.comports()

    port_names = [i.name for i in ports_infos]

    return port_names