// JiyuGuard 可选内核驱动：设备与 IOCTL 分发、内核强杀、卸载清理。
//
// 仅作为本地/隔离环境中的可选组件构建，不随主程序自动加载。
// 设备名 \Device\JiyuGuard、符号链接 \??\JiyuGuard 与 5 个 IOCTL 功能码由用户态
// 与已签名产物依赖，保持与旧实现完全一致。
#include "Driver.h"
#include "Protect.h"
#include "UnExp.h"

// 内核强杀：先走未导出例程逐线程终止，失败再回退 ZwTerminateProcess。
NTSTATUS
JiyuGuardKillProcess(_In_ ULONG ProcessId, _In_ ULONG ExitCode)
{
    PEPROCESS process = NULL;
    NTSTATUS status;
    ULONG terminated = 0;
    HANDLE handle = NULL;
    CLIENT_ID client_id;
    OBJECT_ATTRIBUTES attributes;

    if (ProcessId == 0) {
        return STATUS_INVALID_PARAMETER;
    }

    status = PsLookupProcessByProcessId(ULongToHandle(ProcessId), &process);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    // 首选：拿到 ETHREAD 后用未导出函数终止，能越过普通句柄拿不到
    // PROCESS_TERMINATE 的受保护进程。
    status = JiyuGuardTerminateProcessThreads(process, ExitCode, &terminated);
    ObDereferenceObject(process);
    if (NT_SUCCESS(status) && terminated > 0) {
        return STATUS_SUCCESS;
    }

    // 回退：按句柄终止，走的是系统正常路径。
    client_id.UniqueProcess = ULongToHandle(ProcessId);
    client_id.UniqueThread = NULL;
    InitializeObjectAttributes(&attributes, NULL, OBJ_CASE_INSENSITIVE | OBJ_KERNEL_HANDLE, NULL, NULL);
    status = ZwOpenProcess(&handle, PROCESS_TERMINATE, &attributes, &client_id);
    if (!NT_SUCCESS(status)) {
        DbgPrint("JiyuGuard: ZwOpenProcess(%u) failed 0x%08X\n", ProcessId, status);
        return status;
    }
    status = ZwTerminateProcess(handle, (NTSTATUS)ExitCode);
    ZwClose(handle);
    return status;
}

static NTSTATUS
JiyuGuardDeviceControl(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    PIO_STACK_LOCATION stack;
    ULONG code;
    ULONG input_length;
    ULONG output_length;
    PVOID buffer;
    NTSTATUS status = STATUS_SUCCESS;
    ULONG bytes = 0;

    UNREFERENCED_PARAMETER(DeviceObject);

    stack = IoGetCurrentIrpStackLocation(Irp);
    code = stack->Parameters.DeviceIoControl.IoControlCode;
    input_length = stack->Parameters.DeviceIoControl.InputBufferLength;
    output_length = stack->Parameters.DeviceIoControl.OutputBufferLength;
    buffer = Irp->AssociatedIrp.SystemBuffer;

    switch (code) {
    case IOCTL_JIYU_GUARD_PROTECT:
        if (input_length < sizeof(ULONG)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }
        if (!JiyuGuardProtectAdd(*(ULONG *)buffer)) {
            status = STATUS_INSUFFICIENT_RESOURCES;
        }
        break;
    case IOCTL_JIYU_GUARD_UNPROTECT:
        if (input_length < sizeof(ULONG)) {
            status = STATUS_BUFFER_TOO_SMALL;
            break;
        }
        if (!JiyuGuardProtectRemove(*(ULONG *)buffer)) {
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
            driver_status->protected_count = JiyuGuardProtectedCount();
            driver_status->callback_active = JiyuGuardCallbackActive() ? 1u : 0u;
            driver_status->reserved = 0;
            bytes = sizeof(JIYU_GUARD_STATUS);
        }
        break;
    case IOCTL_JIYU_GUARD_CLEAR:
        JiyuGuardProtectClear();
        break;
    default:
        status = STATUS_INVALID_DEVICE_REQUEST;
        break;
    }

    Irp->IoStatus.Status = status;
    Irp->IoStatus.Information = bytes;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return status;
}

static NTSTATUS
JiyuGuardCreateClose(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    Irp->IoStatus.Status = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

static VOID
JiyuGuardUnload(_In_ PDRIVER_OBJECT DriverObject)
{
    UNICODE_STRING symlink;
    PDEVICE_OBJECT device_object;
    PDEVICE_OBJECT next;

    JiyuGuardProtectUninit();

    RtlInitUnicodeString(&symlink, JIYU_GUARD_SYMLINK_NAME);
    IoDeleteSymbolicLink(&symlink);

    device_object = DriverObject->DeviceObject;
    while (device_object != NULL) {
        next = device_object->NextDevice;
        IoDeleteDevice(device_object);
        device_object = next;
    }
}

NTSTATUS
DriverEntry(_In_ PDRIVER_OBJECT DriverObject, _In_ PUNICODE_STRING RegistryPath)
{
    NTSTATUS status;
    PDEVICE_OBJECT device_object = NULL;
    UNICODE_STRING device_name;
    UNICODE_STRING symlink;

    UNREFERENCED_PARAMETER(RegistryPath);

    // 解析未导出例程：拿不到只记录，强杀自动走 ZwTerminateProcess 回退。
    JiyuGuardResolveUnexported();

    RtlInitUnicodeString(&device_name, JIYU_GUARD_DEVICE_NAME);
    status = IoCreateDevice(
        DriverObject,
        0,
        &device_name,
        FILE_DEVICE_UNKNOWN,
        FILE_DEVICE_SECURE_OPEN,
        FALSE,
        &device_object);
    if (!NT_SUCCESS(status)) {
        DbgPrint("JiyuGuard: IoCreateDevice failed 0x%08X\n", status);
        return status;
    }

    RtlInitUnicodeString(&symlink, JIYU_GUARD_SYMLINK_NAME);
    status = IoCreateSymbolicLink(&symlink, &device_name);
    if (!NT_SUCCESS(status)) {
        DbgPrint("JiyuGuard: IoCreateSymbolicLink failed 0x%08X\n", status);
        IoDeleteDevice(device_object);
        return status;
    }

    DriverObject->MajorFunction[IRP_MJ_CREATE] = JiyuGuardCreateClose;
    DriverObject->MajorFunction[IRP_MJ_CLOSE] = JiyuGuardCreateClose;
    DriverObject->MajorFunction[IRP_MJ_DEVICE_CONTROL] = JiyuGuardDeviceControl;
    DriverObject->DriverUnload = JiyuGuardUnload;

    status = JiyuGuardProtectInit();
    if (!NT_SUCCESS(status)) {
        IoDeleteSymbolicLink(&symlink);
        IoDeleteDevice(device_object);
        return status;
    }

    return STATUS_SUCCESS;
}