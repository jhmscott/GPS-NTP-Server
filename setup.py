import serial.tools.list_ports
import serial
import time
from netifaces import interfaces, ifaddresses, AF_INET

def checkInput():
    try:
        return int(input())
    except ValueError:
        return -1

def getGpsPort(ports):
    print("Which port you will be connecting to the GPS?\r\n")

    for i in range(0, len(ports)):
        port, desc, hwid = ports[i]
        print("{} - {}: {}".format(i, port, desc))
    return checkInput()

def getBaudRate():
    print("\r\nEnter baud Rate used to communicate with GPS")
    
    return checkInput()

def getNmeaType():
    print("\r\nWhat type of NMEA sentence does your GPS use to supply the time?\r\n")
    print("0 - $GPRMC")
    print("1 - $GPZDA")

    return checkInput()

def getPoll():
    print("\r\nWhat polling value should be used? (enter 10 if you don't know)")
    
    return checkInput()

def getAddress(addresses):
    print("\r\nWhich IP address will this server be listening for requests?\r\n")
    
    for i in range(0, len(addresses)):
        print("{} - {}".format(i, addresses[i]))

    return checkInput()

def setup():
    ports = sorted(serial.tools.list_ports.comports())

    gpsPort = getGpsPort(ports)

    while gpsPort < 0 or gpsPort >= len(ports):
        print("\r\nInvalid Port")
        gpsPort = getGpsPort(ports)

    baudRate = getBaudRate()

    while baudRate < 0:
        print("\r\nInvalid Baud Rate")
        baudRate = getBaudRate()

    nmeaType = getNmeaType()

    while nmeaType != 0 and nmeaType != 1:
        print("\r\nInvalid nmeaType")
        nmeaType = getNmeaType()

    addresses = []

    for ifaceName in interfaces():
        ifAddress = [i['addr'] for i in ifaddresses(ifaceName).setdefault(AF_INET, [{'addr':'No IP addr'}] )][0]
        
        if ifAddress != 'No IP addr':
            addresses.append(ifAddress)

    address = getAddress(addresses)

    while address < 0 or address >= len(addresses):
        print("\r\nInvalid IP address")
        address = getAddress(addresses)

    poll = getPoll()

    while poll < 0:
        print("\r\nInvalid Poll")
        poll = getPoll()

    print("\r\nOne final step. Connect a loopback adapter to your serial port.")
    print("If using a raspberry pi connect a jumper between the RX and TX pins")
    print("When this is ready, press any key...")

    input()

    serPort, desc, hwId = ports[gpsPort]
    sampleText = open("GPS Sample Data.txt", "r").read()
    delays = []
    numLines = len(sampleText.split("\r\n"))

    with serial.Serial(serPort, baudrate=baudRate, timeout=1) as ser:
        for i in range(0, 30):    
            ser.write(sampleText.encode())
            txTime = time.perf_counter()

            ser.readline()
            #store the time it took to read the line
            delays.append(time.perf_counter() - txTime) 

            #read remaining lines 
            for j in range(0, numLines - 1):
                ser.readline()

    delays = sorted(delays)
    minDelay = delays[0]
    maxDelay = delays[-1]

    #calculate Serial Delay and error
    meanDelay = (maxDelay + minDelay) / 2
    delayErr = maxDelay - meanDelay 

    #build enviroment file
    env = open(".env", "w")
    env.write("SERIAL_PORT=" + serPort + "\n")
    env.write("SERIAL_BAUD=" + str(baudRate) + "\n")
    env.write("SEIRAL_DELAY=" + str(meanDelay)+ "\n")
    env.write("SERIAL_ERROR=" + str(delayErr)+ "\n")
    env.write("NMEA_TYPE=" +  ("$GPZDA" if nmeaType == 1 else "$GPRMC") + "\n\n")
    env.write("NTP_ADDRESS=" + addresses[address] + "\n")
    env.write("NTP_POLL=" + str(poll) + "\n")
    env.close()

    print("Setup Complete")

try:
    setup()
except KeyboardInterrupt:
    exit()