/* veh3.c - the Boehm-GC write-barrier shape.
 *
 * mono-2.0-BDWGC installs a vectored handler (GC_write_fault_handler) that
 * catches an ACCESS_VIOLATION on a write-protected heap page, calls
 * VirtualProtect() to make the page writable, marks it dirty, and returns
 * EXCEPTION_CONTINUE_EXECUTION *without touching Rip* - the faulting store is
 * re-executed and must now succeed.  If the new protection is not visible to
 * the re-executed instruction, the same instruction faults forever.  That is
 * exactly the ULTRAKILL signature: ~305 AVs at one address, all dispatched to
 * mono-2.0-bdwgc's VEH, then stack exhaustion.
 *
 * build: x86_64-w64-mingw32-gcc -O1 -o veh3.exe veh3.c
 * run:   veh3.exe [mode]
 *   1 PAGE_READONLY -> PAGE_READWRITE on a write fault   (the Boehm case)
 *   2 PAGE_NOACCESS -> PAGE_READWRITE on a read fault
 *   3 like 1 but the store is executed from JIT-like RWX memory
 *   4 like 1 but the handler VirtualProtects and ALSO advances Rip (control:
 *     proves the fault site itself is fine)
 */
#include <windows.h>
#include <stdio.h>

#define MAXFAULT 12

static volatile long g_faults = 0;
static int g_mode = 1;
static char *g_page = 0;
static void *g_resume = 0;

extern char store_end[];

static void say(const char *s) { fputs(s, stdout); fflush(stdout); }

/* "movl $0x2a,(%rcx)" then a label: the store is what faults */
__attribute__((noinline)) static void do_store(void *p)
{
    __asm__ __volatile__(
        "movl $42, (%%rcx)\n\t"
        ".globl store_end\n"
        "store_end:\n\t"
        "nop\n\t"
        : : "c"(p) : "memory");
}

static LONG CALLBACK veh(EXCEPTION_POINTERS *ep)
{
    char buf[256];
    DWORD old = 0;
    long n;
    BOOL ok;
    ULONG_PTR kind, addr;

    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION)
        return EXCEPTION_CONTINUE_SEARCH;

    kind = ep->ExceptionRecord->ExceptionInformation[0]; /* 0 read, 1 write */
    addr = ep->ExceptionRecord->ExceptionInformation[1];
    n = ++g_faults;

    ok = VirtualProtect(g_page, 4096, PAGE_READWRITE, &old);

    sprintf(buf, "  veh: fault #%-3ld %s at %p Rip=%p | VirtualProtect->RW %s (old=%lx)\n",
            n, kind ? "WRITE" : "read", (void *)addr,
            (void *)(ULONG_PTR)ep->ContextRecord->Rip,
            ok ? "ok" : "FAILED", (unsigned long)old);
    say(buf);

    if (n > MAXFAULT) {
        sprintf(buf, "FAIL mode%d: LOOPED - the store re-faulted %ld times even though"
                     " VirtualProtect made the page writable.  This IS the ULTRAKILL bug.\n",
                g_mode, n);
        say(buf);
        ExitProcess(3);
    }

    if (g_mode == 4)
        ep->ContextRecord->Rip = (ULONG64)(ULONG_PTR)g_resume;
    return EXCEPTION_CONTINUE_EXECUTION;
}

/* copy do_store into fresh RWX memory so the faulting store runs from a page
 * Rosetta has never seen before, like Mono's JIT output */
typedef void (*storefn)(void *);
static storefn make_jit_store(void **resume_out)
{
    /* mov $42,(%rcx) ; nop ; ret   -> c7 01 2a 00 00 00 | 90 | c3 */
    static const unsigned char code[] = { 0xc7, 0x01, 0x2a, 0x00, 0x00, 0x00, 0x90, 0xc3 };
    unsigned char *m = VirtualAlloc(NULL, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!m) return NULL;
    memcpy(m, code, sizeof(code));
    FlushInstructionCache(GetCurrentProcess(), m, sizeof(code));
    *resume_out = m + 6;
    return (storefn)m;
}

int main(int argc, char **argv)
{
    char buf[256];
    DWORD old = 0, want;
    MEMORY_BASIC_INFORMATION mbi;
    storefn jit = NULL;

    setvbuf(stdout, NULL, _IONBF, 0);
    g_mode = (argc > 1) ? atoi(argv[1]) : 1;
    g_resume = store_end;

    g_page = VirtualAlloc(NULL, 4096, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!g_page) { say("VirtualAlloc failed\n"); return 9; }
    *(volatile int *)g_page = 1;              /* touch it while it is writable */

    if (g_mode == 3) {
        jit = make_jit_store(&g_resume);
        if (!jit) { say("jit alloc failed\n"); return 9; }
    }

    want = (g_mode == 2) ? PAGE_NOACCESS : PAGE_READONLY;
    if (!VirtualProtect(g_page, 4096, want, &old)) { say("VirtualProtect failed\n"); return 9; }
    VirtualQuery(g_page, &mbi, sizeof(mbi));
    sprintf(buf, "veh3 mode=%d page=%p protected as %s (VirtualQuery says %lx)\n",
            g_mode, g_page, (g_mode == 2) ? "NOACCESS" : "READONLY",
            (unsigned long)mbi.Protect);
    say(buf);

    if (!AddVectoredExceptionHandler(1, veh)) { say("AVEH failed\n"); return 9; }

    if (g_mode == 2) {
        volatile int v = *(volatile int *)g_page;
        sprintf(buf, "OK mode2: read %d after %ld fault(s)\n", v, g_faults);
    } else if (g_mode == 3) {
        jit(g_page);
        sprintf(buf, "OK mode3: JIT store, page now holds %d after %ld fault(s)\n",
                *(volatile int *)g_page, g_faults);
    } else {
        do_store(g_page);
        sprintf(buf, "OK mode%d: page now holds %d after %ld fault(s)\n",
                g_mode, *(volatile int *)g_page, g_faults);
    }
    say(buf);
    return 0;
}
