import os
import numpy as np
import socket
import struct
import time
import threading
from enum import Enum
import math
import queue
from numpy.lib.function_base import percentile
import serial
import select
from dotenv import load_dotenv

load_dotenv()

CLK_PRECISION       = 2 ** -16 #Perf Counter has Nanosecond precision

NTP_VERSION         = 3             #NTP version used by server
NTP_MAX_VERSION     = 4             #max supported NTP version
NTP_PORT            = 123

#constants for UTC calculations
SECONDS_IN_MINUTE   = 60.0
SECONDS_IN_HOUR     = 60.0 * SECONDS_IN_MINUTE
SECONDS_IN_HUNDRETH = 0.01
SECONDS_IN_DAY      = 24.0 * SECONDS_IN_HOUR
SECONDS_IN_MONTH    = [ 31.0 * SECONDS_IN_DAY, 28.0 * SECONDS_IN_DAY, 31.0 * SECONDS_IN_DAY,
                        30.0 * SECONDS_IN_DAY, 31.0 * SECONDS_IN_DAY, 30.0 * SECONDS_IN_DAY,
                        31.0 * SECONDS_IN_DAY, 31.0 * SECONDS_IN_DAY, 30.0 * SECONDS_IN_DAY,
                        31.0 * SECONDS_IN_DAY, 30.0 * SECONDS_IN_DAY, 31.0 * SECONDS_IN_DAY]
SECONDS_IN_YEAR     = 365 * SECONDS_IN_DAY

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

class LeapIndicator(Enum):
    """NTP Leap Indicator Enum

    Encodes the 4 leap indictaor states
    """
    NO_WARNING = 0
    LAST_MINUTE_61 = 1
    LAST_MINUTE_59 = 2
    ALARM = 3

class NmeaGpsMessages(Enum):
    """NMEA GPS Message types

    Encodes a type of GPS NMEA message,
    like GPGLL or GPGSA. Currently only supports 
    GPRMC and GPZDA
    """
    GPRMC = "$GPRMC"
    GPZDA = "$GPZDA"

