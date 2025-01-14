import busio
import digitalio
import board
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn
import threading
import time
import RPi.GPIO as GPIO
import socket
from datetime import datetime, timedelta


def networkingSetup():
    """Initialize sockets and connect to them"""
    print("Network setup...")
    TCP_IP = "102.39.247.225"
    TCP_PORT = 5005

    global BUFFER_SIZE, ENABLED, networkSocket, timeout
    ENABLED = True
    BUFFER_SIZE = 1024
    networkSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    connected = False
    timeout = 10
    timestamp = datetime.now + timedelta(hours=2)
    timestamp = timestamp.strftime("%H:%M:%S")
    while not connected:
        try:
            networkSocket.connect((TCP_IP, TCP_PORT))
            connected = True
        except OSError:
            print(f"{timestamp}: Failed to connect to {TCP_IP} on Port {TCP_PORT}... Retrying in {timeout} seconds.")
            time.sleep(timeout)
    print("Done.")


def setup():
    """Initialize spi interface, GPIO pins and add interrupts"""
    print("Board setup...")
    # create the spi bus
    spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)

    # create the cs (chip select)
    cs = digitalio.DigitalInOut(board.D5)

    # create the mcp object
    mcp = MCP.MCP3008(spi, cs)

    global temp, light
    temp = AnalogIn(mcp, MCP.P1)
    light = AnalogIn(mcp, MCP.P2)

    global samplingTimes, currentSamplingTime, lastSampleTime
    samplingTimes = [10, 5, 1]
    currentSamplingTime = 0
    lastSampleTime = datetime.now()

    GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(17, GPIO.FALLING, callback=changeSamplingTime, bouncetime=200)
    print("Done.")


def changeSamplingTime(channel):
    """Cycle between 1, 5 and 10 second sampling intervals.

    :param channel: Required param for this method to act as an interupt
    :type channel: n/a
    """
    global samplingTimes, currentSamplingTime
    print(
        f"Sampling time will be changed from {samplingTimes[currentSamplingTime]}s to {samplingTimes[(currentSamplingTime + 1) % 3]}s after the next sample"
    )
    currentSamplingTime = (currentSamplingTime + 1) % 3


def readValues():
    """Read the value from the temperature sensor and ldr, compile them into a data packet and send them to the server."""
    global temp, light, samplingTimes, currentSamplingTime, networkSocket, ENABLED, lastSampleTime
    while 1:
        if not ENABLED:
            continue
        sleepTime = samplingTimes[currentSamplingTime]
        # print(f"{str(round(time.time()-startTime))}s\t{str(temp.value)}\t\t{str(round((temp.voltage-0.5)/0.01, 2))}°C\t{str(light.value)}")
        now = datetime.now() + timedelta(hours=2)
        timestamp = now.strftime("%H:%M:%S")
        #tempValue = str(temp.value)
        tempVolts = str(round((temp.voltage-0.5)/0.01, 2))
        lightVal = str(light.value)
        dataStr = f"SENSORS#{timestamp}${tempVolts}${lightVal}"
        print(dataStr)
        sendToSocket(dataStr)        
        lastSampleTime = now
        time.sleep(sleepTime)

def sendToSocket(unencodedData):
    global networkSocket, timeout
    sent = False
    timestamp = datetime.now + timedelta(hours=2)
    timestamp = timestamp.strftime("%H:%M:%S")
    while not sent:
        try:
            networkSocket.send(unencodedData.encode())
            sent = True
        except BrokenPipeError:
            print(f"{timestamp}: Timed out...Retrying in {timeout} seconds")
            time.sleep(timeout)
        
def sendStatus():
    """Compile a timestamp and the status of the client into a datapack and send to server."""
    global ENABLED, lastSampleTime, networkSocket
    print("Sending Status")
    timestamp = lastSampleTime.strftime("%H:%M:%S")
    dataStr = f"STATUS#{timestamp}${ENABLED}"
    sendToSocket(dataStr)
    print("Sent Status... " + dataStr)

def disableSensors():
    """Disable the sensor reading and sending. Send new status to server."""
    global ENABLED
    ENABLED = False
    print("Disabling...")
    sendStatus()


def enableSensors():
    """Enable sensor reading and sending. Send new status to server."""
    global ENABLED
    ENABLED = True
    print("Enabling...")
    sendStatus()


if __name__ == "__main__":

    # Run setups
    setup()
    networkingSetup()
    global startTime, networkSocket, BUFFER_SIZE

    # Create and start threads to read and send sensor values
    x = threading.Thread(target=readValues)
    x.start()
    try:
        while 1:

            # Wait to recieve a packet
            data = networkSocket.recv(BUFFER_SIZE)
            serverMessage = data.decode()

            # Decode packet and act accordingly
            if serverMessage == "CHECK":
                sendStatus()
            elif serverMessage == "SENDOFF":
                disableSensors()
            elif serverMessage == "SENDON":
                enableSensors()
            elif serverMessage == "CYCLE":
                changeSamplingTime()
    except KeyboardInterrupt:
        pass
    finally:
        x.join()
