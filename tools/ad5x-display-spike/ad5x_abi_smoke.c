#include <gnu/libc-version.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/utsname.h>

int main(void) {
    union {
        uint32_t value;
        unsigned char bytes[4];
    } endian = { .value = 0x01020304u };

    struct utsname uts;
    int uname_ok = uname(&uts) == 0;

    puts("ad5x-abi-smoke: ok");
    printf("sizeof(void*)=%zu\n", sizeof(void *));
    printf("endianness=%s\n", endian.bytes[0] == 0x04 ? "little" : "big-or-unknown");
    printf("glibc=%s\n", gnu_get_libc_version());

#ifdef __mips__
    printf("__mips=%d\n", __mips);
#else
    puts("__mips=not-defined");
#endif

#ifdef __mips_isa_rev
    printf("__mips_isa_rev=%d\n", __mips_isa_rev);
#else
    puts("__mips_isa_rev=not-defined");
#endif

#ifdef __mips_nan2008
    puts("nan2008=yes");
#else
    puts("nan2008=no");
#endif

#ifdef _MIPS_SIM
    printf("_MIPS_SIM=%d\n", _MIPS_SIM);
#endif

    if (uname_ok) {
        printf("uname.sysname=%s\n", uts.sysname);
        printf("uname.release=%s\n", uts.release);
        printf("uname.machine=%s\n", uts.machine);
    } else {
        puts("uname=failed");
    }

    return 0;
}
