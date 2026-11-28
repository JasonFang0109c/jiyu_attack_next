// 课堂防护 DLL 与 Python 注入端共用的策略结构，必须保持 16 字节定长。
#pragma once

#define JIYU_GUARD_POLICY_MAGIC 0x3150474Au  // 'JGP1'
#define JIYU_GUARD_POLICY_VERSION 1u

// 策略位与 NeoJiYuTrainer/Features/Classroom/Data.py 的 GUARD_* 常量一一对应。
enum JiyuGuardFlags {
    JIYU_GUARD_ANTI_MONITOR = 1u << 0,
    JIYU_GUARD_ANTI_CONTROL = 1u << 1,
    JIYU_GUARD_BLOCK_CLOSE = 1u << 2,
    JIYU_GUARD_BLOCK_TERMINATE = 1u << 3,
    JIYU_GUARD_BLOCK_REMOTE = 1u << 4,
};

#pragma pack(push, 1)
struct JiyuGuardPolicy {
    unsigned int magic;
    unsigned int version;
    unsigned int flags;
    unsigned int reserved;
};
#pragma pack(pop)
