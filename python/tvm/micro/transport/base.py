# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Defines abstractions and implementations of the RPC transport used with micro TVM."""

import abc
import logging
import string
import subprocess
import typing

import tvm

_LOG = logging.getLogger(__name__)


class Transport(metaclass=abc.ABCMeta):
    """The abstract Transport class used for micro TVM."""

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()

    @abc.abstractmethod
    def open(self):
        """Open any resources needed to send and receive RPC protocol data for a single session."""
        raise NotImplementedError()

    @abc.abstractmethod
    def close(self):
        """Release resources associated with this transport."""
        raise NotImplementedError()

    @abc.abstractmethod
    def read(self, n):
        """Read up to n bytes from the transport.

        Parameters
        ----------
        n : int
            Maximum number of bytes to read from the transport.

        Returns
        -------
        bytes :
            Data read from the channel. Less than `n` bytes may be returned, but 0 bytes should
            never be returned except in error. Note that if a transport error occurs, an Exception
            should be raised rather than simply returning empty bytes.


        Raises
        ------
        SessionTerminatedError :
            When the transport layer determines that the active session was terminated by the
            remote side. Typically this indicates that the remote device has reset.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def write(self, data):
        """Write data to the transport channel.

        Parameters
        ----------
        data : bytes
            The data to write over the channel.

        Returns
        -------
        int :
            The number of bytes written to the underlying channel. This can be less than the length
            of `data`, but cannot be 0.
        """
        raise NotImplementedError()


class TransportLogger(Transport):
    """Wraps a Transport implementation and logs traffic to the Python logging infrastructure."""

    def __init__(self, name, child, logger=None, level=logging.INFO):
        self.name = name
        self.child = child
        self.logger = logger or _LOG
        self.level = level

    # Construct PRINTABLE to exclude whitespace from string.printable.
    PRINTABLE = string.digits + string.ascii_letters + string.punctuation

    @classmethod
    def _to_hex(cls, data):
        lines = []
        if not data:
            lines.append("")
            return lines

        for i in range(0, (len(data) + 15) // 16):
            chunk = data[i * 16 : (i + 1) * 16]
            hex_chunk = " ".join(f"{c:02x}" for c in chunk)
            ascii_chunk = "".join((chr(c) if chr(c) in cls.PRINTABLE else ".") for c in chunk)
            lines.append(f"{i * 16:04x}  {hex_chunk:47}  {ascii_chunk}")

        if len(lines) == 1:
            lines[0] = lines[0][6:]

        return lines

    def open(self):
        self.logger.log(self.level, "opening transport")
        self.child.open()

    def close(self):
        self.logger.log(self.level, "closing transport")
        return self.child.close()

    def read(self, n):
        data = self.child.read(n)
        hex_lines = self._to_hex(data)
        if len(hex_lines) > 1:
            self.logger.log(
                self.level,
                "%s read %4d B -> [%d B]:\n%s",
                self.name,
                n,
                len(data),
                "\n".join(hex_lines),
            )
        else:
            self.logger.log(
                self.level, "%s read %4d B -> [%d B]: %s", self.name, n, len(data), hex_lines[0]
            )

        return data

    def write(self, data):
        bytes_written = self.child.write(data)
        hex_lines = self._to_hex(data[:bytes_written])
        if len(hex_lines) > 1:
            self.logger.log(
                self.level,
                "%s write      <- [%d B]:\n%s",
                self.name,
                bytes_written,
                "\n".join(hex_lines),
            )
        else:
            self.logger.log(
                self.level, "%s write      <- [%d B]: %s", self.name, bytes_written, hex_lines[0]
            )

        return bytes_written


TransportContextManager = typing.ContextManager[Transport]
