import os
import sys
import time
import struct
#import signal
from mini_rv32ima_decoder import *
from default64mbdtc import *

# Constants
MINI_RV32_RAM_SIZE = 64 * 1024 * 1024
MINIRV32_RAM_IMAGE_OFFSET = 0x80000000
MINIRV32_MMIO_RANGE = lambda n: 0x10000000 <= n < 0x12000000

# Global variables
core = None
fail_on_all_faults = False

SET_RAM_SIZE(MINI_RV32_RAM_SIZE)

def MINIRV32_POSTEXEC(pc, ir, retval):
    if retval > 0:
        if fail_on_all_faults:
            print("FAULT")
            return 3
        else:
            retval = HandleException(ir, retval)
    return retval

def MINIRV32_HANDLE_MEM_STORE_CONTROL(addy, val):
    if HandleControlStore(addy, val):
        return val
    else:
        return None

def MINIRV32_HANDLE_MEM_LOAD_CONTROL(addy):
    return HandleControlLoad(addy)

def MINIRV32_OTHERCSR_WRITE(image, csrno, value):
    HandleOtherCSRWrite(image, csrno, value)

def MINIRV32_OTHERCSR_READ(image, csrno):
    return HandleOtherCSRRead(image, csrno)

# Functions

#
# OS specific
#
if os.name == "nt":
    import msvcrt

    def CaptureKeyboardInput():
        #Poorly documented tick: Enable VT100 Windows mode.
        os.system(" ")
        pass

    def IsKBHit():
        return 1 if msvcrt.kbhit() else 0

    def ReadKBByte():
        char =  ord(msvcrt.getch()) 
        return char
    
if os.name == "posix":
    import select, termios

    def CaptureKeyboardInput():
        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)  # (For restoring later.)

        # Create new unbufferd terminal settings to use:
        new_term = termios.tcgetattr(fd)
        new_term[3] = (new_term[3] & ~termios.ICANON & ~termios.ECHO)
        termios.tcsetattr(fd, termios.TCSAFLUSH, new_term)

    def IsKBHit():
        results = select.select([sys.stdin], [], [], 0)
        return results[0] != []

    def ReadKBByte():
        return ord(sys.stdin.read(1))

def SimpleReadNumberInt(number, defaultNumber):
    if not number or not number[0]:
        return defaultNumber
    radix = 10
    if number[0] == '0':
        nc = number[1]
        number = number[2:]
        if nc == '0':
            return 0
        elif nc == 'x':
            radix = 16
        elif nc == 'b':
            radix = 2
        else:
            number = number[1:]
            radix = 8
    try:
        return int(number, radix)
    except ValueError:
        return defaultNumber

def GetTimeMicroseconds():
    return int(time.time() * 1000000)

def MiniSleep():
    time.sleep(0.0005)

def HandleException(ir, code):
    if code == 3:
        pass
    return code

def HandleControlStore(addy, val):
    if addy == 0x10000000:
        print(chr(val), end='', flush=True)
    elif addy == 0x11004004:
        core.timermatchh = val
    elif addy == 0x11004000:
        core.timermatchl = val
    elif addy == 0x11100000:
        core.pc += 4
        return val
    return 0

def HandleControlLoad(addy):
    if addy == 0x10000005:
        return 0x60 | IsKBHit()
    elif addy == 0x10000000 and IsKBHit():
        return ReadKBByte()
    elif addy == 0x1100bffc:
        return core.timerh
    elif addy == 0x1100bff8:
        return core.timerl
    return 0

def HandleOtherCSRWrite(image, csrno, value):
    if csrno == 0x136:
        print(value, end='', flush=True)
    elif csrno == 0x137:
        print(f"{value:08x}", end='', flush=True)
    elif csrno == 0x138:
        ptrstart = value - MINIRV32_RAM_IMAGE_OFFSET
        ptrend = ptrstart
        if ptrstart >= MINI_RV32_RAM_SIZE:
            print(f"DEBUG PASSED INVALID PTR ({value:08x})")
        while ptrend < MINI_RV32_RAM_SIZE:
            if image[ptrend] == 0:
                break
            ptrend += 1
        if ptrend != ptrstart:
            sys.stdout.write(image[ptrstart:ptrend])
    elif csrno == 0x139:
        print(chr(value), end='', flush=True)

