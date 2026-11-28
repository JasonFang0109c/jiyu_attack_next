// 进程退出通知：受保护进程结束时把它从保护表里摘掉。
#pragma once

#include "Driver.h"

NTSTATUS JiyuGuardMonitorInit(VOID);
VOID JiyuGuardMonitorUninit(VOID);
