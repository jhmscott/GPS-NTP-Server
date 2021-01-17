import socket
import struct
import time
import threading
from enum import Enum
import math
import Queue

GPS_POLL = 1.0              #1Hz GPS module is used
CLK_PRECISION = 10 ** -9    #Perf Counter has Nanosecond precision
NTP_VERSION = 3

mutex = threading.Lock()

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

class CurrentTime:
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
        mutex.acquire()
        self.__gpsTime = time
        self.__perfTime = time.perf_counter()
        mutex.release()
        
    
    def getTime(self):
        """Returns the current time, calculated from the reference 
        and elapsed time, as well as the reference time

        Returns:
        Current Time in UTC format, 
        Reference Time in UTC format
        """
        mutex.acquire()
        elapsedTime = self.__gpsTime + time.perf_counter - self.__perfTime
        refTime = self.__gpsTime
        mutex.release()

        return (elapsedTime, refTime)
        

class NtpPacket: 
    """NTP Packet Class

    Stores packs and unpacks all the ntp packet fields
    """

    _PACKET_FORMAT = "!B B B b 11I"

    def __init__(self, version, mode, refId):
        """Constructor

        Initializes local Variables

        Paramaters:
        version -- the NTP version the packet is using (1,2,3,4)
        mode -- the NTP mode (see Mode Enum)
        refID -- For a Stratum 1 or primary server, this is a 4
        character pneumonic that represents the time source

        Code    External Reference Source
        -------------------------------------------------------
        LOCL    uncalibrated local clock 
        CESM    calibrated Cesium clock
        RBDM    calibrated Rubidium clock
        PPS     calibrated quartz clock or other pulse-per-second source
        IRIG    Inter-Range Instrumentation Group
        ACTS    NIST telephone modem service
        USNO    USNO telephone modem service<
        PTB     PTB (Germany) telephone modem service
        TDF     Allouis (France) Radio 164 kHz
        DCF     Mainflingen (Germany) Radio 77.5 kHz
        MSF     Rugby (UK) Radio 60 kHz
        WWV     Ft. Collins (US) Radio 2.5, 5, 10, 15, 20 MHz
        WWVB    Boulder (US) Radio 60 kHz
        WWVH    Kauai Hawaii (US) Radio 2.5, 5, 10, 15 MHz 
        CHU     Ottawa (Canada) Radio 3330, 7335, 14670 kHz 
        LORC    LORAN-C radionavigation system
        OMEG    OMEGA radionavigation system
        GPS     Global Positioning Service
        """
        self.__leap = LeapInictaor.NO_WARNING
        self.__version = version
        self.__mode = mode
        self.__stratum = 1
        
        self.__poll = 0
        self.__precision = 0
        self.__rootDelay = 0
        self.__rootDispersion = 0
        self.__refId = refId

        self.__refTimestamp = 0
        self.__originTimestamp = 0
        self.__rxTimestamp = 0
        self.__txTimestamp = 0

    def setPoll(self, poll):
        """Set Poll
        
        Sets Poll time for packet

        Parameters:
        poll -- poll time for packet
        """
        self.__poll = poll
    
    def setPrecision(self, precisionFloat):
        """Set Precision

        Sets the precision of the server in the NTP Packet.
        This is the base2 log of the actual precision, and is
        stored as an 8 bit signed integer
        
        Parameters:
        precisionFloat -- floating point value of the precision
        """
        self.__precision = round(math.log2(precisionFloat))

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
        return intPart << fracBits | fracPart

   

