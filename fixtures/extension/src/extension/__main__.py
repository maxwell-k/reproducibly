# SPDX-FileCopyrightText: 2024 Keith Maxwell
#
# SPDX-License-Identifier: MPL-2.0

import ctypes

lib = ctypes.CDLL("./hello.so")
lib.hello_world.restype = ctypes.c_char_p

if __name__ == "__main__":
    print(lib.hello_world().decode("utf-8"))