class CurrentTime:
    """Current Time Class

    Stores reference time from an external source, along with the time
    it was received
    """
    def __init__(self):
        """Constructor

        Initializes local Variables
        """
        self.__gpsTime = 0
        self.__perfTime = 0
        self.__rootDelay = 0

    def setTime(self, newTime, rxTime):
        """Stores the reference time and records the time it 
        was recieved

        Parameters:
        time -- current time in UTC format
        rxTime -- performance counter value when NMEA sentence 
        was recieved via serial
        """
        if newTime != 0:
            mutex.acquire()
            self.__rootDelay = time.perf_counter() - rxTime + float(os.getenv("SERIAL_DELAY"))
            self.__gpsTime = newTime 
            self.__perfTime = time.perf_counter()
            mutex.release()
        
    
    def getTime(self):
        """Returns the current time, calculated from the reference 
        and elapsed time, as well as the reference time

        Returns:
        Current Time in UTC format, 
        Reference Time in UTC format,
        rootDelay in seconds
        """
        mutex.acquire()
        elapsedTime = self.__gpsTime + time.perf_counter() - self.__perfTime + self.__rootDelay
        refTime     = self.__gpsTime
        rootDelay   = self.__rootDelay
        mutex.release()

        return (elapsedTime, refTime, rootDelay)

    def getCurrentTime(self):
        """Returns just the current time,

        Returns:
        Current Time in UTC format, 
        """
        mutex.acquire()
        elapsedTime = self.__gpsTime + time.perf_counter() - self.__perfTime + self.__rootDelay
        mutex.release()

        return elapsedTime

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
        self.__leap = LeapIndicator.NO_WARNING
        
        if version > 0 and version <= NTP_MAX_VERSION:
            self.__version = np.int8(version)
        else:
            raise NtpException("Invalid NTP Version")
            
        
        if type(mode) is Mode:
            self.__mode = mode
        else: 
            raise NtpException("Invalid NTP mode")
        
        self.__stratum          = np.int8(1)                #8 bit int
        
        self.__poll             = np.int8(0)                #8 bit signed int
        self.__precision        = np.int8(0)                #8 bit signed int
        self.__rootDelay        = np.int32(0)               #32 bit signed fixed
        self.__rootDispersion   = np.int32(0)               #32 bit signed fixed

        if type(refId) is str:
            self.__refId        = self._stringToInt(refId)  #4 character string
        else: 
            raise NtpException("Invalid NTP refId")

        self.__refTimestamp     = np.uint64(0)              #64 bit unsigned fixed
        self.__originTimestamp  = np.uint64(0)              #64 bit unsigned fixed
        self.__rxTimestamp      = np.uint64(0)              #64 bit undsined fixed
        self.__txTimestamp      = np.uint64(0)              #64 bit unsigned fixed

    def fromBuffer(self, buffer):
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

        self.__leap             = LeapIndicator((unpacked[0] >> 6) & 0x3)
        self.__version          = np.int8((unpacked[0] >> 3) & 0x7)
        self.__mode             = Mode(unpacked[0] & 0x7)
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
        Transmit timeset is set when packet gets packed.
        *note* floating point must be UTC, whereas fixed must be NTP format

        Parameters:
        refTimestamp -- last time server was set by an external source (floating)
        originTimestamp -- the transmit time of the ntp client packet (fixed)
        rxTimestamp --- timestamp of when the client packet was recieved (floating)
        """
        self.__refTimestamp     = np.uint64(self._validateFloat(refTimestamp)) 
        self.__originTimestamp  = np.uint64(self._validateFloat(originTimestamp))
        self.__rxTimestamp      = np.uint64(self._validateFloat(rxTimestamp)) 

    def getTxTimestamp(self):
        """Get Transmitted timestamp

        Gets the time this packet was trasmitted

        Returns:
        Transmitted timestamp in fixed UTC format
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

        self.__txTimestamp = np.int64(self._floatToFixed(txTimestamp,32)) + self._UTC_TO_NTP

        try:
            packed = struct.pack(self._PACKET_FORMAT, 
                                int(self.__leap.value << 6 | self.__version << 3 | self.__mode.value),
                                int(self.__stratum),     
                                int(self.__poll),        
                                int(self.__precision),
                                int(self.__rootDelay),
                                int(self.__rootDispersion),
                                int(self.__refId),
                                (int(self.__refTimestamp) & 0xFFFFFFFF00000000) >> 32, 
                                int(self.__refTimestamp) & 0xFFFFFFFF,
                                (int(self.__originTimestamp) & 0xFFFFFFFF00000000) >> 32, 
                                int(self.__originTimestamp) & 0xFFFFFFFF,
                                (int(self.__rxTimestamp) & 0xFFFFFFFF00000000) >> 32, 
                                int(self.__rxTimestamp) & 0xFFFFFFFF,
                                (int(self.__txTimestamp) & 0xFFFFFFFF00000000) >> 32, 
                                int(self.__txTimestamp) & 0xFFFFFFFF)
        except struct.error:
            raise NtpException("Invalid NTP Fields")
        
        return packed

    def getMode(self):
        """Get NTP mode

        Gets the NTP mode of the packet

        Returns:
        Mode of the packet with the type Mode
        """
        return self.__mode

    def _validateFloat(self, floatOrFixed):
        """Validate Float

        Takes in a floating or fixed point number. If it is 
        fixed point, pass the result through. If floating convert to
        fixed. this currently only works for 64 bit fixed point, with 32
        bit integer and fractional bits

        """
        if type(floatOrFixed) is np.uint64:
            return floatOrFixed
        else:
            return self._floatToFixed(floatOrFixed, 32) + self._UTC_TO_NTP

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
        intPart = math.floor(floatNum)
        fracPart = int(abs(floatNum - int(floatNum)) * 2 ** fracBits)
        return intPart << fracBits | fracPart

    def _stringToInt(self, refString):
        """ string to Integer

        Converts a 4 character string to a 32 bit integer, for 
        use with the NTP Reference ID.

        Parameters:
        refString -- 4 character string representing the ref ID

        Returns:
        Refrence ID in np.uint32 format if a valid ID is passed in. 
        Otherwise returns 0 
        """
        refValue = np.uint32(0)

        if type(refString) is str:
            if len(refString) == 4:
                refValue = np.uint32((ord(refString[0]) << 24) | (ord(refString[1]) << 16) | (ord(refString[2]) << 8) | ord(refString[3]))
            elif len(refString) == 3:
                refValue = np.uint32((ord(refString[0]) << 24) | (ord(refString[1]) << 16) | (ord(refString[2]) << 8))
        return refValue
        
