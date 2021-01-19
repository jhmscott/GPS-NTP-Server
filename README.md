# GPS-NTP-Server

Simple Python Based Stratum 1 NTP server that uses a NMEA GPS as the reference source

Compatible with both windows and linux, if configured correctly

Create a file called .env and paste the following into it

SERIAL_PORT=
SERIAL_BAUD=
SERIAL_DELAY=
NMEA_TYPE=

Enter the port and baud rate that are used by your GPS module. NMEA_TYPE should be set to the type of NMEA message that you want to get the time data. Currently $GPRMC and $GPZDA are supported. Finally, SERIA_DELAY is the delay between the transmisson and recieval of the NMEA message over serial. I hope to later automate finding this with a script