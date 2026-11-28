// 未导出内核例程定位与线程级强杀。
//
// 思路照搬上游 JiYuTrainerDriver 的 UnExp.c + KillProcess：先定位未导出的
// PspTerminateThreadByPointer，再对目标进程的每个 ETHREAD 调用它。区别在于
// 这里只保留 Win10/11（19041–26100）可用路径，去掉了 XP/2003 的特征码分支，
// 并且所有地址解析都做了映像范围校验，解析不出来就返回失败交给
// ZwTerminateProcess 回退，不会调用到野指针。
#include "Driver.h"
#include "UnExp.h"

JIYU_PSP_TERMINATE_THREAD g_JiyuGuardTerminateThread = NULL;
JIYU_PS_SUSPEND_PROCESS g_JiyuGuardSuspendProcess = NULL;
JIYU_PS_SUSPEND_PROCESS g_JiyuGuardResumeProcess = NULL;
JIYU_PS_NEXT_PROCESS_THREAD g_JiyuGuardNextProcessThread = NULL;

static PVOID g_JiyuGuardKernelBase = NULL;
static ULONG g_JiyuGuardKernelSize = 0;

// 从任意内核地址按页回退找 MZ 头，得到 ntoskrnl 映像基址。
static PVOID
JiyuGuardFindKernelBase(_In_ PVOID Address)
{
    PUCHAR page;
    ULONG index;

    if (Address == NULL) {
        return NULL;
    }

    page = (PUCHAR)((ULONG_PTR)Address & ~(ULONG_PTR)(PAGE_SIZE - 1));
    for (index = 0; index < 0x2000; ++index) {
        if (!MmIsAddressValid(page)) {
            return NULL;
        }
        if (page[0] == 'M' && page[1] == 'Z') {
            return page;
        }
        page -= PAGE_SIZE;
    }
    return NULL;
}

// 解析 ntoskrnl 的文件头，记下映像范围，用于校验后面的特征码命中是否可信。
static VOID
JiyuGuardLoadKernelRange(_In_ PVOID Address)
{
    PUCHAR base;
    LONG lfanew;
    ULONG size;

    if (g_JiyuGuardKernelBase != NULL) {
        return;
    }

    base = (PUCHAR)JiyuGuardFindKernelBase(Address);
    if (base == NULL) {
        DbgPrint("JiyuGuard: kernel base not found\n");
        return;
    }
    if (!MmIsAddressValid(base + 0x40)) {
        return;
    }

    lfanew = *(LONG *)(base + 0x3C);
    if (lfanew <= 0 || lfanew > 0x1000) {
        return;
    }
    if (!MmIsAddressValid(base + lfanew + 0x60)) {
        return;
    }
    if (*(ULONG *)(base + lfanew) != 0x00004550) { // "PE\0\0"
        return;
    }

    // PE32+ 可选头偏移 0x18，SizeOfImage 在可选头内偏移 0x38。
    size = *(ULONG *)(base + lfanew + 0x18 + 0x38);
    if (size == 0 || size > 0x4000000) {
        return;
    }

    g_JiyuGuardKernelBase = base;
    g_JiyuGuardKernelSize = size;
}

static BOOLEAN
JiyuGuardIsKernelAddress(_In_ ULONG_PTR Address)
{
    if (g_JiyuGuardKernelBase == NULL || g_JiyuGuardKernelSize == 0) {
        return FALSE;
    }
    if (Address < (ULONG_PTR)g_JiyuGuardKernelBase) {
        return FALSE;
    }
    return Address < (ULONG_PTR)g_JiyuGuardKernelBase + g_JiyuGuardKernelSize;
}

// 在 PsTerminateSystemThread 体内找唯一一条 call rel32，它的目标就是
// PspTerminateThreadByPointer。命中必须落在 ntoskrnl 映像内才算数。
static ULONG_PTR
JiyuGuardResolveTerminateThread(VOID)
{
    UNICODE_STRING name;
    PUCHAR start;
    ULONG offset;

    RtlInitUnicodeString(&name, L"PsTerminateSystemThread");
    start = (PUCHAR)MmGetSystemRoutineAddress(&name);
    if (start == NULL) {
        return 0;
    }

    for (offset = 0; offset + 5 < 0x60; ++offset) {
        LONG relative;
        ULONG_PTR target;

        if (!MmIsAddressValid(start + offset + 5)) {
            break;
        }
        if (start[offset] != 0xE8) { // call rel32
            continue;
        }

        RtlCopyMemory(&relative, start + offset + 1, sizeof(relative));
        target = (ULONG_PTR)(start + offset + 5) + (ULONG_PTR)(LONG_PTR)relative;
        if (target == (ULONG_PTR)start) {
            continue;
        }
        if (!JiyuGuardIsKernelAddress(target)) {
            continue;
        }
        if (!MmIsAddressValid((PVOID)target)) {
            continue;
        }
        // 被调函数开头不可能是 int 3 或空字节，命中这两类一律视为误匹配。
        if (*(PUCHAR)target == 0xCC || *(PUCHAR)target == 0x00) {
            continue;
        }
        return target;
    }
    return 0;
}

