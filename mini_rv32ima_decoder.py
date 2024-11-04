import ctypes
import struct

# Constants
MINI_RV32_RAM_SIZE = 0x80000000
MINIRV32_RAM_IMAGE_OFFSET = 0x80000000

INT32_MIN=0x80000000

MINIRV32_POSTEXEC = None
MINIRV32_HANDLE_MEM_STORE_CONTROL = None
MINIRV32_HANDLE_MEM_LOAD_CONTROL  = None
MINIRV32_OTHERCSR_WRITE = None
MINIRV32_OTHERCSR_READ = None

def SET_RAM_SIZE(size):
    global MINI_RV32_RAM_SIZE;
    MINI_RV32_RAM_SIZE = size

def SET_HANDLERS(MINIRV32_POSTEXEC_, MINIRV32_HANDLE_MEM_STORE_CONTROL_, MINIRV32_HANDLE_MEM_LOAD_CONTROL_, MINIRV32_OTHERCSR_WRITE_, MINIRV32_OTHERCSR_READ_):
    global MINIRV32_POSTEXEC, MINIRV32_HANDLE_MEM_STORE_CONTROL, MINIRV32_HANDLE_MEM_LOAD_CONTROL, MINIRV32_OTHERCSR_WRITE, MINIRV32_OTHERCSR_READ
    MINIRV32_POSTEXEC, MINIRV32_HANDLE_MEM_STORE_CONTROL, MINIRV32_HANDLE_MEM_LOAD_CONTROL, MINIRV32_OTHERCSR_WRITE, MINIRV32_OTHERCSR_READ = MINIRV32_POSTEXEC_, MINIRV32_HANDLE_MEM_STORE_CONTROL_, MINIRV32_HANDLE_MEM_LOAD_CONTROL_, MINIRV32_OTHERCSR_WRITE_, MINIRV32_OTHERCSR_READ_

if 0:
    def LOG(x): print(x)
else:
    def LOG(x): pass

def MINIRV32_MMIO_RANGE(n):
    return 0x10000000 <= n < 0x12000000

def MINIRV32_STORE4(image, ofs, val):
    image[ofs:ofs + 4] = val.to_bytes(4, byteorder='little')

def MINIRV32_STORE2(image, ofs, val):
    image[ofs:ofs + 2] = (val & 0xFFFF).to_bytes(2, byteorder='little')

def MINIRV32_STORE1(image, ofs, val):
    image[ofs] = val & 0xFF

def MINIRV32_LOAD4(image, ofs):
    r =  struct.unpack('<I', image[ofs:ofs+4])[0]
    return r

def MINIRV32_LOAD2(image, ofs):
    return struct.unpack('<H', image[ofs:ofs+2])[0]

def MINIRV32_LOAD1(image, ofs):
    return struct.unpack('<B', image[ofs:ofs+1])[0]

def MINIRV32_LOAD2_SIGNED(image, ofs):
    return struct.unpack('<h', image[ofs:ofs+2])[0]

def MINIRV32_LOAD1_SIGNED(image, ofs):
    return struct.unpack('<b', image[ofs:ofs+1])[0]

# Struct
class MiniRV32IMAState():
    regs = [i for i in range(32)]
    pc = 0
    mstatus = 0
    cyclel = 0
    cycleh = 0
    timerl = 0
    timerh = 0
    timermatchl = 0
    timermatchh = 0
    mscratch = 0
    mtvec = 0
    mie = 0
    mip = 0
    mepc = 0
    mtval = 0
    mcause = 0
    extraflags = 0
    
