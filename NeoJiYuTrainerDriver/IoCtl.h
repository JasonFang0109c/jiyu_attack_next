// JiyuGuard 驱动与用户态共用的 IOCTL 定义。
//
// 设备名、符号链接、服务名与 5 个功能码（0x800–0x804）由用户态与已签名产物依赖，
// 名称与数值都不能改；结构一律按 1 字节对齐，与 ctypes 侧布局保持一致。
#pragma once

#include <devioctl.h>

#define JIYU_GUARD_DEVICE_NAME L"\\Device\\JiyuGuard"
#define JIYU_GUARD_SYMLINK_NAME L"\\??\\JiyuGuard"
#define JIYU_GUARD_DRIVER_VERSION 1u

#define IOCTL_JIYU_GUARD_PROTECT \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_JIYU_GUARD_UNPROTECT \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_JIYU_GUARD_KILL \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_JIYU_GUARD_STATUS \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x803, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_JIYU_GUARD_CLEAR \
    CTL_CODE(FILE_DEVICE_UNKNOWN, 0x804, METHOD_BUFFERED, FILE_ANY_ACCESS)

#pragma pack(push, 1)
typedef struct _JIYU_GUARD_KILL_REQUEST {
    unsigned int process_id;
    unsigned int exit_code;
} JIYU_GUARD_KILL_REQUEST;

typedef struct _JIYU_GUARD_STATUS {
    unsigned int version;
    unsigned int protected_count;
    unsigned int callback_active;
    unsigned int reserved;
} JIYU_GUARD_STATUS;
#pragma pack(pop)