#!/usr/bin/python
# -----------------------------------------------------------------------------
# Copyright (C) 2012, Robert Johansson <rob@raditex.nu>, Raditex Control AB
# All rights reserved.
#
# This file is part of the rSCADA system.
#
# rSCADA
# http://www.rSCADA.se
# info@rscada.se
# -----------------------------------------------------------------------------

"""
Python bindings for rSCADA libCANopen.
"""

import ctypes as ct
import errno

# libcanopen = ct.cdll.LoadLibrary('libcanopen.so')
# libc = ct.cdll.LoadLibrary('libc.so.6')

libcanopen = ct.CDLL('libcanopen.so', use_errno=True)
libc = ct.CDLL('libc.so.6', use_errno=True)

class CANFrame(ct.Structure):
    _fields_ = [("can_id",  ct.c_uint32),
                ("can_dlc", ct.c_uint8),
                ("align",   ct.c_uint8 * 3),
                ("data",    ct.c_uint8 * 8),
                ]

    def __str__(self):
        data_str = " ".join(["%.2x" % (x,) for x in self.data])
        return ("CAN Frame: ID=%.2x DLC=%.2x DATA=[%s]" %
                (self.can_id, self.can_dlc, data_str))


class CANopenFrame(ct.Structure):
    _fields_ = [("rtr",           ct.c_uint8),
                ("function_code", ct.c_uint8),
                ("type",          ct.c_uint8),
                ("id",            ct.c_uint32),
                ("data",          ct.c_uint8 * 8),  # should be a union...
                ("data_len",      ct.c_uint8),
                ]

    def __str__(self):
        data_str = " ".join(["%.2x" % (x,) for x in self.data])
        return ("CANopen Frame: RTR=%d FC=0x%.2x ID=0x%.2x [len=%d] %s" %
                (self.rtr, self.function_code, self.id,
                 self.data_len, data_str))