def HandleOtherCSRRead(image, csrno):
    if csrno == 0x140:
        if not IsKBHit():
            return -1
        return ReadKBByte()
    return 0

def DumpState(core, ram_image):
    pc = core.pc
    pc_offset = pc - MINIRV32_RAM_IMAGE_OFFSET
    ir = 0
    print(f"PC: {pc:08x} ", end='')
    if 0 <= pc_offset < MINI_RV32_RAM_SIZE - 3:
        ir = struct.unpack('<I', ram_image[pc_offset:pc_offset+4])[0]
        print(f"[{ir:08x}] ", end='')
    else:
        print("[xxxxxxxxxx] ", end='')
    regs = core.regs
    print(f"Z:{regs[0]:08x} ra:{regs[1]:08x} sp:{regs[2]:08x} gp:{regs[3]:08x} tp:{regs[4]:08x} t0:{regs[5]:08x} t1:{regs[6]:08x} t2:{regs[7]:08x} s0:{regs[8]:08x} s1:{regs[9]:08x} a0:{regs[10]:08x} a1:{regs[11]:08x} a2:{regs[12]:08x} a3:{regs[13]:08x} a4:{regs[14]:08x} a5:{regs[15]:08x} ", end='')
    print(f"a6:{regs[16]:08x} a7:{regs[17]:08x} s2:{regs[18]:08x} s3:{regs[19]:08x} s4:{regs[20]:08x} s5:{regs[21]:08x} s6:{regs[22]:08x} s7:{regs[23]:08x} s8:{regs[24]:08x} s9:{regs[25]:08x} s10:{regs[26]:08x} s11:{regs[27]:08x} t3:{regs[28]:08x} t4:{regs[29]:08x} t5:{regs[30]:08x} t6:{regs[31]:08x}\n")

SET_HANDLERS(MINIRV32_POSTEXEC, MINIRV32_HANDLE_MEM_STORE_CONTROL, MINIRV32_HANDLE_MEM_LOAD_CONTROL, MINIRV32_OTHERCSR_WRITE, MINIRV32_OTHERCSR_READ);

