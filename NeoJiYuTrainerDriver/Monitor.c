// 对应上游 Monitor.c：用进程创建/退出回调维护保护表，
// 免掉受保护进程退出后残留的 PID。该回调要求驱动带 /integritycheck
// 并有有效签名，注册失败时只降级记录，不阻止驱动加载。
#include "Monitor.h"
#include "Protect.h"

static BOOLEAN g_monitor_active = FALSE;

static VOID
JiyuGuardProcessNotify(
    _In_ PEPROCESS Process,
    _In_ HANDLE ProcessId,
    _In_opt_ PPS_CREATE_NOTIFY_INFO CreateInfo)
{
    UNREFERENCED_PARAMETER(Process);

    // CreateInfo 非空表示进程创建，这里只关心退出。
    if (CreateInfo != NULL) {
        return;
    }

    JiyuGuardProtectRemove((ULONG)(ULONG_PTR)ProcessId);
}

NTSTATUS
JiyuGuardMonitorInit(VOID)
{
    NTSTATUS status;

    status = PsSetCreateProcessNotifyRoutineEx(JiyuGuardProcessNotify, FALSE);
    if (!NT_SUCCESS(status)) {
        DbgPrint("JiyuGuard: PsSetCreateProcessNotifyRoutineEx failed 0x%08X\n", status);
        return status;
    }

    g_monitor_active = TRUE;
    return STATUS_SUCCESS;
}

VOID
JiyuGuardMonitorUninit(VOID)
{
    if (!g_monitor_active) {
        return;
    }

    PsSetCreateProcessNotifyRoutineEx(JiyuGuardProcessNotify, TRUE);
    g_monitor_active = FALSE;
}
