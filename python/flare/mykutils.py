# -*- coding: utf-8 -*-
# Copyright (C) 2019 FireEye, Inc. All Rights Reserved.

"""IDA utils by @mykill"""

import idc
import idaapi
import idautils
import ida_kernwin

import numbers
from collections import namedtuple

__author__ = 'Michael Bailey'
__copyright__ = 'Copyright (C) 2019 FireEye, Inc.'
__license__ = 'Apache License 2.0'
__version__ = '1.0'

# There is much more to this library, but it needn't be code reviewed or
# publicly released until/unless needed to support future flare-ida tools.

###############################################################################
# Useful tidbits
###############################################################################


def phex(n):
    """Pretty hex.

    The `hex()` function can append a trailing 'L' signifying the long
    datatype. Stripping the trailing 'L' does two things:
    1. Can double click it in the IDA output window to jump to that address
    2. Looks cleaner

    Args:
        n (numbers.Integral): Number to prettify

    Returns:
        Hex string for `n` without trailing 'L'
    """
    return hex(n).rstrip('L')


def get_bitness():
    """Get the architecture bit width of this IDB."""
    inf = idaapi.get_inf_structure()
    return 64 if inf.is_64bit() else 32 if inf.is_32bit() else 16


def for_each_call_to(callback, va=None):
    """For each xref to va that is a call, pass xref va to callback.

    Falls back to highlighted identifier or current location if va is
    unspecified.
    """
    if not va:
        nm = ida_kernwin.get_highlighted_identifier()
        va = idc.LocByName(nm)
        if va >= idaapi.cvar.inf.maxEA:
            va = None

    va = va or idc.here()

    # Obtain and de-duplicate addresses of xrefs that are calls
    callsites = set([x.frm for x in idautils.XrefsTo(va)
                     if idc.GetMnem(x.frm) == 'call'])
    for va in callsites:
        callback(va)

OpSpec = namedtuple('OpSpec', 'pos type name')

def find_instr(va_start, direction, mnems=None, op_specs=[], max_instrs=0):
    """Find an instruction in the current function conforming to the
    specified mnemonics/operands.

    Args:
        va_start (numbers.Integral): Virtual address from whence to begin
            search.
        direction (str): Direction in assembly listing to proceed with search.
            Valid directions are 'up' or 'down'.
        mnems (str or iterable of str): Optional assembly language mnemonic(s)
            to search for.
        op_specs (iterable of OpSpec): Iterable containing OpSpec operand
            specifications.
        max_instrs (numbers.Integral): Number of instructions to search before
            returning None.

    Returns:
        Virtual address where instruction was found
        None if not applicable

    The search begins at the next instruction above or below the specified
    virtual address.

    Notably, upward search scans *decreasing* addresses because the direction
    is with respect to the assembly listing as it appears on the screen, not
    addresses in memory.

    You must specify either one or more mnemonics, or one or more operand
    specifications.

    If max_instrs is left as the default value of zero, this function will scan
    9999 instructions or to the start/end of the function, whichever is first.
    """
    if va_start and (not isinstance(va_start, numbers.Integral)):
        raise ValueError('Invalid va_start')

    va = va_start or here()

    if not max_instrs:
        max_instrs = 9999

    if direction.lower() in ('up', 'back', 'backward', 'previous', 'prev'):
        iterate = idaapi.prev_head
        va_stop = idc.GetFunctionAttr(va, idc.FUNCATTR_START)
        if va_stop == idc.BADADDR:
            va_stop = 0
    elif direction.lower() in ('down', 'forward', 'next'):
        iterate = idaapi.next_head
        va_stop = idc.GetFunctionAttr(va, idc.FUNCATTR_END)
    else:
        raise ValueError('Invalid direction')

    for count in xrange(max_instrs):
        va = iterate(va, va_stop)

        if is_conformant_instr(va, mnems, op_specs):
            return va

        if va in (0, idc.BADADDR):
            break

    return None

def is_conformant_instr(va, mnems, op_specs):
    """Check if instruction at @va conforms to operand specifications list.

    Args:
        va (numbers.Integral): Virtual address of instruction to assess.
        mnems (str or iterable of str): Optional instruction mnemonic(s) to
            check for.
        op_specs (iterable of OpSpec): Iterable containing zero or more operand
            specification tuples (operand position, type, and name).

    Returns:
        True if conformant
        False if nonconformant
    """
    if (not mnems) and (not op_specs):
        msg = 'Must specify either a mnemonic or an operand specification list'
        raise ValueError(msg)

    mnem_current = idc.GetMnem(va)
    if mnems:
        if isinstance(mnems, basestring):
            if mnem_current != mnems:
                return False
        else:
            if mnem_current not in mnems:
                return False

    for spec in op_specs:
        if not is_conformant_operand(va, spec):
            return False

    return True

def is_conformant_operand(va, op_spec):
    """Check that operand conforms to specification.

    Args:
        va (numbers.Integral): Virtual address of instruction to assess.
        op_spec (OpSpec): Operand specification tuple (operand position, type,
            and name)

    Returns:
        True if conformant
        False if nonconformant
    """
    spec = OpSpec(*op_spec)  # Make it convenient to pass plain tuples

    if (spec.pos is None) or ((not spec.name) and (not spec.type)):
        msg = 'Must specify an operand position and either a name or type'
        raise ValueError(msg)

    if spec.type is not None and idc.GetOpType(va, spec.pos) != spec.type:
        return False

    if spec.name is not None:
        # For two types:
        #   3 Base + Index
        #   4 Base + Index + Displacement
        # Use substring matching to compensate for IDA Pro's representation
        if spec.type in (3, 4):
            if spec.name not in idc.GetOpnd(va, spec.pos):
                return False

        # For these types:
        #   5   Immediate
        #   6   Immediate Far Address
        #   7   Immediate Near Address
        # Check both address and name
        elif spec.type in (5, 6, 7):
            if isinstance(spec.name, basestring):
                if idc.GetOpnd(va, spec.pos) != spec.name:
                    return False
            elif idc.GetOperandValue(va, spec.pos) != spec.name:
                return False
        else:
            if idc.GetOpnd(va, spec.pos) != spec.name:
                return False

    return True

