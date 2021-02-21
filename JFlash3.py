# WARNING! This file is auto-translated from Python 2.7 by https://pythonconverter.com/

r"""
JFlash.py -- GDB script for Milandr MCU 1986x flashing with J-Link
http://github.com/in4lio/mdr1986x-JFlash/

Usage: gdb-py --batch -x JFlash.py -ex "py program_from_shell(<bin_file>)"

Copyright (c) 2016,2017 Vitaly Kravtsov (in4lio@gmail.com)
See the LICENSE file.

Modified by Vladislav Kochetkov (2021)
"""

APP               = 'JFlash3'
VERSION           = '0.7.5'

#  Write CRC-32 of binary file right after the image in EEPROM
CRC32_WRITING     = True

#  J-Link GDB Server
HOST              = 'localhost'
PORT              = 2331

LOADER_F9Qx       = 'LOADER/LOADER_F9Qx.bin'
LOADER_F1         = 'LOADER/LOADER_F1.bin'
OBJCOPY           = 'arm-none-eabi-objcopy'

#  LOADER layout (according to MAP file)
#  NOTE: Use 'mapper.py' if you need to update the following definitions.
LD_COMPILER_F9Qx  = 1
LD_START_F9Qx     = 0x0000000020000bc4
LD_STACK_F9Qx     = 0x0000000020008000
LD_WRITE_F9Qx     = 0x0000000020002464
LD_WRITE_SZ_F9Qx  = 0x4008
LD_STATE_F9Qx     = 0x000000002000245c
LD_ERROR_F9Qx     = 0x0000000020002460
LD_RTT_F9Qx       = 0x0000000020002004

LD_COMPILER_F1    = 1
LD_START_F1       = 0x201000c0
LD_STACK_F1       = 0x20008000
LD_WRITE_F1       = 0x20000008
LD_WRITE_SZ_F1    = 0x4008
LD_STATE_F1       = 0x20100620
LD_ERROR_F1       = 0x20000004
LD_RTT_F1         = 0

LD_ADDR_SZ        = 4
LD_LEN_SZ         = 4

#  LOADER running command or state
START             = 0
ERASE             = 1
WRITE_BLOCK       = 2
IDLE              = 0xFFFFFFFF

#  LOADER error
ERR_NONE          = 0
ERR_ADDR          = 1
ERR_ADDR_ALIGN    = 2
ERR_ADDR_END      = 3

#  MCU memory layout
RAM_START_F9Qx    = 0x20000000
EEPROM_START_F9Qx = 0x08000000

RAM_START_F1      = 0x20100000
EEPROM_START_F1   = 0x00000000

CPUID             = 0xE000ED00
CPUID_CM1         = 0x411CC210
CPUID_CM3         = 0x412FC230

RE_RTT_ADDR       = r'\s+(0x[0-9a-fA-F]+)\s+_SEGGER_RTT\s*'

import gdb
import sys
import os
import logging
from time import sleep
import filecmp
import re
import binascii
import tempfile

#  Logging
LOG               = APP + '.log'
LOG_LEVEL         = logging.DEBUG
LOG_FORMAT        = '%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s'
LOG_TIME          = '%H:%M:%S'

log = logging.getLogger( 'log' )
log.setLevel( LOG_LEVEL )

#  MCU registers
#  R0 .. R15
for x in range( 0, 16 ):
    #  I know, it's a really bad idea, but...
    globals()[ 'R%d' % x ] = 'r%d' % x

PC  = 'pc'
LR  = 'lr'
MSP = 'MSP'
PSP = 'PSP'

#  Execute GDB command
def execute( st ):
    return gdb.execute( st, to_string=True )

#  Execute GDB 'monitor' command
def monitor( st ):
    return execute( 'monitor ' + st )

#  Read DWORD (32 bit) for memory
def mem32( addr ):
    ret = execute( 'x ' + str( addr ))
    try:
        return int( ret.splitlines()[ 0 ].split( ':' )[ -1 ].strip(), 16 )

    except ValueError:
        log.error( 'Fail to read DWORD at %#x (%s).', addr, ret )
        return -1

