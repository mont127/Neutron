/* veh2.c - does each VEH-handled fault that returns EXCEPTION_CONTINUE_EXECUTION
 * leak stack?  ULTRAKILL dies after ~305 faults with Rsp below the whole 1MB
 * stack, i.e. ~3.4KB lost per dispatch.  Fault N times in a loop, each time the
 * handler advances Rip, and print the handler's OWN stack address (not the
 * ContextRecord Rsp) so any drift is visible.
 *
 * build: x86_64-w64-mingw32-gcc -O1 -o veh2.exe veh2.c
 * run:   veh2.exe [iterations] [mode]
 *   mode 1 (default) advance Rip     mode 2 redirect Rip to a resume stub
 */
#include <windows.h>
#include <stdio.h>

static volatile long g_faults = 0;
static int g_mode = 1;
static char *g_first_handler_sp = 0;
static char *g_last_handler_sp = 0;
static ULONG64 g_first_ctx_rsp = 0;

extern char fault_insn_end2[];

static void say(const char *s) { fputs(s, stdout); fflush(stdout); }

__attribute__((noinline)) static int do_fault(void)
{
    int r;
    __asm__ __volatile__(
        "xor %%eax, %%eax\n\t"
        "movl (%%rax), %%eax\n\t"
        ".globl fault_insn_end2\n"
        "fault_insn_end2:\n\t"
        "movl $1, %%eax\n\t"
        : "=a"(r) : : "memory");
    return r;
}

static LONG CALLBACK veh(EXCEPTION_POINTERS *ep)
{
    char buf[256];
    char here;              /* address of this = the real stack depth right now */
    long n;

    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION)
        return EXCEPTION_CONTINUE_SEARCH;

    n = ++g_faults;
    if (n == 1) {
        g_first_handler_sp = &here;
        g_first_ctx_rsp = ep->ContextRecord->Rsp;
    }
    g_last_handler_sp = &here;

    if (n <= 3 || (n % 50) == 0) {
        sprintf(buf, "  fault #%-4ld handler_sp=%p (drift %+lld)  ctx.Rsp=%p (drift %+lld)\n",
                n, (void *)&here, (long long)(&here - g_first_handler_sp),
                (void *)(ULONG_PTR)ep->ContextRecord->Rsp,
                (long long)(ep->ContextRecord->Rsp - g_first_ctx_rsp));
        say(buf);
    }
    ep->ContextRecord->Rip = (ULONG64)(ULONG_PTR)fault_insn_end2;
    return EXCEPTION_CONTINUE_EXECUTION;
}

int main(int argc, char **argv)
{
    char buf[256];
    int i, iters = 500;
    MEMORY_BASIC_INFORMATION mbi;
    char probe;

    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc > 1) iters = atoi(argv[1]);
    if (argc > 2) g_mode = atoi(argv[2]);

    VirtualQuery(&probe, &mbi, sizeof(mbi));
    sprintf(buf, "veh2 start iters=%d  stack alloc_base=%p  main_sp=%p\n",
            iters, mbi.AllocationBase, (void *)&probe);
    say(buf);

    if (!AddVectoredExceptionHandler(1, veh)) { say("AVEH failed\n"); return 9; }

    for (i = 0; i < iters; i++) do_fault();

    sprintf(buf, "DONE: %ld faults survived. handler_sp drift over the run = %+lld bytes"
                 " (%.1f bytes/fault)\n",
            g_faults, (long long)(g_last_handler_sp - g_first_handler_sp),
            g_faults > 1 ? (double)(g_last_handler_sp - g_first_handler_sp) / (double)(g_faults - 1) : 0.0);
    say(buf);
    return 0;
}