# Function
def MiniRV32IMAStep(state, image, vProcAddress, elapsedUs, count):
    new_timer = state.timerl + elapsedUs
    if new_timer < state.timerl:
        state.timerh += 1
    state.timerl = new_timer

    if (state.timerh > state.timermatchh or (state.timerh == state.timermatchh and state.timerl > state.timermatchl)) and (state.timermatchh or state.timermatchl):
        state.extraflags &= ~4  # Clear WFI
        state.mip |= 1 << 7  # MTIP of MIP
    else:
        state.mip &= ~(1 << 7)

    if state.extraflags & 4:
        return 1

    trap = 0
    rval = 0
    pc = state.pc
    cycle = state.cyclel

    if (state.mip & (1 << 7)) and (state.mie & (1 << 7)) and (state.mstatus & 0x8):
        trap = 0x80000007
        pc -= 4
    else:
        for icount in range(count):
            ir = 0
            rval = 0
            cycle += 1
            ofs_pc = pc - MINIRV32_RAM_IMAGE_OFFSET

            if ofs_pc >= MINI_RV32_RAM_SIZE:
                trap = 1 + 1
                break
            elif ofs_pc & 3:
                trap = 1 + 0
                break
            else:
                ir = MINIRV32_LOAD4(image, ofs_pc)
                rdid = (ir >> 7) & 0x1f

                cmd = ir & 0x7f
                if cmd == 0x37:  # LUI (0b0110111)
                    LOG("LUI")
                    rval = (ir & 0xfffff000)
                elif cmd == 0x17:  # AUIPC (0b0010111)
                    LOG("AUIPC")
                    rval = pc + (ir & 0xfffff000)
                elif cmd == 0x6F:  # JAL (0b1101111)
                    LOG("JAL")
                    reladdy = ((ir & 0x80000000) >> 11) | ((ir & 0x7fe00000) >> 20) | ((ir & 0x00100000) >> 9) | ((ir & 0x000ff000))
                    if reladdy & 0x00100000:
                        reladdy |= 0xffe00000  # Sign extension.
                    rval = pc + 4
                    pc = (pc + reladdy - 4) & 0xFFFFFFFF
                elif cmd == 0x67:  # JALR (0b1100111)
                    LOG("JALR")
                    imm = ir >> 20
                    
                    imm_se = imm | (0xfffff000 if (imm & 0x800) else 0)
                    rval = pc + 4
                    rs1 = state.regs[(ir >> 15) & 0x1f]
                    pc = (((rs1 + imm_se) & ~1) - 4) & 0xFFFFFFFF
                elif cmd == 0x63:  # Branch (0b1100011)
                    LOG("Branch")
                    immm4 = ((ir & 0xf00) >> 7) | ((ir & 0x7e000000) >> 20) | ((ir & 0x80) << 4) | ((ir >> 31) << 12)
                    if immm4 & 0x1000:
                        immm4 |= 0xffffe000
                    rs1 = ctypes.c_int32( state.regs[(ir >> 15) & 0x1f]).value
                    rs2 = ctypes.c_int32(state.regs[(ir >> 20) & 0x1f]).value
                    immm4 = (pc + immm4 - 4) & 0xFFFFFFFF
                    rdid = 0
                    #BEQ, BNE, BLT, BGE, BLTU, BGEU
                    irs12 = (ir >> 12) & 0x7
                    if irs12 == 0:
                        if rs1 == rs2:
                            pc = immm4
                    elif irs12 == 1:
                        if rs1 != rs2:
                            pc = immm4
                    elif irs12== 4:
                        if rs1 < rs2:
                            pc = immm4
                    elif irs12 == 5:
                        if rs1 >= rs2:
                            pc = immm4
                    elif irs12 == 6:
                        if (ctypes.c_uint32(rs1).value < ctypes.c_uint32(rs2).value):
                            pc = immm4
                    elif irs12 == 7:
                        if (ctypes.c_uint32(rs1).value >= ctypes.c_uint32(rs2).value):
                            pc = immm4
                    else:
                        trap = (2 + 1)
                elif cmd == 0x03:  # Load (0b0000011)
                    LOG("Load")
                    rs1 = state.regs[(ir >> 15) & 0x1f]
                    imm = ir >> 20
                    imm_se = imm | (0xfffff000 if (imm & 0x800) else 0)
                    rsval = (rs1 + imm_se) & 0xFFFFFFFF

                    rsval -= MINIRV32_RAM_IMAGE_OFFSET
                    rsval &= 0xFFFFFFFF
                    if rsval >= MINI_RV32_RAM_SIZE - 3:
                        rsval += MINIRV32_RAM_IMAGE_OFFSET
                        rsval &= 0xFFFFFFFF
                        if MINIRV32_MMIO_RANGE(rsval):
                            rval = MINIRV32_HANDLE_MEM_LOAD_CONTROL(rsval)
                        else:
                            trap = (5 + 1)
                            rval = rsval
                    else:
                        #LB, LH, LW, LBU, LHU
                        irs12 = (ir >> 12) & 0x7
                        if irs12 == 0:
                            rval = MINIRV32_LOAD1_SIGNED(image, rsval)
                        elif irs12 == 1:
                            rval = MINIRV32_LOAD2_SIGNED(image, rsval)
                        elif irs12 == 2:
                            rval = MINIRV32_LOAD4(image, rsval)
                        elif irs12 == 4:
                            rval = MINIRV32_LOAD1(image, rsval)
                        elif irs12 == 5:
                            rval = MINIRV32_LOAD2(image, rsval)
                        else:
                            trap = (2 + 1)
                elif cmd == 0x23:  # Store 0b0100011
                    LOG("Store")
                    rs1 = state.regs[(ir >> 15) & 0x1f]
                    rs2 = state.regs[(ir >> 20) & 0x1f]
                    addy = ((ir >> 7) & 0x1f) | ((ir & 0xfe000000) >> 20)
                    if addy & 0x800:
                        addy |= 0xfffff000
                    addy += rs1 - MINIRV32_RAM_IMAGE_OFFSET
                    addy &= 0xFFFFFFFF
                    rdid = 0

                    if addy >= MINI_RV32_RAM_SIZE - 3:
                        addy += MINIRV32_RAM_IMAGE_OFFSET
                        addy &= 0xFFFFFFFF
                        if MINIRV32_MMIO_RANGE(addy):
                            MINIRV32_HANDLE_MEM_STORE_CONTROL(addy, rs2)
                        else:
                            trap = (7 + 1)
                            rval = addy
                    else:
                        irs12 = (ir >> 12) & 0x7
                        if irs12 == 0:
                            MINIRV32_STORE1(image, addy, rs2)
                        elif irs12 == 1:
                            MINIRV32_STORE2(image, addy, rs2)
                        elif irs12 == 2:
                            MINIRV32_STORE4(image, addy, rs2)
                        else:
                            trap = (2 + 1)
                elif cmd == 0x13 or cmd == 0x33:  # Op-immediate 0b0010011 or Op 0b0110011
                    LOG("Op-immediate")
                    imm = ir >> 20
                    imm = imm | (0xfffff000 if (imm & 0x800) else 0)
                    reg = (ir >> 15) & 0x1f
                    rs1 = state.regs[reg]
                    is_reg = (ir & 0x20) #check !!
                    rs2 = state.regs[imm & 0x1f] if is_reg else imm

                    cmd_ = (ir >> 12) & 7
                    if is_reg and (ir & 0x02000000):
                        #0x02000000 = RV32M
                        if cmd_ == 0:
                            #MUL
                            rval = rs1 * rs2
                        elif cmd_ == 1:
                            #MULH
                            rval = ((ctypes.c_int64(rs1).value * ctypes.c_int64(rs2).value) >> 32)
                        elif cmd_ == 2:
                            #MULHSU
                            rval = ((ctypes.c_int64(rs1).value * ctypes.c_uint64(rs2).value) >> 32)
                        elif cmd_ == 3:
                            #MULHU
                            rval = ((ctypes.c_uint64(rs1).value * ctypes.c_uint64(rs2).value) >> 32) 
                        elif cmd_ == 4:
                            #DIV
                            if rs2 == 0:
                                rval = 0xFFFFFFFF #-1
                            else:
                                if (rs1 == INT32_MIN and ctypes.c_int32(rs2).value == -1): 
                                    rval = rs1
                                else:
                                    rval = (ctypes.c_int32(rs1).value // ctypes.c_int32(rs2).value)
                        elif cmd_ == 5:
                            #DIVU
                            if rs2 == 0:
                                rval = 0xffffffff
                            else:
                                rval = rs1 // rs2
                        elif cmd_ == 6:
                            #REM
                            if rs2 == 0:
                                rval = rs1
                            else:
                                if (rs1 == INT32_MIN and ctypes.c_int32(rs2).value == INT32_MIN):
                                    rval = 0 
                                else:
                                    rval = (ctypes.c_uint32(rs1).value % ctypes.c_uint32(rs2).value)
                        elif cmd_ == 7:
                            #REMU
                            if rs2 == 0:
                                rval = rs1
                            else:
                                rval = rs1 % rs2
                    else:
                        #// These could be either op-immediate or op commands.  Be careful
                        if cmd_ == 0:
                            rval = (rs1 - rs2) if is_reg and (ir & 0x40000000) else (rs1 + rs2)
                        elif cmd_ == 1:
                            rval = rs1 << (rs2 & 0x1F)
                        elif cmd_ == 2:
                            rval = (ctypes.c_int32(rs1).value < ctypes.c_int32(rs2).value)
                        elif cmd_ == 3:
                            rval = rs1 < rs2
                        elif cmd_ == 4:
                            rval = rs1 ^ rs2
                        elif cmd_ == 5:
                            shift_len = rs2 & 0x1F
                            rval = ((ctypes.c_int32(rs1).value >> (shift_len)) if (ir & 0x40000000) else (rs1 >> (shift_len)))
                        elif cmd_ == 6:
                            rval = rs1 | rs2
                        elif cmd_ == 7:
                            rval = rs1 & rs2
                elif cmd == 0x0f:  # 0b0001111
                    LOG("0b0001111")
                    #fencetype = (ir >> 12) & 0b111; We ignore fences in this impl
                    rdid = 0
                elif cmd == 0x73:  # Zifencei+Zicsr  (0b1110011)
                    LOG("Zifencei+Zicsr")
                    csrno = ir >> 20
                    microop = (ir >> 12) & 0x7
                    if (microop & 3):
                        rs1imm = (ir >> 15) & 0x1f
                        rs1 = state.regs[rs1imm]
                        writeval = rs1

                        if csrno == 0x340:
                            rval = state.mscratch
                        elif csrno == 0x305:
                            rval = state.mtvec
                        elif csrno == 0x304:
                            rval = state.mie
                        elif csrno == 0xC00:
                            rval = cycle
                        elif csrno == 0x344:
                            rval = state.mip
                        elif csrno == 0x341:
                            rval = state.mepc
                        elif csrno == 0x300:
                            rval = state.mstatus
                        elif csrno == 0x342:
                            rval = state.mcause
                        elif csrno == 0x343:
                            rval = state.mtval
                        elif csrno == 0xf11:
                            rval = 0xff0ff0ff
                        elif csrno == 0x301:
                            rval = 0x40401101
                        else:
                            rval = MINIRV32_OTHERCSR_READ(image, csrno)

                        if microop == 1:
                            writeval = rs1
                        elif microop == 2:
                            writeval = rval | rs1
                        elif microop == 3:
                            writeval = rval & ~rs1
                        elif microop == 5:
                            writeval = rs1imm
                        elif microop == 6:
                            writeval = rval | rs1imm
                        elif microop == 7:
                            writeval = rval & ~rs1imm

                        if csrno == 0x340:
                            state.mscratch = writeval
                        elif csrno == 0x305:
                            state.mtvec = writeval
                        elif csrno == 0x304:
                            state.mie = writeval
                        elif csrno == 0x344:
                            state.mip = writeval
                        elif csrno == 0x341:
                            state.mepc = writeval
                        elif csrno == 0x300:
                            state.mstatus = writeval
                        elif csrno == 0x342:
                            state.mcause = writeval
                        elif csrno == 0x343:
                            state.mtval = writeval
                        else:
                            MINIRV32_OTHERCSR_WRITE(image, csrno, writeval)
                    elif microop == 0x0:
                        rdid = 0
                        if csrno == 0x105:
                            state.mstatus |= 8
                            state.extraflags |= 4
                            state.pc = pc + 4
                            return 1
                        elif (csrno & 0xff) == 0x02:
                            startmstatus = state.mstatus
                            startextraflags = state.extraflags
                            state.mstatus = ((startmstatus & 0x80) >> 4) | ((startextraflags & 3) << 11) | 0x80
                            state.extraflags = (startextraflags & ~3) | ((startmstatus >> 11) & 3)
                            pc = state.mepc - 4
                        else:
                            if csrno == 0:
                                trap = (11 + 1) if (state.extraflags & 3) else (8 + 1)
                            elif csrno == 1:
                                trap = (3 + 1)
                            else:
                                trap = (2 + 1)
                    else:
                        trap = (2 + 1)
                elif cmd == 0x2f:  # RV32A (0b00101111)
                    LOG("RV32A")
                    rs1 = state.regs[(ir >> 15) & 0x1f]
                    rs2 = state.regs[(ir >> 20) & 0x1f]
                    irmid = (ir >> 27) & 0x1f

                    rs1 -= MINIRV32_RAM_IMAGE_OFFSET

                    if rs1 >= MINI_RV32_RAM_SIZE - 3:
                        trap = (7 + 1)
                        rval = rs1 + MINIRV32_RAM_IMAGE_OFFSET
                    else:
                        rval = MINIRV32_LOAD4(image, rs1)

                        dowrite = 1
                        if irmid == 2:
                            dowrite = 0
                            state.extraflags = (state.extraflags & 0x07) | (rs1 << 3)
                        elif irmid == 3:
                            rval = (state.extraflags >> 3 != (rs1 & 0x1fffffff))
                            dowrite = not rval
                        elif irmid == 1:
                            pass
                        elif irmid == 0:
                            rs2 += rval
                            rs2 &= 0xFFFFFFFF
                        elif irmid == 4:
                            rs2 ^= rval
                        elif irmid == 12:
                            rs2 &= rval
                        elif irmid == 8:
                            rs2 |= rval
                        elif irmid == 16:
                            rs2 = (rs2 if (ctypes.c_int32(rs2).value < ctypes.c_int32(rval).value) else rval)
                        elif irmid == 20:
                            rs2 = (rs2 if (ctypes.c_int32(rs2).value > ctypes.c_int32(rval).value) else rval)
                        elif irmid == 24:
                            rs2 = rs2 if (rs2 < rval) else rval
                        elif irmid == 28:
                            rs2 = rs2 if (rs2 > rval) else rval
                        else:
                            trap = (2 + 1)
                            dowrite = 0
                        if dowrite:
                            MINIRV32_STORE4(image, rs1, rs2)
                else:
                    trap = (2 + 1)

                if trap:
                    break

                if rdid:
                    state.regs[rdid] = rval & 0xFFFFFFFF


            MINIRV32_POSTEXEC(pc, ir, trap)

            pc += 4

    if trap:
        if trap & 0x80000000:
            state.mcause = trap
            state.mtval = 0
            pc += 4
        else:
            state.mcause = trap - 1
            state.mtval = rval if (trap > 5 and trap <= 8) else pc
        state.mepc = pc
        state.mstatus = ((state.mstatus & 0x08) << 4) | ((state.extraflags & 3) << 11)
        pc = (state.mtvec - 4)

        state.extraflags |= 3

        trap = 0
        pc += 4

    if state.cyclel > cycle:
        state.cycleh += 1
    state.cyclel = cycle
    state.pc = pc
    return 0