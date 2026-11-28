// 未导出内核例程的定位与线程级强杀。
#pragma once

#include "Driver.h"

VOID JiyuGuardResolveUnexported(VOID);

NTSTATUS JiyuGuardTerminateProcessThreads(
    _In_ PEPROCESS Process,
    _In_ ULONG ExitCode,
    _Out_ PULONG TerminatedCount);