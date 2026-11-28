// JiyuGuard 可选内核驱动：进程自保护与内核强杀。
//
// 仅作为本地/隔离环境中的可选组件构建，不随主程序自动加载。
#include <ntddk.h>

#include "driver_ioctl.h"

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

typedef struct _JIYU_GUARD_CONTEXT {
    KSPIN_LOCK lock;
    ULONG pids[JIYU_GUARD_MAX_PIDS];
    ULONG count;
    BOOLEAN callback_active;
} JIYU_GUARD_CONTEXT;

static JIYU_GUARD_CONTEXT g_context;
static PVOID g_registration = NULL;

static BOOLEAN
JiyuGuardIsProtected(_In_ ULONG process_id)
{
    ULONG index;
    BOOLEAN found = FALSE;
    KIRQL irql;

    KeAcquireSpinLock(&g_context.lock, &irql);
    for (index = 0; index < g_context.count; ++index) {
        if (g_context.pids[index] == process_id) {
            found = TRUE;
            break;
        }
    }
    KeReleaseSpinLock(&g_context.lock, irql);
    return found;
}

static BOOLEAN
JiyuGuardAddPid(_In_ ULONG process_id)
{
    ULONG index;
    KIRQL irql;

    KeAcquireSpinLock(&g_context.lock, &irql);
    for (index = 0; index < g_context.count; ++index) {
        if (g_context.pids[index] == process_id) {
            KeReleaseSpinLock(&g_context.lock, irql);
            return TRUE;
        }
    }
    if (g_context.count >= JIYU_GUARD_MAX_PIDS) {
        KeReleaseSpinLock(&g_context.lock, irql);
        return FALSE;
    }
    g_context.pids[g_context.count++] = process_id;
    KeReleaseSpinLock(&g_context.lock, irql);
    return TRUE;
}

static BOOLEAN
JiyuGuardRemovePid(_In_ ULONG process_id)
{
    ULONG index;
    BOOLEAN removed = FALSE;
    KIRQL irql;

    KeAcquireSpinLock(&g_context.lock, &irql);
    for (index = 0; index < g_context.count; ++index) {
        if (g_context.pids[index] == process_id) {
            g_context.pids[index] = g_context.pids[g_context.count - 1];
            --g_context.count;
            removed = TRUE;
            break;
        }
    }
    KeReleaseSpinLock(&g_context.lock, irql);
    return removed;
}

static OB_PREOP_CALLBACK_STATUS
JiyuGuardPreOperation(
    _In_ PVOID registration_context,
    _In_ POB_PRE_OPERATION_INFORMATION information)
{
    ULONG process_id;
    ACCESS_MASK denied;

    UNREFERENCED_PARAMETER(registration_context);

    if (information->KernelHandle) {
        return OB_PREOP_SUCCESS;
    }
    if (information->ObjectType != *PsProcessType) {
        return OB_PREOP_SUCCESS;
    }

    process_id = HandleToULong(PsGetProcessId((PEPROCESS)information->Object));
    if (!JiyuGuardIsProtected(process_id)) {
        return OB_PREOP_SUCCESS;
    }
    if (HandleToULong(PsGetCurrentProcessId()) == process_id) {
        // 保护只拦截其它进程；受保护进程自己仍可正常退出或管理子进程。
        return OB_PREOP_SUCCESS;
    }

    denied = PROCESS_TERMINATE | PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE;
    if (information->Operation == OB_OPERATION_HANDLE_CREATE) {
        information->Parameters->CreateHandleInformation.DesiredAccess &= ~denied;
    } else if (information->Operation == OB_OPERATION_HANDLE_DUPLICATE) {
        information->Parameters->DuplicateHandleInformation.DesiredAccess &= ~denied;
    }
    return OB_PREOP_SUCCESS;
}

static NTSTATUS
JiyuGuardRegisterCallback(VOID)
{
    OB_OPERATION_REGISTRATION operation;
    OB_CALLBACK_REGISTRATION registration;
    UNICODE_STRING altitude;
    NTSTATUS status;

    RtlZeroMemory(&operation, sizeof(operation));
    operation.ObjectType = PsProcessType;
    operation.Operations = OB_OPERATION_HANDLE_CREATE | OB_OPERATION_HANDLE_DUPLICATE;
    operation.PreOperation = JiyuGuardPreOperation;

    RtlInitUnicodeString(&altitude, L"321000");
    RtlZeroMemory(&registration, sizeof(registration));
    registration.Version = OB_FLT_REGISTRATION_VERSION;
    registration.OperationRegistrationCount = 1;
    registration.Altitude = altitude;
    registration.RegistrationContext = NULL;
    registration.OperationRegistration = &operation;

    status = ObRegisterCallbacks(&registration, &g_registration);
    if (NT_SUCCESS(status)) {
        g_context.callback_active = TRUE;
    }
    return status;
}

static VOID
JiyuGuardUnregisterCallback(VOID)
{
    if (g_registration != NULL) {
        ObUnRegisterCallbacks(g_registration);
        g_registration = NULL;
    }
    g_context.callback_active = FALSE;
}

static NTSTATUS
JiyuGuardKillProcess(_In_ ULONG process_id, _In_ ULONG exit_code)
{
    HANDLE process = NULL;
    CLIENT_ID client_id;
    OBJECT_ATTRIBUTES attributes;
    NTSTATUS status;

    if (process_id == 0) {
        return STATUS_INVALID_PARAMETER;
    }
    client_id.UniqueProcess = ULongToHandle(process_id);
    client_id.UniqueThread = NULL;
    InitializeObjectAttributes(&attributes, NULL, OBJ_CASE_INSENSITIVE | OBJ_KERNEL_HANDLE, NULL, NULL);
    status = ZwOpenProcess(&process, PROCESS_TERMINATE, &attributes, &client_id);
    if (!NT_SUCCESS(status)) {
        return status;
    }
    status = ZwTerminateProcess(process, exit_code);
    ZwClose(process);
    return status;
}