# Main function
def main(argv):
    global core
    global fail_on_all_faults
    ram_amt = MINI_RV32_RAM_SIZE
    instct = -1
    show_help = 0
    time_divisor = 1
    fixed_update = 0
    do_sleep = 1
    single_step = 0
    dtb_ptr = 0
    image_file_name = None
    dtb_file_name = None
    kernel_command_line = None

    image_file_name = "Image"

    i = 1
    while i < len(argv):
        param = argv[i]
        param_continue = 0
        while True:
            if param[0] == '-' or param_continue:
                if param[1] == 'm':
                    i += 1
                    ram_amt = SimpleReadNumberInt(argv[i], ram_amt)
                elif param[1] == 'c':
                    i += 1
                    instct = SimpleReadNumberInt(argv[i], -1)
                elif param[1] == 'k':
                    i += 1
                    kernel_command_line = argv[i]
                elif param[1] == 'f':
                    i += 1
                    image_file_name = argv[i]
                elif param[1] == 'b':
                    i += 1
                    dtb_file_name = argv[i]
                elif param[1] == 'l':
                    param_continue = 1
                    fixed_update = 1
                elif param[1] == 'p':
                    param_continue = 1
                    do_sleep = 0
                elif param[1] == 's':
                    param_continue = 1
                    single_step = 1
                elif param[1] == 'd':
                    param_continue = 1
                    fail_on_all_faults = 1
                elif param[1] == 't':
                    i += 1
                    time_divisor = SimpleReadNumberInt(argv[i], 1)
                else:
                    if param_continue:
                        param_continue = 0
                    else:
                        show_help = 1
            else:
                show_help = 1
                break
            param = param[1:]
            if not param_continue:
                break

        i += 1

    if show_help or image_file_name is None or time_divisor <= 0:
        print("./mini-rv32imaf [parameters]\n\t-m [ram amount]\n\t-f [running image]\n\t-k [kernel command line]\n\t-b [dtb file, or 'disable']\n\t-c instruction count\n\t-s single step with full processor state\n\t-t time divion base\n\t-l lock time base to instruction count\n\t-p disable sleep when wfi\n\t-d fail out immediately on all faults\n")
        return 1

    ram_image = bytearray(ram_amt)
    if not ram_image:
        print("Error: could not allocate system image.")
        return -4

    while True:
        try:
            with open(image_file_name, "rb") as f:
                f.seek(0, os.SEEK_END)
                flen = f.tell()
                f.seek(0, os.SEEK_SET)
                if flen > ram_amt:
                    print(f"Error: Could not fit RAM image ({flen} bytes) into {ram_amt}")
                    return -6

                ram_image = bytearray(ram_amt)
                if f.readinto(ram_image) != flen:
                    print("Error: Could not load image.")
                    return -7

                if dtb_file_name:
                    if dtb_file_name == "disable":
                        pass
                    else:
                        with open(dtb_file_name, "rb") as f:
                            f.seek(0, os.SEEK_END)
                            dtblen = f.tell()
                            f.seek(0, os.SEEK_SET)
                            dtb_ptr = ram_amt - dtblen - sys.getsizeof(MiniRV32IMAState)
                            if f.readinto(ram_image[dtb_ptr:]) != dtblen:
                                print(f"Error: Could not open dtb \"{dtb_file_name}\"")
                                return -9
                else:
                    #sys.getsizeof(MiniRV32IMAState)
                    state_size = 192
                    mbdtb_size = len(default64mbdtb)
                    dtb_ptr = ram_amt - mbdtb_size - state_size
                    ram_image[dtb_ptr:dtb_ptr+mbdtb_size] = default64mbdtb
                    if kernel_command_line:
                        ram_image[dtb_ptr+0xc0:dtb_ptr+0xc0+len(kernel_command_line)] = kernel_command_line.encode()

                break
        except FileNotFoundError:
            print(f"Error: \"{image_file_name}\" not found")
            return -5

    CaptureKeyboardInput()

    core = MiniRV32IMAState()
    core.pc = MINIRV32_RAM_IMAGE_OFFSET
    core.regs[10] = 0x00
    core.regs[11] = (dtb_ptr+MINIRV32_RAM_IMAGE_OFFSET) if dtb_ptr else 0
    core.extraflags |= 3

    if dtb_file_name is None:
        ptr = dtb_ptr + 0x13c
        dtb = struct.unpack('<I', ram_image[ptr:ptr+4])[0]
        if dtb == 0x00c0ff03:
            validram = dtb_ptr
            ram_image[ptr] =     validram >> 24 & 0xFF
            ram_image[ptr + 1] = validram >> 16 & 0xFF
            ram_image[ptr + 2] = validram >> 8  & 0xFF
            ram_image[ptr + 3] = validram       & 0xFF

    rt = 0
    lastTime = 0 if fixed_update else GetTimeMicroseconds() // time_divisor
    instrs_per_flip = 1 if single_step else 1024
    while rt < instct + 1 or instct < 0:
        this_ccount = core.cyclel
        elapsedUs = 0
        if fixed_update:
            elapsedUs = this_ccount // time_divisor - lastTime
        else:
            elapsedUs = GetTimeMicroseconds() // time_divisor - lastTime
        lastTime += elapsedUs

        if single_step:
            DumpState(core, ram_image)

        ret = MiniRV32IMAStep(core, ram_image, 0, elapsedUs, instrs_per_flip)
        if ret == 0:
            pass
        elif ret == 1:
            if do_sleep:
                MiniSleep()
            this_ccount += instrs_per_flip
        elif ret == 3:
            instct = 0
        elif ret == 0x7777:
            continue
        elif ret == 0x5555:
            print(f"POWEROFF@0x{core.cycleh:08x}{core.cyclel:08x}")
            return 0
        else:
            print("Unknown failure")

        rt += instrs_per_flip

    DumpState(core, ram_image)

if __name__ == "__main__":
    main(sys.argv)