class CANopen:

    def __init__(self, interface="can0"):
        """
        Constructor for CANopen class. Optionally takes an interface
        name for which to bind a socket to. Defaults to interface "can0"
        """
        if isinstance(interface, str):
            interface = ct.c_char_p(interface)
        self.sock = libcanopen.can_socket_open(interface)

    def open(self, interface):
        """
        Open a new socket. If open socket already exist, close it first.
        """
        if self.sock:
            self.close()

        if isinstance(interface, str):
            interface = ct.c_char_p(interface.encode())
        self.sock = libcanopen.can_socket_open(interface)

    def close(self):
        """
        Close the socket associated with this class instance.
        """
        if self.sock:
            libcanopen.can_socket_close(self.sock)
            self.sock = None

    def read_can_frame(self):
        """
        Low-level function: Read a CAN frame from socket.
        """
        if self.sock:
            can_frame = CANFrame()
            if libc.read(self.sock, ct.byref(can_frame), ct.c_int(16)) == 16:
                return can_frame
            if ct.get_errno() in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise CANNothingToReadException()
            raise CANframeReadException()
        else:
            raise CANSocketNotConnectedException(socket=self.sock)

    def parse_can_frame(self, can_frame):
        """
        Low level function: Parse a given CAN frame into CANopen frame
        """
        canopen_frame = CANopenFrame()
        if libcanopen.canopen_frame_parse(ct.byref(canopen_frame),
                                          ct.byref(can_frame)) == 0:
            return canopen_frame
        else:
            raise CANopenFrameParseException()

    def read_frame(self):
        """
        Read a CANopen frame from socket. First read a CAN frame, then parse
        into a CANopen frame and return it.
        """
        can_frame = self.read_can_frame()
        if not can_frame:
            raise CANframeReadException()

        canopen_frame = self.parse_can_frame(can_frame)
        if not canopen_frame:
            raise CANopenFrameParseException()

        return canopen_frame

    # -------------------------------------------------------------------------
    # SDO related functions
    #

    #
    # EXPEDIATED
    #

    def SDOUploadExp(self, node, index, subindex):
        """
        Expediated SDO upload
        """
        res = ct.c_uint32()
        ret = libcanopen.canopen_sdo_upload_exp(
            self.sock, ct.c_uint8(node), ct.c_uint16(index),
            ct.c_uint8(subindex), ct.byref(res)
        )

        if ret != 0:
            if ct.get_errno() in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise CANNothingToReadException("Did not get reply")
            raise CANopenSDOUploadException("Expediated Upload returns %s" %
                                            ret)
        return res.msg

    def SDODownloadExp(self, node, index, subindex, data, size):
        """
        Expediated SDO download
        """

        ret = libcanopen.canopen_sdo_download_exp(
            self.sock, ct.c_uint8(node), ct.c_uint16(index),
            ct.c_uint8(subindex), ct.c_uint32(data), ct.c_uint16(size)
        )

        if ret != 0:
            if ct.get_errno() in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise CANNothingToReadException("Did not get reply")
            raise CANopenSDOUploadException("Expediated Download error undefined")

    #
    # SEGMENTED
    #

    def SDOUploadSeg(self, node, index, subindex, size):
        """
        Segmented SDO upload
        """
        data = ct.create_string_buffer(size)
        ret = libcanopen.canopen_sdo_upload_seg(
            self.sock, ct.c_uint8(node), ct.c_uint16(index),
            ct.c_uint8(subindex), data, ct.c_uint16(size)
        )

        if ret < 0:
            raise CANopenSDOUploadException("Segmented Upload returns %s" %
                                            ret)

        hex_str = "".join(["%.2x" % ord(data[i]) for i in range(ret)])
        return hex_str

    def SDODownloadSeg(self, node, index, subindex, str_data, size):
        """
        Segmented SDO download
        """
        m = len(str_data)/2
        data = ct.create_string_buffer(''.join([chr(
            int(str_data[2*n:2*n+2], 16)) for n in range(m)]))

        ret = libcanopen.canopen_sdo_download_seg(
            self.sock, ct.c_uint8(node), ct.c_uint16(index),
            ct.c_uint8(subindex), data, ct.c_uint16(n)
        )

        if ret != 0:
            raise CANopenSDOUploadException("Segmented Download returns %s" %
                                            ret)

    #
    # BLOCK
    #

    def SDOUploadBlock(self, node, index, subindex, size):
        """
        Block SDO upload.
        """
        data = ct.create_string_buffer(size)
        ret = libcanopen.canopen_sdo_upload_block(
            self.sock, ct.c_uint8(node), ct.c_uint16(index),
            ct.c_uint8(subindex), data, ct.c_uint16(size)
        )

        if ret != 0:
            raise CANopenSDOUploadException("Block Upload returns %s" %
                                            ret)

        hex_str = "".join(["%.2x" % ord(d) for d in data])[0:-2]

        return hex_str

    def SDODownloadBlock(self, node, index, subindex, str_data, size):
        """
        Block SDO download.
        """
        m = len(str_data)/2
        data = ct.create_string_buffer(''.join([chr(
            int(str_data[2*n:2*n+2], 16)) for n in range(m)]))

        ret = libcanopen.canopen_sdo_download_block(
            self.sock, ct.c_uint8(node), ct.c_uint16(index),
            ct.c_uint8(subindex), data, ct.c_uint16(n+1)
        )

        if ret != 0:
            raise CANopenSDOUploadException("Block Download returns %s" %
                                            ret)


class CANframeReadException(Exception):

    def __init__(self, msg="", errornr=0):
        self.msg = msg
        self.errornr = errornr

    def __str__(self):
        return "Could not read CAN frame. Error no:%s \n%s" % (self.errornr,
                                                               self.msg)


class CANframeWriteException(Exception):

    def __init__(self, msg="", errornr=0):
        self.msg = msg
        self.errornr = errornr

    def __str__(self):
        return "Could not write CAN frame. Error no:%s \n%s" % (self.errornr,
                                                                self.msg)


class CANSocketNotConnectedException(Exception):

    def __init__(self, msg="", socket="N/A"):
        self.msg = msg
        self.socket = socket

    def __str__(self):
        return "Could not read from socket %s. Socket is not connected" % (
            self.socket, self.msg)


class CANopenFrameParseException(Exception):

    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        return "Could not parse CAN frame to CANopen frame. \n%s" % self.msg


class CANframeParseException(Exception):

    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        return "Could not parse CANopen frame to CAN frame. \n%s" % self.msg


class CANopenSDOUploadException(Exception):

    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        return "Could not perform SDO Upload. \n%s" % self.msg


class CANopenSDODownloadException(Exception):

    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        return "Could not perform SDO Download. \n%s" % self.msg


class CANNothingToReadException(Exception):

    def __init__(self, msg=""):
        self.msg = msg

    def __str__(self):
        return "There is no message on the socket. Don't worry, be happy!"

