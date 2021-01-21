# GPS-NTP-Server

Simple Python based Stratum 1 NTP server that uses a NMEA GPS as the reference source

Compatible with both windows and linux, if configured correctly.

## General Setup
Create a file called .env in the project directory and paste the following into it.

SERIAL_PORT=\
SERIAL_BAUD=\
SERIAL_DELAY=\
SERIAL_ERROR=\
NMEA_TYPE=

NTP_ADDRESS=\
NTP_POLL=

Enter the port and baud rate that are used by your GPS module. NMEA_TYPE should be set to the type of NMEA message that you want to get the time data. Currently $GPRMC and $GPZDA are supported. Finally, SERIAL_DELAY is the delay between the transmisson and recieval of the NMEA message over serial. 

The NTP address should be set to the IP address you are listening for requests on. Poll should be set to your desired poll value (use 10 if you don't Know)
I hope to later to automate the setup steps with a script.

## Starting the Server
If you just want to test the server, you can run python ntpServer.py from a command window. This will fail if python doesn't have access to the Network. Check that you've allowed python through the firewall for ntp traffic (port 123) and ensure no other programs are already using that port (This will likely be w32tm under Windows and ntpd or chronyd under Linux). You will need to stop these services to run the server.

## Running as a service
I personally use pm2 in order to run the program as a service (https://pm2.keymetrics.io/) It is incredibly convenient, and even provides logging. However, it is not required and you can set it up any way you would like.

