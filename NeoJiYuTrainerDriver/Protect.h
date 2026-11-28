// 进程自保护：ObRegisterCallbacks 回调注册与受保护 PID 表。
#pragma once

#include "Driver.h"

// 回调高度值，与上游 JiYuTrainerDriver 保持一致。
#define JIYU_GUARD_ALTITUDE L"321000"

NTSTATUS JiyuGuardProtectInit(VOID);
VOID JiyuGuardProtectUninit(VOID);

BOOLEAN JiyuGuardIsProtected(_In_ ULONG ProcessId);
BOOLEAN JiyuGuardProtectAdd(_In_ ULONG ProcessId);
BOOLEAN JiyuGuardProtectRemove(_In_ ULONG ProcessId);
VOID JiyuGuardProtectClear(VOID);

ULONG JiyuGuardProtectedCount(VOID);
BOOLEAN JiyuGuardCallbackActive(VOID);