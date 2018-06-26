from subprocess import call


def midisend(opcode, mode):
    MIDISEND_BIN = '/home/tobiw/code/rust/midisend/target/release/midisend'
    call([MIDISEND_BIN, '0', str(opcode), str(mode)])