#  Write DWORD (32 bit) to memory
def set_mem32( addr, val ):
    return execute( 'set {int}%d = %d' % ( addr, val ))

#  Read register
def reg( r ):
    ret = gdb.parse_and_eval( '$' + r )
    try:
        return int( ret )

    except ValueError:
        log.error( 'Fail to get %s (%s).', r, ret )
        return -1

#  Write register
def set_reg( r, val ):
    #  BUG!? With JLink V6.10g, command `set $MSP = val` doesn't work properly for CM1.
    return monitor( 'reg %s = %d' % ( r, val ))

#  Upload binary data form file to memory
#  This command does not allow to quote the filename with "",
#  so you can NOT use space characters in the filename.
def load_binary( fn, offset, start=None, end=None ):
    st = 'restore %s binary %d' % ( fn, offset )
    if start is not None:
        st += ' %d' % start
        if end is not None:
            st += ' %d' % end
    return execute( st )

#  Save data form memory to dump file
#  This command does not allow to quote the filename with "",
#  so you can NOT use space characters in the filename.
def dump_binary( fn, offset, l ):
    return execute( 'dump binary memory %s %d %d' % ( fn, offset, offset + l ))

#  Set taken from MAP file address of SEGGER_RTT structure
def set_RTT( fn ):
    fn_map = os.path.splitext( fn )[ 0 ] + '.map'
    if os.path.exists( fn_map ):
        regex = re.compile( RE_RTT_ADDR )
        for ln in open( fn_map ).readlines():
            m = regex.match( ln )
            if m:
                RTT = m.group( 1 )
                log.info( 'RTT structure at %s', RTT )
                monitor( 'exec SetRTTAddr ' + RTT )
                return True
    return False

#  Calculate CRC-32 of file
def calc_crc32( fn ):
    with open( fn, 'rb' ) as f:
        return ( binascii.crc32( f.read()) & 0xFFFFFFFF )

