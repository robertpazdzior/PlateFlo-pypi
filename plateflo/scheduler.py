'''
Scheduler
=========
Module for scheduling and executing PlateFlo perfusion system events.

Copyright Robert Pazdzior 2020-2021

This file may be distributed under the terms of the GNU GPLv3+ license.
'''

import logging
from datetime import datetime, timedelta

# TODO implement threaded schedule monitoring/execution
# from threading import Thread, Lock, Event

sched_logger = logging.getLogger('scheduler')

class Scheduler():
    '''
    Event schedule handler. Schedules, monitors, and executes events
    
    Attributes
    ----------
    events : list
        Unexecuted future event objects.

    event_history : list
        Previous triggered event objects.
    '''
    def __init__(self):
        self.events = []
        self.event_history = []
        self.lastID = 0  # Event ID, to reference specific event

    def add_event(self, event):
        '''
        Inserts scheduled event into the event queue.
        
        Parameters
        ----------
        event : SingleEvent, RecurringEvent
            :class:`SingleEvent` or :class:`RecurringEvent` object

        Returns
        -------
        int
            Event identifier. Can be used to remove event with :meth:`remove_event`
        '''
        _event = event
        if not _event.eventID:
            eventID = self.lastID + 1
            self.lastID = eventID
            _event.eventID = eventID
        else:
            eventID = _event.eventID

        next_dateTime = _event.dateTime
        self.events.append(
            {
                'eventID': eventID,
                'dateTime': next_dateTime,
                'event': _event
            }
        )
        sched_logger.debug('Added - %s', _event)
        self.events = sorted(self.events,
                                 key = lambda i: (i['dateTime'], i['eventID']))
        return _event.eventID

    def remove_event(self, eventID):
        '''
        Removes the selected event from the scheduler queue.
        
        Parameters
        ----------
        eventID : int
            Unique event identifier.
        '''
        e = next(event for event in self.events if event['eventID'] == eventID)
        sched_logger.debug('Removed - %s' % e['event'])
        self.events.remove(e)

    def monitor(self):
        '''
        **Call frequently from the main script loop!**

        Checks if events are due to trigger and transfers triggered events
        to the event history.
        Reschedules recurring events if necessary.
        '''
        if len(self.events):
            queued = self.events[0]
        else:
            return
        if queued['dateTime'] <= datetime.now():
            self.event_history.append(queued)
            self.events.remove(queued)

            sched_logger.debug('Triggered - %s', queued['event'])
            recurrance = queued['event'].trigger() # Recuring returns new event
            if recurrance:
                self.add_event(recurrance)

class SingleEvent():
    '''
    Simple event object, executes once at the specified time.
    
    Parameters
    ----------
    dateTime : datetime
               Scheduled execution start time

    task : function pointer
            Function to excecute at scheduled time

    kwargs
        keyword arguments passed to task
    
    '''
    def __init__(self, dateTime, task, _eventID = None, *args, **kwargs):
        self.eventType = "Single"
        self.triggered = False
        self.dateTime = dateTime
        self._task = task
        self._taskargs = args
        self._taskkwargs = kwargs
        self.eventID = _eventID

    def trigger(self):
        'Execute the event task.'
        self._task(*self._taskargs, **self._taskkwargs)
        return None

    def __str__(self):
        time_fmt = format(self.dateTime, "%Y/%m/%d %H:%M:%S")
        msg_str = ('One-time event (%s) sched=%s task=%s args=%s kwargs=%s') % (self.eventID, time_fmt, self._task.__name__,
                                self._taskargs, self._taskkwargs)
        return msg_str

class RecurringEvent():
    '''
    Event triggered at the specified interval w/ optional start time OR delay.

    Parameters
    ----------
    interval : float
        Recurrance interval, in minutes

    task : function pointer
        Function to excute at scheduled interval

    start_time : datetime, optional
        First occurance at specified time. Excludes `delay_m`

    stop_time : datetime, optional
        Terminate recurrance after this time

    delay_m : float, float
        First occurance only after this number of minutes. Excludes `start_time`.

    args
        Positional arguments passed to task

    kwargs
        Keyword arguments passed to task

    Raises
    ------
    Exception
        if both `start_time` and `delay_m` parameters are provided.
    '''
    def __init__(self, interval, task, start_time = None, stop_time = None,
                 delay_m = None, _eventID = None, *args, **kwargs):
        self.eventType = "Recurring"
        self.interval = interval
        self._task = task
        self._start_time = start_time
        self._stop_time = stop_time
        self._delay_m = delay_m
        self.eventID = _eventID
        self._taskkwargs = kwargs
        self._taskargs = args
        self.dateTime = None

        self.set_sched_dateTime()

    def set_sched_dateTime(self):
        # Argument check
        if self._delay_m and self._start_time:
            raise Exception('Enter one of "delay_m" OR "start_time", not both.')
        
        # Simple interval
        if not (self._start_time or self._delay_m):
            self.dateTime = datetime.now() + timedelta(minutes=self.interval)

        # Start after delay (minutes)
        elif self._delay_m:
            if not self.eventID:
                self.dateTime = datetime.now() + timedelta(minutes=self._delay_m)
            else:
                self.dateTime = datetime.now() + timedelta(minutes=self.interval)
        
        # Start at specified time
        elif self._start_time:
            # Handle recurrance (start_time is in the past)
            new_start = self._start_time
            while new_start < datetime.now():
                new_start += timedelta(minutes=self.interval)
            self.dateTime = new_start

    def trigger(self):
        if self._stop_time and datetime.now() >= self._stop_time:
            return None

        self._task(*self._taskargs, **self._taskkwargs)
        next_event = RecurringEvent(self.interval, self._task, self._start_time,
                                    self._stop_time, self._delay_m, 
                                    self.eventID, *self._taskargs,
                                    **self._taskkwargs)
        return next_event

    def __str__(self):
        time_fmt = format(self.dateTime, "%Y/%m/%d %H:%M:%S:%f")
        msg_str = 'recurring event (%i), interval_minutes=%.3f next_sched=%s, task=%s args=%s kwargs=%s' % (self.eventID, self.interval, time_fmt, self._task.__name__,
                                self._taskargs, self._taskkwargs)
        if self._start_time:
            msg_str += ', start_time=%s' % format(self._start_time, "%Y/%m/%d %H:%M:%S")
        if self._delay_m:
            msg_str += ', delay=%fmin' % self._delay_m
        return msg_str

def DailyEvent(task, hh = 0, mm = 0, s = 0, *args, **kwargs):
    '''
    Wrapper around :class:`RecurringEvent` for convenient daily task execution.

    Parameters
    ----------
    hh : int
        Time of day, hour [0-23]
    
    mm : int, default = 0
        Time of day, minute [0-59]

    s : int, default = 0
        Time of day, seconds [0-59]

    task : function pointer
        Function executed at scheduled time

    args
        Add positional arguments passed to task

    kwargs
        Additional keyword arguments passed to task

    Returns
    -------
    RecurringEvent
        Daily recurring event.
    '''   
    today = datetime.today()
    dateTime = datetime(today.year,
                        today.month,
                        today.day,
                        hour=hh,
                        minute=mm,
                        second=s)
    event = RecurringEvent(interval=60*24, task=task, start_time=dateTime,
                           *args, **kwargs)
    return event