def secondsFromMonths(month):
    """Seconds from all months preceeding provided month

    Takes ina given month and calculates the sum of the number 
    of seconds in all preceeding months. Does not account for leap years

    Parameters:
    month -- the current month in integer format
    
    Returns:
    Seconds in all preceeding months, not including the current month
    """
    monthSeconds = 0

    for i in range(0, month-1):
        monthSeconds += SECONDS_IN_MONTH[i]
    
    return monthSeconds

def leapYearsSince1970(year, month):
    """Leap Years since 1970

    Returns how many leap years have occured between 1970 
    and supplied year. If past February this number in a 
    leap year it includes the current year, otherwise doesn't.

    Paramaters:
    year -- years since 1970 in integer format
    month -- the current month in integer format

    Returns:
    Number of leap days have occured
    """

    numLeapYears = np.int32((year + 2)  / 4)
    if month < 3:
        numLeapYears -= 1
    return numLeapYears

def nmeaChecksum(nmeaSentence):
    """NMEA Checksum

    Validates a NMEA sentence's checksum

    Parameters:
    nmeSentence -- NMEA sentence from GPS containing checksum

    Returns:
    True if checksum is correct, Flase otherwise
    """

    if len(nmeaSentence.split('*')) != 2:
        return False

    [data , checksum] = nmeaSentence.split('*')
    data = data[1:]

    calcChecksum = 0
    for char in data:
        calcChecksum ^= ord(char)

    return calcChecksum == int(checksum, 16)
    
def utcFromGps(nmeaSentence, nmeaSentenceName):
    """UTC timestamp from GPS NMEA Message

    Takes a NMEA message and extracts the UTC 
    time. Currently only supports GPRMC and
    GPZDA messages

    Parameters:
    nmeaSentence -- NMEA sentence from GPS containing UTC time
    nmeaSentenceName -- Type of NMEA sentence to parse (GPRMC or GPZDA)

    Returns:
    UTC timestamp if valid nmea message is sent in, 0 otherwise
    """ 
    
    valid =False
    utcTimestamp = 0
    if nmeaChecksum(nmeaSentence):
        nmeaFields  = nmeaSentence.split(',')

        if nmeaSentenceName == NmeaGpsMessages.GPRMC:
            valid       = True
            
            utcDate     = nmeaFields[9]

            utcDay      = int(utcDate[0:2])
            utcMonth    = int(utcDate[2:4])
            utcYear     = int(utcDate[4:6]) + 30 # year between 1970 and 2000
        elif nmeaSentenceName == NmeaGpsMessages.GPZDA:
            valid       = True

            utcDay      = int(nmeaFields[2])
            utcMonth    = int(nmeaFields[3])
            utcYear     = int(nmeaFields[4]) - 1970
            
        if valid == True:
            utcTime     = nmeaFields[1]

            utcHour     = int(utcTime[0:2])
            utcMinute   = int(utcTime[2:4])
            utcSeconds  = int(utcTime[4:6])
            utcHundreth = int(utcTime[7:9])

            #start building the timestamp from fields
            utcTimestamp    = (utcHour * SECONDS_IN_HOUR) + (utcMinute * SECONDS_IN_MINUTE) + utcSeconds
            utcTimestamp    += utcHundreth * SECONDS_IN_HUNDRETH
            utcTimestamp    += utcDay * SECONDS_IN_DAY 
            utcTimestamp    += secondsFromMonths(utcMonth)
            utcTimestamp    += utcYear * SECONDS_IN_YEAR
            utcTimestamp    += leapYearsSince1970(utcYear, utcMonth) * SECONDS_IN_DAY 
    else:
        print(nmeaSentence + " Failed Checksum")

    return utcTimestamp

