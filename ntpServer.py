import socket
import struct
import time
from enum import Enum

GPS_POLL 

class Mode(Enum):
    """NTP Mode Enum

    Encodes the 7 possible NTP modes
    """
    UNSPECIFIED = 0
    SYMMETRIC_ACTIVE = 1
    SYMMETRIC_PASSIVE = 2
    CLIENT = 3
    SERVER = 4
    BROADCAST = 5
    RESERVED_CONTROL = 6
    RESERVED_PRIVATE = 7

class LeapInictaor(Enum):
    """NTP Leap Indicator Enum

    Encodes the 4 leap indictaor states
    """
    NO_WARNING = 0
    LAST_MINUTE_61 = 1
    LAST_MINUTE_59 = 2
    ALARM = 3

class currentTime:
    """Current Time Class

    Stores reference rime from an external source, along with the time
    it was recieved
    """
    def __init__(self):
        """Constructor

        Initializes local Variables
        """
        self.__gpsTime = 0
        self.__perfTime = 0

    def setTime(self, time):
        """Stores the reference time and records the time it 
        was recieved

        Parameters:
        time -- current time in UTC format
        """
        self.__gpsTime = time
        self.__perfTime = time.perf_counter()

    def getRefTime(self):
        """Gets the reference time, the last updated time

        Returns:
        Reference time in UTC format
        """
        return self.__gpsTime
    
    def getTime(self):
        """Returns the current time, calculated from the reference 
        and elapsed time

        Returns:
        Current Time in UTC format
        """
        elapsedTime = time.perf_counter - self.__perfTime
        return (self.__gpsTime + elapsedTime)

class NtpPacket: 
    """NTP Packet Class

    Stores all the ntp packet fields
    """

    _PACKET_FORMAT = "!B B B b 11I"

    def __init__(self, version, mode, txTimestamp):
        self.leap = LeapInictaor.NO_WARNING
        self.version = version
        self.mode = mode
        self.stratum = 1
        
        self.poll = 0
        self.precision = 0
        self.rootDelay = 0
        self.rootDispersion = 0
        self.refId = ""

        self.refTimestamp = 0
        self.originTimestamp = 0
        self.rxTimestamp = 0
        self.txTimestamp = txTimestamp
    
    def _floatToFixed(self, floatNum, fracBits):
        """Floating point to fixed point conversion

        Converts a standard floating point number to fixed point
        with a provided number of fractional bits 

        Parameters:
        floatNum -- floating point number to convert
        fracBits -- number of fractional bits in desired fixed point result

        Returns:
        Original input in fixed point
        """
        intPart = int(floatNum)
        fracPart = int(abs(floatNum - int(floatNum)) * 2 ** fracBits)
        return intPart << n | fracPart

    

