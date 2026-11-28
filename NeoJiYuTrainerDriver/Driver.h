// JiyuGuard 驱动内部公共头：模块间共享的类型、未导出例程句柄与函数声明。
//
// 只保留 Windows 10/11（19041–26100）可用路径，不再带任何 XP/2003 适配。
#pragma once

#include <ntifs.h>

#include "IoCtl.h"

// 受保护进程表容量，与用户态 IOCTL 行为保持一致。
#define JIYU_GUARD_MAX_PIDS 64
#define JIYU_GUARD_POOL_TAG 'gUYJ'

#ifndef PROCESS_TERMINATE
#define PROCESS_TERMINATE 0x0001
#endif
#ifndef PROCESS_VM_OPERATION
#define PROCESS_VM_OPERATION 0x0008
#endif
#ifndef PROCESS_VM_READ
#define PROCESS_VM_READ 0x0010
#endif
#ifndef PROCESS_VM_WRITE
#define PROCESS_VM_WRITE 0x0020
#endif

// 未导出例程原型：这些函数在 WDK 头里没有声明，统一按内核真实调用约定自己声明，
// 使用前一律判空，拿不到就走 ZwTerminateProcess 回退，绝不空指针调用。
typedef NTSTATUS (NTAPI *JIYU_PSP_TERMINATE_THREAD)(
    _In_ PETHREAD Thread,
    _In_ NTSTATUS ExitStatus,
    _In_ BOOLEAN DirectTerminate);

typedef NTSTATUS (NTAPI *JIYU_PS_SUSPEND_PROCESS)(_In_ PEPROCESS Process);

typedef PETHREAD (NTAPI *JIYU_PS_NEXT_PROCESS_THREAD)(
    _In_ PEPROCESS Process,
    _In_opt_ PETHREAD Thread);

// 由 UnExp.c 在驱动加载时填充，未解析到时保持 NULL。
extern JIYU_PSP_TERMINATE_THREAD g_JiyuGuardTerminateThread;
extern JIYU_PS_SUSPEND_PROCESS g_JiyuGuardSuspendProcess;
extern JIYU_PS_SUSPEND_PROCESS g_JiyuGuardResumeProcess;
extern JIYU_PS_NEXT_PROCESS_THREAD g_JiyuGuardNextProcessThread;

// Driver.c
NTSTATUS JiyuGuardKillProcess(_In_ ULONG ProcessId, _In_ ULONG ExitCode);