taskQueue = queue.Queue()
utcTime = CurrentTime()
stopFlag = False

class IoThread(threading.Thread):
    """I/O Thread for server

    This thread handles input and output from the NTP
    Server. This includes both the Serial and optional 
    display
    """
    def __init__(self):
        """Default constructor"""
        threading.Thread.__init__(self)
    
    def run(self):
        global stopFlag, utcTime
        with serial.Serial(os.getenv("SERIAL_PORT"), baudrate=os.getenv("SERIAL_BAUD"), timeout=1) as ser:
            while stopFlag == False:
                sioMesage = ser.readline().decode('ascii')  
                startTime = time.perf_counter()    
                
                while sioMesage.split(',')[0] != os.getenv("NMEA_TYPE"):
                    sioMesage = ser.readline().decode('ascii')
                    startTime = time.perf_counter()

                utcTime.setTime(utcFromGps(sioMesage.replace("\r\n",""), NmeaGpsMessages(os.getenv("NMEA_TYPE"))), startTime)

                time.sleep(0.00001) #small sleep, prevents cpu redline

class RxThread(threading.Thread):
    """NTP Recieve Thread

    This thread handles recieving NTP requests and pushing them
    to a queue to be handled by the TxThread
    """
    def __init__(self, socket):
        """Default constructor"""
        threading.Thread.__init__(self)
        self.__socket = socket
    def run(self):
        global stopFlag, taskQueue, utcTime
        while stopFlag == False:
            rlist,wlist,elist = select.select([self.__socket], [], [], 1)
            if len(rlist) != 0:
                for temp in rlist:
                    try:
                        data,address = temp.recvfrom(1024)
                        taskQueue.put((data, address, utcTime.getCurrentTime()))
                    except socket.error as err:
                        print(err)
            time.sleep(0.00001) #small sleep, prevents cpu redline

class TxThread(threading.Thread):
    """NTP Transmit Thread

    This thread responds to NTP requests from clients
    """
    def __init__(self, socket):
        """Default constructor"""
        threading.Thread.__init__(self)
        self.__socket = socket
    def run(self):
        global stopFlag, taskQueue, utcTime
        while stopFlag == False:
            try:
                if taskQueue.empty() == False:
                    data, address, rxTime = taskQueue.get(timeout=1)
                    rxPacket = NtpPacket(3, Mode.CLIENT, "GPS")
                    try:
                        rxPacket.fromBuffer(data)
                        rxMode = rxPacket.getMode()

                        #special case of accepting symetric active packets, as that is what PDC send
                        #to upstream ntp server in an active directory enviroment
                        if rxMode == Mode.CLIENT or rxMode == Mode.SYMMETRIC_ACTIVE:
                            txPacket = NtpPacket(3, Mode.SERVER, "GPS")

                            txPacket.setPoll(os.getenv("NTP_POLL"))
                            txPacket.setPrecision(CLK_PRECISION)

                            txTime,refTime,rootDelay = utcTime.getTime()

                            txPacket.setRootValues(rootDelay, float(os.getenv("SERIAL_ERROR")))
                            txPacket.setTimestamps(refTime, rxPacket.getTxTimestamp(), rxTime)

                            self.__socket.sendto(txPacket.getBuffer(txTime), address)
                    except NtpException:
                        print("Bad NTP packet from client")
                    
                time.sleep(0.00001) #small sleep, prevents cpu redline
            except queue.Empty:
                continue


socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
socket.bind((os.getenv("NTP_ADDRESS"), NTP_PORT))

ioThread = IoThread()
ioThread.start()

txThread = TxThread(socket)
txThread.start()

rxThread = RxThread(socket)
rxThread.start()

while True:
    try:
        time.sleep(0.5)
    except KeyboardInterrupt:
        print("Exiting...")
        stopFlag = True
        ioThread.join()
        txThread.join()
        rxThread.join()
        print("Exited")
        break