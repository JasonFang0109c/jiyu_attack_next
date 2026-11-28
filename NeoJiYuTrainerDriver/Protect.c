// 进程自保护：用 ObRegisterCallbacks 拦进程句柄的危险权限。
//
// 受保护进程的普通句柄打开、句柄复制都会被剥掉 PROCESS_TERMINATE /
// PROCESS_VM_OPERATION / PROCESS_VM_READ / PROCESS_VM_WRITE，因此任务管理器、
// 常见结束进程工具拿不到强杀权限；受保护进程自己不受影响，仍可正常退出。
#include "Driver.h"
#include "Protect.h"

typedef struct _JIYU_GUARD_PROTECT_STATE {
    KSPIN_LOCK Lock;
    ULONG Pids[JIYU_GUARD_MAX_PIDS];
    ULONG Count;
    BOOLEAN CallbackActive;
} JIYU_GUARD_PROTECT_STATE;

static JIYU_GUARD_PROTECT_STATE g_JiyuGuardProtect;
static PVOID g_JiyuGuardRegistration = NULL;

// 回调函数：进程句柄即将创建或复制时调用。
static OB_PREOP_CALLBACK_STATUS
JiyuGuardPreOperation(
    _In_ PVOID RegistrationContext,
    _In_ POB_PRE_OPERATION_INFORMATION Information)
{
    ULONG process_id;
    ACCESS_MASK denied;

    UNREFERENCED_PARAMETER(RegistrationContext);

    if (Information->KernelHandle) {
        return OB_PREOP_SUCCESS;
    }
    if (Information->ObjectType != *PsProcessType) {
        return OB_PREOP_SUCCESS;
    }

    process_id = HandleToULong(PsGetProcessId((PEPROCESS)Information->Object));
    if (!JiyuGuardIsProtected(process_id)) {
        return OB_PREOP_SUCCESS;
    }
    if (HandleToULong(PsGetCurrentProcessId()) == process_id) {
        // 保护只拦截其它进程；受保护进程自己仍可正常退出或管理子进程。
        return OB_PREOP_SUCCESS;
    }

    denied = PROCESS_TERMINATE | PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE;
    if (Information->Operation == OB_OPERATION_HANDLE_CREATE) {
        Information->Parameters->CreateHandleInformation.DesiredAccess &= ~denied;
    } else if (Information->Operation == OB_OPERATION_HANDLE_DUPLICATE) {
        Information->Parameters->DuplicateHandleInformation.DesiredAccess &= ~denied;
    }
    return OB_PREOP_SUCCESS;
}

NTSTATUS
JiyuGuardProtectInit(VOID)
{
    OB_OPERATION_REGISTRATION operation;
    OB_CALLBACK_REGISTRATION registration;
    UNICODE_STRING altitude;
    NTSTATUS status;

    KeInitializeSpinLock(&g_JiyuGuardProtect.Lock);
    g_JiyuGuardProtect.Count = 0;
    g_JiyuGuardProtect.CallbackActive = FALSE;

    RtlZeroMemory(&operation, sizeof(operation));
    operation.ObjectType = PsProcessType;
    operation.Operations = OB_OPERATION_HANDLE_CREATE | OB_OPERATION_HANDLE_DUPLICATE;
    operation.PreOperation = JiyuGuardPreOperation;

    RtlInitUnicodeString(&altitude, JIYU_GUARD_ALTITUDE);
    RtlZeroMemory(&registration, sizeof(registration));
    registration.Version = ObGetFilterVersion();
    registration.OperationRegistrationCount = 1;
    registration.Altitude = altitude;
    registration.RegistrationContext = NULL;
    registration.OperationRegistration = &operation;

    status = ObRegisterCallbacks(&registration, &g_JiyuGuardRegistration);
    if (!NT_SUCCESS(status)) {
        DbgPrint("JiyuGuard: ObRegisterCallbacks failed 0x%08X\n", status);
        return status;
    }
    g_JiyuGuardProtect.CallbackActive = TRUE;
    return STATUS_SUCCESS;
}

