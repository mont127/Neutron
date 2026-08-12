/* veh.c - minimal repro: does a vectored exception handler's modification of
 * ContextRecord (Rip / Rsp) get honoured when it returns
 * EXCEPTION_CONTINUE_EXECUTION?
 *
 * build: x86_64-w64-mingw32-gcc -O1 -o veh.exe veh.c
 * run:   veh.exe <mode>
 *
 * modes:
 *   1  handler advances Rip past the 2-byte faulting insn        -> expect "OK mode1"
 *   2  handler redirects Rip to a different function (what Mono   -> expect "OK mode2"
 *      does to throw a managed NullReferenceException)
 *   3  handler redirects Rip AND Rsp                              -> expect "OK mode3"
 *   4  handler returns CONTINUE_EXECUTION touching nothing        -> must loop (sanity)
 *   5  handler returns CONTINUE_SEARCH                            -> must die
 */
#include <windows.h>
#include <stdio.h>

#define MAXFAULT 12

static volatile long g_faults = 0;
static int g_mode = 0;
static ULONG64 g_fault_rip = 0;

extern char fault_insn_end[];

static void say(const char *s)
{
    fputs(s, stdout);
    fflush(stdout);
    OutputDebugStringA(s);
}

/* the faulting site. "movl (%rax),%eax" with rax==0 is 2 bytes: 8b 00.
 * fault_insn_end is the address of the next instruction, so the handler can
 * set Rip exactly instead of guessing a length. */
__attribute__((noinline)) static int do_fault(void)
{
    int r;
    __asm__ __volatile__(
        "xor %%eax, %%eax\n\t"
        "movl (%%rax), %%eax\n\t"
        ".globl fault_insn_end\n"
        "fault_insn_end:\n\t"
        "movl $1234, %%eax\n\t"
        : "=a"(r) : : "memory");
    return r;
}

/* mode 2/3 target: never returns, so no fake return address is needed. */
__attribute__((noinline)) static void recovery_fn(void)
{
    char buf[128];
    sprintf(buf, "OK mode%d: reached recovery_fn, faults=%ld\n", g_mode, g_faults);
    say(buf);
    ExitProcess(0);
}

static LONG CALLBACK veh(EXCEPTION_POINTERS *ep)
{
    char buf[256];
    long n;
    DWORD code = ep->ExceptionRecord->ExceptionCode;

    if (code != EXCEPTION_ACCESS_VIOLATION)
        return EXCEPTION_CONTINUE_SEARCH;

    n = ++g_faults;
    if (n == 1) g_fault_rip = ep->ContextRecord->Rip;

    sprintf(buf, "  veh: fault #%ld code=%08lx addr=%p Rip=%p Rsp=%p\n",
            n, (unsigned long)code, ep->ExceptionRecord->ExceptionAddress,
            (void *)(ULONG_PTR)ep->ContextRecord->Rip,
            (void *)(ULONG_PTR)ep->ContextRecord->Rsp);
    say(buf);

    if (n > MAXFAULT) {
        sprintf(buf, "FAIL mode%d: LOOPED - the same instruction faulted %ld times,"
                     " the context modification was NOT honoured\n", g_mode, n);
        say(buf);
        ExitProcess(3);
    }

    switch (g_mode) {
    case 1:
        ep->ContextRecord->Rip = (ULONG64)(ULONG_PTR)fault_insn_end;
        return EXCEPTION_CONTINUE_EXECUTION;
    case 2:
        ep->ContextRecord->Rip = (ULONG64)(ULONG_PTR)recovery_fn;
        return EXCEPTION_CONTINUE_EXECUTION;
    case 3:
        /* move the stack pointer down a page as well, like a throw helper
         * building a fresh frame, keeping (Rsp % 16) == 8 as on function entry */
        ep->ContextRecord->Rsp = ((ep->ContextRecord->Rsp - 4096) & ~(ULONG64)15) + 8;
        ep->ContextRecord->Rip = (ULONG64)(ULONG_PTR)recovery_fn;
        return EXCEPTION_CONTINUE_EXECUTION;
    case 4:
        return EXCEPTION_CONTINUE_EXECUTION; /* nothing changed: must loop */
    case 5:
    default:
        say("  veh: returning EXCEPTION_CONTINUE_SEARCH\n");
        return EXCEPTION_CONTINUE_SEARCH;
    }
}

int main(int argc, char **argv)
{
    char buf[256];
    int r;

    setvbuf(stdout, NULL, _IONBF, 0);
    g_mode = (argc > 1) ? atoi(argv[1]) : 1;

    sprintf(buf, "probe start mode=%d  do_fault=%p fault_insn_end=%p recovery_fn=%p\n",
            g_mode, (void *)do_fault, (void *)fault_insn_end, (void *)recovery_fn);
    say(buf);

    if (!AddVectoredExceptionHandler(1, veh)) { say("AddVectoredExceptionHandler failed\n"); return 9; }

    r = do_fault();

    sprintf(buf, "OK mode%d: do_fault returned %d after %ld fault(s)\n", g_mode, r, g_faults);
    say(buf);
    return 0;
}
