// SPDX-FileCopyrightText: 2024 Keith Maxwell
//
// SPDX-License-Identifier: MPL-2.0

// gcc -shared -o hello.so -fPIC src/hello.c
#include <stdio.h>

const char* hello_world() {
    return "hello world";
}