#  Align a number
def aligned( val, align ):
    return (( val + align - 1 ) // align * align )

#  Directory of the script
SCRIPT_DIR = os.path.dirname( os.path.realpath( __file__ ))

#  Verify EEPROM
def verify( offset, binary, binary_sz ):
    dump = tempfile.mktemp()
    dump_binary( dump, offset, binary_sz )
    cmp_res = filecmp.cmp( binary, dump )
    os.remove( dump )
    return cmp_res

# # # # # # # #  MAIN SCRIPT  # # # # # # # #

def program( binary ):
    log.info( '%s %s', APP, VERSION )

    p, e = os.path.splitext( binary )
    if e == '.elf':
        log.info( 'ELF to binary converting...' )
        elf = binary
        binary = p + '.bin'
        os.system( '%s -O binary %s %s' % ( OBJCOPY, elf, binary ))

    if not os.path.exists( binary ):
        log.error( 'Binary file not found (%s).', binary )
        return False

    binary_sz = os.path.getsize( binary )
    crc32 = calc_crc32( binary )

    log.info( 'Binary file: %s', binary )
    log.info( 'Size: %d', binary_sz )
    log.info( 'CRC-32: %#08x', crc32 )

    log.info( 'Hello!' )

    fb = monitor( 'reset 0' )
    log.debug( fb.strip())
    monitor( 'halt' )

    # # # #  IDENTIFY MCU  # # # #

    cpuid = mem32( CPUID )
    MCU_F9Qx = cpuid == CPUID_CM3
    if cpuid == CPUID_CM3:
        core = 'CM3'
    elif cpuid == CPUID_CM1:
        core = 'CM1'
    else:
        core = 'unknown'
    log.info( 'CPUID: %#x (%s)', cpuid, core )

    if MCU_F9Qx:
        LOADER        = LOADER_F9Qx
        LD_START      = LD_START_F9Qx
        LD_STACK      = LD_STACK_F9Qx
        LD_WRITE      = LD_WRITE_F9Qx
        LD_WRITE_SZ   = LD_WRITE_SZ_F9Qx
        LD_STATE      = LD_STATE_F9Qx
        LD_ERROR      = LD_ERROR_F9Qx
        LD_RTT        = LD_RTT_F9Qx
        RAM_START     = RAM_START_F9Qx
        EEPROM_START  = EEPROM_START_F9Qx
    else:
        LOADER        = LOADER_F1
        LD_START      = LD_START_F1
        LD_STACK      = LD_STACK_F1
        LD_WRITE      = LD_WRITE_F1
        LD_WRITE_SZ   = LD_WRITE_SZ_F1
        LD_STATE      = LD_STATE_F1
        LD_ERROR      = LD_ERROR_F1
        LD_RTT        = LD_RTT_F1
        RAM_START     = RAM_START_F1
        EEPROM_START  = EEPROM_START_F1

    LD_DATA           = LD_WRITE
    LD_DATA_SZ        = LD_WRITE_SZ - LD_ADDR_SZ - LD_LEN_SZ
    LD_ADDR           = LD_DATA + LD_DATA_SZ
    LD_LEN            = LD_ADDR + LD_ADDR_SZ

    log.info( 'MCU data buffer at %#x', LD_DATA )
    log.info( 'MCU state at %#x', LD_STATE )
    crc32_addr = EEPROM_START + aligned( binary_sz, 4 )

    # # # #  VERIFY EEPROM BEFORE PROGRAMMING  # # # #

    if verify( EEPROM_START, binary, binary_sz ):
        log.info( 'Binary file exactly matches with EEPROM content.' )

        set_RTT( binary )
        return True

    # # # #  START LOADER  # # # #

    log.info( 'LOADER uploading...' )
    fb = load_binary( os.path.join( SCRIPT_DIR, LOADER ), RAM_START )
    log.debug( fb.strip())
    set_reg( MSP, LD_STACK )
    set_reg( PC , LD_START & ~1 )
    if MCU_F9Qx:
        set_mem32( 0xE000E008, 0x20000000 )
    set_mem32( LD_STATE, START )
    if LD_RTT:
        monitor( 'exec SetRTTAddr ' + hex( LD_RTT ))
    monitor( 'go' )
    sleep( 0.1 )

    #  Check LOADER is started
    monitor( 'halt' )
    if mem32( LD_STATE ) != IDLE:
        log.error( 'LOADER is not running.' )
        return False

    # # # #  ERASE EEPROM  # # # #

    log.info( 'EEPROM erasing...' )
    set_mem32( LD_STATE, ERASE )
    monitor( 'go' )

    #  Wait for ending
    while mem32( LD_STATE ) == ERASE:
        log.info( 'TICK' )
        sleep( 0.2 )

    sleep( 0.2 )
    monitor( 'halt' )

    if not MCU_F9Qx:
        #  Workaround MDR32F1 BUG 0007, we need to renew EEPROM cache...
        mem32( EEPROM_START + 0x2000 )

    #  Check very first DWORD (32 bit)
    if mem32( EEPROM_START ) != 0xFFFFFFFF:
        log.error( 'EEPROM is not empty.' )
        return False

    # # # #  WRITING CYCLE  # # # #

    rest = binary_sz
    block = 0
    start = 0
    while ( rest ):
        if rest > LD_DATA_SZ:
            sz = LD_DATA_SZ
            rest -= LD_DATA_SZ
        else:
            sz = rest
            rest = 0

        block += 1
        log.info( 'BLOCK %d writing...', block )
        fb = load_binary( binary, LD_DATA - start, start, start + sz )
        log.debug( fb.strip())

        set_mem32( LD_ADDR, EEPROM_START + start )
        set_mem32( LD_LEN, aligned( sz, 4 ) // 4 )  # size in EEPROM_WORD (32 bit)
        set_mem32( LD_STATE, WRITE_BLOCK )

        monitor( 'go' )

        sleep( 0.1 )
        #  Wait for ending
        while mem32( LD_STATE ) == WRITE_BLOCK:
            sleep( 0.2 )

        monitor( 'halt' )

        #  Check error
        if mem32( LD_ERROR ) != ERR_NONE:
            log.error( 'Fail to write data (E%d).', mem32( LD_ERROR ))
            return False

        start += sz

    # # # #  VERIFY EEPROM AFTER PROGRAMMING  # # # #

    if not MCU_F9Qx:
        #  Workaround MDR32F1 BUG 0007, we need to renew EEPROM cache...
        mem32( EEPROM_START + 0x2000 )

    if not verify( EEPROM_START, binary, binary_sz ):
        log.error( 'Binary file does NOT match with EEPROM content.' )
        return False

    # # # #  WRITE CRC-32  # # # #

    if CRC32_WRITING:
        log.info( 'CRC-32 writing...' )

        set_mem32( LD_DATA, crc32 )
        set_mem32( LD_ADDR, crc32_addr )
        set_mem32( LD_LEN, 1 )  # size in EEPROM_WORD (32 bit)
        set_mem32( LD_STATE, WRITE_BLOCK )

        monitor( 'go' )

        sleep( 0.1 )
        #  Wait for ending
        while mem32( LD_STATE ) == WRITE_BLOCK:
            sleep( 0.2 )

        monitor( 'halt' )

        #  Check error
        if mem32( LD_ERROR ) != ERR_NONE:
            log.error( 'Fail to write CRC-32 (E%d).', mem32( LD_ERROR ))
            return False

    # # # #  RESET MCU  # # # #

    set_RTT( binary )
    fb = monitor( 'reset 0' )
    log.info( fb.strip())
    monitor( 'halt' )

    if CRC32_WRITING:
        #  BUG!? There is a strong probability that we will get 0xFFFFFFFF
        #  if we read the same word we just wrote to EEPROM.
        #  So, we will check written CRC-32 after MCU reset...
        if mem32( crc32_addr ) != crc32:
            log.error( 'CRC-32 does NOT match with written value.' )
            return False

    log.info( '**** SUCCESS! ****' )

    return True

# # # # # # # #  WRAPPERS  # # # # # # # #

#  Wrapper for program EEPROM from GNU ARM Eclipse
def program_from_eclipse( binary ):
    #  Output log to file
    h = logging.FileHandler( LOG, mode = 'w' )
    h.setFormatter( logging.Formatter( LOG_FORMAT, LOG_TIME ))
    log.addHandler( h )
    try:
        result = program( binary )

    except Exception as e:
        log.exception( str( e ))
        result = False

    log.removeHandler( h )
    return result

#  Wrapper for program EEPROM from CLI
def program_from_shell( binary ):
    #  Output log to stdout
    h = logging.StreamHandler( sys.stdout )
    h.setFormatter( logging.Formatter( LOG_FORMAT, LOG_TIME ))
    log.addHandler( h )

    execute( 'set pagination off' )
    log.info( 'J-Link GDB Server connecting...' )
    try:
        execute( 'target remote %s:%d' % ( HOST, PORT ))

    except Exception as e:
        log.error( 'Fail to connect.' )
        log.info( e.message )
        log.info( 'Please start J-Link GDB Server first.' )
        log.removeHandler( h )
        return False

    result = program( binary )
    if result:
        monitor( 'go' )

    log.removeHandler( h )
    return result

#  GDB "load" command
class LoadCommand( gdb.Command ):
    def __init__( self ):
        #  Redefine "load" command
        super( type( self ), self ).__init__( 'load', gdb.COMMAND_FILES )

    def invoke( self, arg, from_tty ):
        if not program_from_eclipse( arg ):
            #  Cancel debugging
            execute( 'quit' )

LoadCommand()
