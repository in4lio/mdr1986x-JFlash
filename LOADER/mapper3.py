# WARNING! Tested only on xPack GNU Arm Embedded GCC v9.3.1-1.4 and xPack versions above

r"""
mapper.py -- Configure JFlash according to LOADER layout
"""

import sys, os
import fileinput
import re
from shutil import copyfile

DIR_SCRIPT  = '../'
FILE_MAP    = 'LOADER.map'
FILE_BINARY = 'LOADER.bin'
FILE_SCRIPT = 'JFlash3.py'

MCU_DICT = { 'F1': 'MDR32F1, 1986BE1', 'F3': 'MDR32F3, 1986BE3', 'F9': 'MDR32F9Qx, 1986BE9x' }

if ( len( sys.argv ) < 2 ) or ( sys.argv[ 1 ].upper() not in MCU_DICT ):
    sys.exit( '''
Usage: {0} ({1}|{2}|{3})
{1} - %({1})s
{2} - %({2})s
{3} - %({3})s'''.format( os.path.basename(__file__), *list(MCU_DICT.keys())) % MCU_DICT )

MCU = sys.argv[ 1 ].upper()
MCU_F9Qx = MCU == 'F9'

if MCU_F9Qx:
    DIR_ARMCC  = './ARMCC-MDR32F9Qx/'
    DIR_GCC    = './GCC-MDR32F9Qx/'
    FILE_BIN_R = 'LOADER_F9Qx.bin'

    VARIABLES  = (
        'LD_COMPILER_F9Qx',
        'LD_START_F9Qx',
        'LD_STACK_F9Qx',
        'LD_WRITE_F9Qx',
        'LD_WRITE_SZ_F9Qx',
        'LD_STATE_F9Qx',
        'LD_ERROR_F9Qx',
        'LD_RTT_F9Qx'
    )
else:
    DIR_ARMCC  = './ARMCC-MDR32F1/'
    DIR_GCC    = './GCC-MDR32F1/'
    FILE_BIN_R = 'LOADER_F1.bin'

    VARIABLES  = (
        'LD_COMPILER_F1',
        'LD_START_F1',
        'LD_STACK_F1',
        'LD_WRITE_F1',
        'LD_WRITE_SZ_F1',
        'LD_STATE_F1',
        'LD_ERROR_F1',
        'LD_RTT_F1'
    )

CC_LIST = ( 'ARMCC', 'GCC' )

# -- no compiler choice since 0.7, gcc only
#   if ( len( sys.argv ) < 2 ) or ( sys.argv[ 1 ].upper() not in CC_LIST ):
#       sys.exit( 'Usage: %s (%s|%s)' % ( os.path.basename(__file__), CC_LIST[ 0 ], CC_LIST[ 1 ]))
#   CC = CC_LIST.index( sys.argv[ 1 ].upper())
CC = 1

if CC == 0:
    DIR_BINARY = DIR_ARMCC
    RE_ADDR    = r'\s+%s\s+(0x[0-9a-fA-F]+)'
    RE_SIZE    = r'\s+%s\s+0x[0-9a-fA-F]+\s+Data\s+([0-9]+)'
else:
    DIR_BINARY = DIR_GCC
    RE_ADDR    = r'\s+(0x[0-9a-fA-F]+)\s+%s\s*'
    # RE_SIZE    = r'\s*+%s\s+(0x[0-9a-fA-F]+) + (0x[0-9a-fA-F]+)'  # DEPRECATED!!!
    RE_SIZE    = r'\s+%s\s+0x[0-9a-fA-F]+\s+(0x[0-9a-fA-F]+)'

RE_LIST = (
    '',
    RE_ADDR % ( 'Reset_Handler' ),
    RE_ADDR % ( '__initial_sp' if CC == 0 else '__StackTop' ),
    RE_ADDR % ( 'ld_write' ),
    #RE_SIZE % ( 'ld_write' ),  # DEPRECATED!!!
    RE_SIZE % ( '.bss.ld_write' ),
    RE_ADDR % ( 'ld_state' ),
    RE_ADDR % ( 'ld_error' ),
    RE_ADDR % ( '_SEGGER_RTT' )
)

RE_VAR = r'^(%s\s*=\s*)(0x[0-9a-fA-F]+|[0-9]+)(.*)'

DEFAULTS = (
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    '0'
)

os.chdir( os.path.dirname( os.path.realpath( __file__ )))
fn_binary = DIR_BINARY + FILE_BINARY
fn_map = DIR_BINARY + FILE_MAP
fn_script = DIR_SCRIPT + FILE_SCRIPT

sys.stderr.write( '\nRead "%s"\n' % fn_map )

with open( fn_map ) as f:
    MAP = f.readlines()

values = [ None ] * len( VARIABLES )
values[ 0 ] = str( CC )
re_list = [ re.compile( x ) for x in RE_LIST ]

print('RE_LIST')
print('===================')
for r in re_list:
    print(r)
print('===================')

print('Matching regexp...')
for ln in MAP:
    for i, var in enumerate( VARIABLES ):
        if values[ i ] is None:
            m = re_list[ i ].match( ln )
            if m:
                print('===================')
                print(m.groups())
                values[ i ] = m.group( 1 )
                sys.stderr.write( ln )

error = False
for i, ex in enumerate( RE_LIST ):
    print(i, ex)
    if values[ i ] is None:
        if DEFAULTS[ i ] is None:
            sys.stderr.write( 'ERROR: "%s" not found! (%s)\n' % ( ex, fn_map ))
            error = True
        else:
            sys.stderr.write( 'WARNING: "%s" not found! (%s)\n' % ( ex, fn_map ))
            values[ i ] = DEFAULTS[ i ]

if error:
    sys.exit( 1 )

sys.stderr.write( '\nConfigure "%s"\n' % fn_script )

ok = [ 0 ] * len( VARIABLES )
for ln in fileinput.FileInput( fn_script, inplace=1, backup='.bak' ):
    for i, var in enumerate( VARIABLES ):
        if not ok[ i ]:
            ln, ok[ i ] = re.subn( RE_VAR % var, r'\g<1>%s\g<3>' % values[ i ], ln, 1 )
            if ok[ i ]:
                sys.stderr.write( '    ' + ln )
                break
    sys.stdout.write( ln )

for i, var in enumerate( VARIABLES ):
    if not ok[ i ]:
        sys.stderr.write( 'WARNING: "%s" not found! (%s)\n' % ( var, fn_script ))

sys.stderr.write( '\nCopy "%s"\n' % fn_binary )

copyfile( fn_binary, FILE_BIN_R )

sys.stderr.write( '\nDone\n' )
