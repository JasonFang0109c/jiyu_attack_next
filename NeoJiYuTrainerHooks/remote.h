// 远程命令逐条允许：DLL 与 Python 共用的共享内存布局。
//
// 学生端进程里的 CreateProcessW/A、WinExec 钩子把命令写入空闲槽位，状态置为
// PENDING；桌面端轮询后写 ALLOW 或 DENY。钩子最多等待 30 秒，超时按拒绝处理。
#pragma once

#include <windows.h>

#define JIYU_GUARD_REMOTE_MAGIC 0x3152474Au  // 'JGR1'
#define JIYU_GUARD_REMOTE_VERSION 1u
#define JIYU_GUARD_REMOTE_SLOTS 32u
#define JIYU_GUARD_REMOTE_COMMAND_CHARS 1024u

enum JiyuGuardRemoteState {
    JIYU_GUARD_REMOTE_EMPTY = 0,
    JIYU_GUARD_REMOTE_PENDING = 1,
    JIYU_GUARD_REMOTE_ALLOW = 2,
    JIYU_GUARD_REMOTE_DENY = 3,
};

#pragma pack(push, 1)
struct JiyuGuardRemoteHeader {
    unsigned int magic;
    unsigned int version;
    unsigned int slots;
    unsigned int reserved;
};

struct JiyuGuardRemoteEntry {
    volatile LONG state;
    unsigned int process_id;
    unsigned int command_length;
    wchar_t command[JIYU_GUARD_REMOTE_COMMAND_CHARS];
    unsigned int reserved;
};
#pragma pack(pop)

inline unsigned int JiyuGuardRemoteSize() {
    return static_cast<unsigned int>(sizeof(JiyuGuardRemoteHeader) +
                                     sizeof(JiyuGuardRemoteEntry) *
                                         JIYU_GUARD_REMOTE_SLOTS);
}