VOID
JiyuGuardProtectUninit(VOID)
{
    if (g_JiyuGuardRegistration != NULL) {
        ObUnRegisterCallbacks(g_JiyuGuardRegistration);
        g_JiyuGuardRegistration = NULL;
    }
    g_JiyuGuardProtect.CallbackActive = FALSE;
    g_JiyuGuardProtect.Count = 0;
}

BOOLEAN
JiyuGuardIsProtected(_In_ ULONG ProcessId)
{
    ULONG index;
    BOOLEAN found = FALSE;
    KIRQL irql;

    if (ProcessId == 0) {
        return FALSE;
    }

    KeAcquireSpinLock(&g_JiyuGuardProtect.Lock, &irql);
    for (index = 0; index < g_JiyuGuardProtect.Count; ++index) {
        if (g_JiyuGuardProtect.Pids[index] == ProcessId) {
            found = TRUE;
            break;
        }
    }
    KeReleaseSpinLock(&g_JiyuGuardProtect.Lock, irql);
    return found;
}

BOOLEAN
JiyuGuardProtectAdd(_In_ ULONG ProcessId)
{
    ULONG index;
    KIRQL irql;

    if (ProcessId == 0) {
        return FALSE;
    }

    KeAcquireSpinLock(&g_JiyuGuardProtect.Lock, &irql);
    for (index = 0; index < g_JiyuGuardProtect.Count; ++index) {
        if (g_JiyuGuardProtect.Pids[index] == ProcessId) {
            KeReleaseSpinLock(&g_JiyuGuardProtect.Lock, irql);
            return TRUE;
        }
    }
    if (g_JiyuGuardProtect.Count >= JIYU_GUARD_MAX_PIDS) {
        KeReleaseSpinLock(&g_JiyuGuardProtect.Lock, irql);
        return FALSE;
    }
    g_JiyuGuardProtect.Pids[g_JiyuGuardProtect.Count++] = ProcessId;
    KeReleaseSpinLock(&g_JiyuGuardProtect.Lock, irql);
    return TRUE;
}

BOOLEAN
JiyuGuardProtectRemove(_In_ ULONG ProcessId)
{
    ULONG index;
    BOOLEAN removed = FALSE;
    KIRQL irql;

    if (ProcessId == 0) {
        return FALSE;
    }

    KeAcquireSpinLock(&g_JiyuGuardProtect.Lock, &irql);
    for (index = 0; index < g_JiyuGuardProtect.Count; ++index) {
        if (g_JiyuGuardProtect.Pids[index] == ProcessId) {
            g_JiyuGuardProtect.Pids[index] =
                g_JiyuGuardProtect.Pids[g_JiyuGuardProtect.Count - 1];
            --g_JiyuGuardProtect.Count;
            removed = TRUE;
            break;
        }
    }
    KeReleaseSpinLock(&g_JiyuGuardProtect.Lock, irql);
    return removed;
}

VOID
JiyuGuardProtectClear(VOID)
{
    KIRQL irql;

    KeAcquireSpinLock(&g_JiyuGuardProtect.Lock, &irql);
    g_JiyuGuardProtect.Count = 0;
    KeReleaseSpinLock(&g_JiyuGuardProtect.Lock, irql);
}

ULONG
JiyuGuardProtectedCount(VOID)
{
    ULONG count;
    KIRQL irql;

    KeAcquireSpinLock(&g_JiyuGuardProtect.Lock, &irql);
    count = g_JiyuGuardProtect.Count;
    KeReleaseSpinLock(&g_JiyuGuardProtect.Lock, irql);
    return count;
}

BOOLEAN
JiyuGuardCallbackActive(VOID)
{
    return g_JiyuGuardProtect.CallbackActive;
}