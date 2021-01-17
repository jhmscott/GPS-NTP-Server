import numpy as np
import socket
import struct
import time
import threading
from enum import Enum
import math
import Queue
import datetime

GPS_POLL = 1.0                              #1Hz GPS module is used
CLK_PRECISION = 10 ** -9                    #Perf Counter has Nanosecond precision
NTP_VERSION = 3                             #NTP version used by server
NTP_MAX_VERSION = 4                         #max supported NTP version

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


class NtpException(Exception):
    """Exception raised by NTP Packet module
    
    Indicates an error packing, unpacking or constructing a packet
    """
    pass


class NtpPacket: 
    """NTP Packet Class

    Stores packs and unpacks all the ntp packet fields
    """

    _PACKET_FORMAT = "!B B B b 11I"
    _UTC_TO_NTP = np.uint64(2208988800 << 32)    #time between beginnning of NTP and UTC epoch in fixed

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

        Raises:
        NtpException -- in case invalid or incomplete ntp fields
        """
        self.__leap = LeapInictaor.NO_WARNING
        
        if version > 0 and version < 5:
            self.__version = np.int8(version)
        else:
            raise NtpException("Invalid NTP Version")
            
        
        if type(mode) is Mode:
            self.__mode = mode
        else: 
            raise NtpException("Invalid NTP mode")
        
        self.__stratum          = np.int8(1)    #8 bit int
        
        self.__poll             = np.int8(0)    #8 bit signed int
        self.__precision        = np.int8(0)    #8 bit signed int
        self.__rootDelay        = np.int32(0)   #32 bit signed fixed
        self.__rootDispersion   = np.int32(0)   #32 bit signed fixed
        self.__refId            = refId         #4 character string

        self.__refTimestamp     = np.uint64(0)  #64 bit unsigned fixed
        self.__originTimestamp  = np.uint64(0)  #64 bit unsigned fixed
        self.__rxTimestamp      = np.uint64(0)  #64 bit undsined fixed
        self.__txTimestamp      = np.uint64(0)  #64 bit unsigned fixed

    def __init__(self, buffer):
        """Constructor

        Constructs an NTP pcaket from a valid buffer

        Parameter:
        buffer -- buffer containing NTP packet

        Raises:        
        NtpException -- in case invalid or incomplete ntp fields
        """
        try:
            unpacked = struct.unpack(self._PACKET_FORMAT, buffer[0:struct.calcsize(self._PACKET_FORMAT)])
        except struct.error:
            raise NtpException("Invalid NTP fields")

        self.__leap             = np.int8((unpacked[0] >> 6) & 0x3)
        self.__version          = np.int8((unpacked[0] >> 3) & 0x7)
        self.__mode             = np.int8(unpacked[0] & 0x7)
        self.__stratum          = np.int8(unpacked[1])
        self.__poll             = np.int8(unpacked[2])
        self.__precision        = np.int8(unpacked[3])
        self.__rootDelay        = np.int32(unpacked[4])
        self.__rootDispersion   = np.int32(unpacked[5])
        self.__refId            = np.int32(unpacked[6])
        self.__refTimestamp     = np.uint64((unpacked[7] << 32) | unpacked[8])
        self.__originTimestamp  = np.uint64((unpacked[9] << 32) | unpacked[10])
        self.__rxTimestamp      = np.uint64((unpacked[11] << 32) | unpacked[12])
        self.__txTimestamp      = np.uint64((unpacked[13] << 32) | unpacked[14])            

    def setPoll(self, poll):
        """Set Poll
        
        Sets Poll time for packet

        Parameters:
        poll -- poll time for packet
        """
        self.__poll = np.int8(poll)
    
    def setPrecision(self, precisionFloat):
        """Set Precision

        Sets the precision of the server in the NTP Packet.
        This is the base2 log of the actual precision, and is
        stored as an 8 bit signed integer
        
        Parameters:
        precisionFloat -- floating point value of the precision
        """
        self.__precision = np.int8(round(math.log2(precisionFloat)))
    
    def setRootValues(self, rootDelay, rootDispersion):
        """Set Root Values

        Sets the root delay and root dispersion values of the packet

        Parameters:
        rootDelay -- root delay value in floating 
        rootDispersion -- root dispersion value in floating
        """
        self.__rootDelay = np.int32(self._floatToFixed(rootDelay, 16))
        self.__rootDispersion = np.int32(self._floatToFixed(rootDispersion, 16))

    def setTimestamps(self, refTimestamp, originTimestamp, rxTimestamp):
        """Set Timestamps

        Sets the reference, origin and recieve timestamps. 
        Transmit timeset is set when packet gets packed

        Parameters:
        refTimestamp -- last time server was set by an external source
        originTimestamp -- the transmit time of the ntp client packet
        rxTimestamp --- timestamp of when the client packet was recieved
        """
        self.__refTimestamp     = np.uint64(self._floatToFixed(refTimestamp, 32)) + self._UTC_TO_NTP
        self.__originTimestamp  = np.uint64(self._floatToFixed(originTimestamp, 32)) + self._UTC_TO_NTP
        self.__rxTimestamp      = np.uint64(self._floatToFixed(rxTimestamp, 32)) + self._UTC_TO_NTP

    def getTxTimestamp(self):
        """Get Transmitted timestamp

        Gets the time this packet was trasmitted

        Returns:
        Transmitted timestamp in UTC format
        """
        return self.__txTimestamp
    
    def getBuffer(self, txTimestamp):
        """Get Packet Buffer

        Converts this packet to a buffer that can be transmitted via
        UDP.

        Parameters:
        txTimestamp -- the current timestamp, this gets placed in the packet 
        before it is packed into the buffer

        Returns:
        Buffer representing the packet

        Raises:
        NtpException -- in case invalid or incomplete ntp fields
        """

        self.__txTimestamp = np.int64(self._floatToFixed(txTimestamp)) + self._UTC_TO_NTP

        try:
            packed = struct.pack(self._PACKET_FORMAT, 
                                int(self.__leap.value << 6 | self.__version << 3 | self.__mode.value),
                                int(self.__stratum),     
                                int(self.__poll),        
                                int(self.__precision),
                                int(self.__rootDelay),
                                int(self.__rootDispersion),
                                int(self.__refId),
                                int((self.__refTimestamp & 0xFFFFFFFF00000000) >> 32), 
                                int(self.__refTimestamp & 0xFFFFFFFF),
                                int((self.__originTimestamp & 0xFFFFFFFF00000000) >> 32), 
                                int(self.__originTimestamp & 0xFFFFFFFF),
                                int((self.__rxTimestamp & 0xFFFFFFFF00000000) >> 32), 
                                int(self.__rxTimestamp & 0xFFFFFFFF),
                                int((self.__txTimestamp & 0xFFFFFFFF00000000) >> 32), 
                                int(self.__txTimestamp & 0xFFFFFFFF))
        except struct.error:
            raise NtpException("Invalid NTP Fields")
        
        return packed
        
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

taskQueue = Queue.Queue()
utcTime = CurrentTime()