static NTSTATUS
JiyuGuardDeviceControl(_In_ PDEVICE_OBJECT device_object, _In_ PIRP irp)
{
    PIO_STACK_LOCATION stack;
    ULONG code;
    ULONG input_length;
    ULONG output_length;
    PVOID buffer;
    NTSTATUS status = STATUS_SUCCESS;
    ULONG bytes = 0;

    UNREFERENCED_PARAMETER(device_object);
    stack = IoGetCurrentIrpStackLocation(irp);
    code = stack->Parameters.DeviceIoControl.IoControlCode;
    input_length = stack->Parameters.DeviceIoControl.InputBufferLength;
    output_length = stack->Parameters.DeviceIoControl.OutputBufferLength;
    buffer = irp->AssociatedIrp.SystemBuffer;

    switch (code) {
    case IOCTL_JIYU_GUARD_PROTECT:
        if (input_length < sizeof(ULONG)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }
        if (!JiyuGuardAddPid(*(ULONG *)buffer)) {
            status = STATUS_INSUFFICIENT_RESOURCES;
        }
        break;
    case IOCTL_JIYU_GUARD_UNPROTECT:
        if (input_length < sizeof(ULONG)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }
        if (!JiyuGuardRemovePid(*(ULONG *)buffer)) {
            status = STATUS_NOT_FOUND;
        }
        break;
    case IOCTL_JIYU_GUARD_KILL:
        if (input_length < sizeof(JIYU_GUARD_KILL_REQUEST)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }
        {
            JIYU_GUARD_KILL_REQUEST *request = (JIYU_GUARD_KILL_REQUEST *)buffer;
            status = JiyuGuardKillProcess(request->process_id, request->exit_code);
        }
        break;
    case IOCTL_JIYU_GUARD_STATUS:
        if (output_length < sizeof(JIYU_GUARD_STATUS)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }
        {
            JIYU_GUARD_STATUS *driver_status = (JIYU_GUARD_STATUS *)buffer;
            driver_status->version = JIYU_GUARD_DRIVER_VERSION;
            driver_status->protected_count = g_context.count;
            driver_status->callback_active = g_context.callback_active ? 1u : 0u;
            driver_status->reserved = 0;
            bytes = sizeof(JIYU_GUARD_STATUS);
        }
        break;
    case IOCTL_JIYU_GUARD_CLEAR:
        {
            KIRQL irql;
            KeAcquireSpinLock(&g_context.lock, &irql);
            g_context.count = 0;
            KeReleaseSpinLock(&g_context.lock, irql);
        }
        break;
    default:
        status = STATUS_INVALID_DEVICE_REQUEST;
        break;
    }

    irp->IoStatus.Status = status;
    irp->IoStatus.Information = bytes;
    IoCompleteRequest(irp, IO_NO_INCREMENT);
    return status;
}

static NTSTATUS
JiyuGuardCreateClose(_In_ PDEVICE_OBJECT device_object, _In_ PIRP irp)
{
    UNREFERENCED_PARAMETER(device_object);
    irp->IoStatus.Status = STATUS_SUCCESS;
    irp->IoStatus.Information = 0;
    IoCompleteRequest(irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

static VOID
JiyuGuardUnload(_In_ PDRIVER_OBJECT driver_object)
{
    UNICODE_STRING symlink;

    UNREFERENCED_PARAMETER(driver_object);
    JiyuGuardUnregisterCallback();
    RtlInitUnicodeString(&symlink, JIYU_GUARD_SYMLINK_NAME);
    IoDeleteSymbolicLink(&symlink);
    if (driver_object->DeviceObject != NULL) {
        IoDeleteDevice(driver_object->DeviceObject);
    }
}

NTSTATUS
DriverEntry(_In_ PDRIVER_OBJECT driver_object, _In_ PUNICODE_STRING registry_path)
{
    NTSTATUS status;
    PDEVICE_OBJECT device_object = NULL;
    UNICODE_STRING device_name;
    UNICODE_STRING symlink;

    UNREFERENCED_PARAMETER(registry_path);
    RtlZeroMemory(&g_context, sizeof(g_context));
    KeInitializeSpinLock(&g_context.lock);

    RtlInitUnicodeString(&device_name, JIYU_GUARD_DEVICE_NAME);
    status = IoCreateDevice(
        driver_object,
        0,
        &device_name,
        FILE_DEVICE_UNKNOWN,
        FILE_DEVICE_SECURE_OPEN,
        FALSE,
        &device_object);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    RtlInitUnicodeString(&symlink, JIYU_GUARD_SYMLINK_NAME);
    status = IoCreateSymbolicLink(&symlink, &device_name);
    if (!NT_SUCCESS(status)) {
        IoDeleteDevice(device_object);
        return status;
    }

    driver_object->MajorFunction[IRP_MJ_CREATE] = JiyuGuardCreateClose;
    driver_object->MajorFunction[IRP_MJ_CLOSE] = JiyuGuardCreateClose;
    driver_object->MajorFunction[IRP_MJ_DEVICE_CONTROL] = JiyuGuardDeviceControl;
    driver_object->DriverUnload = JiyuGuardUnload;

    status = JiyuGuardRegisterCallback();
    if (!NT_SUCCESS(status)) {
        IoDeleteSymbolicLink(&symlink);
        IoDeleteDevice(device_object);
        return status;
    }
    return STATUS_SUCCESS;
}