VOID
JiyuGuardResolveUnexported(VOID)
{
    UNICODE_STRING name;

    if (g_JiyuGuardKernelBase == NULL) {
        RtlInitUnicodeString(&name, L"PsTerminateSystemThread");
        JiyuGuardLoadKernelRange(MmGetSystemRoutineAddress(&name));
    }

    if (g_JiyuGuardTerminateThread == NULL) {
        ULONG_PTR address = JiyuGuardResolveTerminateThread();
        if (address != 0) {
            g_JiyuGuardTerminateThread = (JIYU_PSP_TERMINATE_THREAD)address;
        }
    }

    if (g_JiyuGuardSuspendProcess == NULL) {
        RtlInitUnicodeString(&name, L"PsSuspendProcess");
        *(PVOID *)&g_JiyuGuardSuspendProcess = MmGetSystemRoutineAddress(&name);
    }
    if (g_JiyuGuardResumeProcess == NULL) {
        RtlInitUnicodeString(&name, L"PsResumeProcess");
        *(PVOID *)&g_JiyuGuardResumeProcess = MmGetSystemRoutineAddress(&name);
    }
    if (g_JiyuGuardNextProcessThread == NULL) {
        RtlInitUnicodeString(&name, L"PsGetNextProcessThread");
        *(PVOID *)&g_JiyuGuardNextProcessThread = MmGetSystemRoutineAddress(&name);
    }

    DbgPrint("JiyuGuard: PspTerminateThreadByPointer 0x%p, PsSuspendProcess 0x%p, "
             "PsResumeProcess 0x%p, PsGetNextProcessThread 0x%p\n",
             g_JiyuGuardTerminateThread,
             g_JiyuGuardSuspendProcess,
             g_JiyuGuardResumeProcess,
             g_JiyuGuardNextProcessThread);
}

// 逐个线程调用未导出的 PspTerminateThreadByPointer。
// 线程链拿不到时退回按线程 ID 探测，两条路径都以“至少结束一个线程”为成功。
NTSTATUS
JiyuGuardTerminateProcessThreads(
    _In_ PEPROCESS Process,
    _In_ ULONG ExitCode,
    _Out_ PULONG TerminatedCount)
{
    PETHREAD thread;
    PETHREAD next;
    ULONG count = 0;
    ULONG index;
    BOOLEAN suspended = FALSE;

    if (TerminatedCount == NULL) {
        return STATUS_INVALID_PARAMETER;
    }
    *TerminatedCount = 0;
    if (Process == NULL) {
        return STATUS_INVALID_PARAMETER;
    }
    if (g_JiyuGuardTerminateThread == NULL) {
        return STATUS_NOT_SUPPORTED;
    }

    // 先挂起，避免目标在遍历线程时又开出新线程。
    if (g_JiyuGuardSuspendProcess != NULL &&
        NT_SUCCESS(g_JiyuGuardSuspendProcess(Process))) {
        suspended = TRUE;
    }

    if (g_JiyuGuardNextProcessThread != NULL) {
        thread = g_JiyuGuardNextProcessThread(Process, NULL);
        for (index = 0; thread != NULL && index < 0x1000; ++index) {
            next = g_JiyuGuardNextProcessThread(Process, thread);
            if (NT_SUCCESS(g_JiyuGuardTerminateThread(thread, (NTSTATUS)ExitCode, TRUE))) {
                ++count;
            }
            ObDereferenceObject(thread);
            thread = next;
        }
    } else {
        for (index = 8; index < 0x10000; index += 4) {
            thread = NULL;
            if (!NT_SUCCESS(PsLookupThreadByThreadId(ULongToHandle(index), &thread))) {
                continue;
            }
            if (IoThreadToProcess(thread) == Process) {
                if (NT_SUCCESS(g_JiyuGuardTerminateThread(thread, (NTSTATUS)ExitCode, TRUE))) {
                    ++count;
                }
            }
            ObDereferenceObject(thread);
        }
    }

    if (suspended && g_JiyuGuardResumeProcess != NULL) {
        g_JiyuGuardResumeProcess(Process);
    }

    *TerminatedCount = count;
    return (count > 0) ? STATUS_SUCCESS : STATUS_UNSUCCESSFUL;
}