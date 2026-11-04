#!/usr/bin/env python3
"""用本机 IPv4 地址验证报文发送与接收，无需第二台测试设备。"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import core  # noqa: E402  (需要先把仓库根加入 sys.path)


class TestFailure(RuntimeError):
    pass


class LocalReceiver:
    def __init__(self, target, port=0):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.bind((target, port))
        except OSError as error:
            self.socket.close()
            raise TestFailure(
                "无法在 %s:%d 监听：%s" % (target, port, error)
            ) from error
        self.target, self.port = self.socket.getsockname()[:2]

    def collect(self, count, timeout):
        packets = []
        deadline = time.monotonic() + timeout
        while len(packets) < count:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self.socket.settimeout(remaining)
            try:
                packet, _ = self.socket.recvfrom(65535)
            except TimeoutError:
                break
            packets.append(packet)
        return packets

    def close(self):
        self.socket.close()


def decode_text(packet, offset):
    return packet[offset:].decode("utf-16-le", errors="replace").split("\x00", 1)[0]


def send_once(target, port, **kwargs):
    options = core.SendOptions(target=target, port=port, **kwargs)
    expected = len(core.prepare_packets(options))
    try:
        core.execute_send(options)
    except Exception as error:
        raise TestFailure("发送失败：%s" % error) from error
    return expected


def check_packets(label, packets, expected, kwargs, timeout):
    if len(packets) != expected:
        raise TestFailure(
            "%s：预期收到 %d 个报文，实际收到 %d 个（等待 %.1f 秒）"
            % (label, expected, len(packets), timeout)
        )
    for packet in packets:
        if packet[:4] != b"DMOC":
            raise TestFailure("%s：报文缺少 DMOC 标识" % label)
        if "message" in kwargs:
            actual = decode_text(packet, core.MESSAGE_OFFSET)
            if actual != kwargs["message"]:
                raise TestFailure("%s：消息内容不一致：%r" % (label, actual))
        elif "command" in kwargs:
            actual = decode_text(packet, core.COMMAND_OFFSET)
            if actual != kwargs["command"]:
                raise TestFailure("%s：命令内容不一致：%r" % (label, actual))
        elif kwargs.get("extra") in ("r", "s"):
            code = 0x13 if kwargs["extra"] == "r" else 0x14
            if len(packet) <= 52 or packet[52] != code:
                raise TestFailure("%s：命令码不是 0x%02x" % (label, code))
        elif kwargs.get("extra") == "l":
            actual = decode_text(packet, core.COMMAND_OFFSET)
            if actual != core.LOGOFF_COMMAND:
                raise TestFailure("%s：注销命令不一致：%r" % (label, actual))
    return len(packets)


def run(target, port, timeout, repeat):
    address = ipaddress.IPv4Address(target)
    if address.is_unspecified or address.is_multicast:
        raise TestFailure("目标必须是可以绑定监听的本机单播 IPv4 地址")

    receiver = LocalReceiver(target, port)
    cases = [
        ("文本消息", {"message": "本机 IP 自测消息"}),
        ("远程命令", {"command": "whoami"}),
        ("重启指令", {"extra": "r"}),
        ("关机指令", {"extra": "s"}),
        ("注销指令", {"extra": "l"}),
    ]
    total = 0
    passed = 0
    try:
        print("目标地址：%s" % receiver.target)
        print("接收端口：%d" % receiver.port)
        print("超时时间：%.1f 秒" % timeout)
        print()

        for label, kwargs in cases:
            expected = send_once(receiver.target, receiver.port, **kwargs)
            packets = receiver.collect(expected, timeout)
            total += check_packets(label, packets, expected, kwargs, timeout)
            passed += 1
            print("通过：%s（%d 个报文）" % (label, expected))

        burst = {"message": "本机连续发送测试"}
        per_send = len(
            core.prepare_packets(
                core.SendOptions(target=receiver.target, port=receiver.port, **burst)
            )
        )
        for _ in range(repeat):
            send_once(receiver.target, receiver.port, **burst)
        expected = per_send * repeat
        packets = receiver.collect(expected, timeout)
        total += check_packets("连续发送", packets, expected, burst, timeout)
        passed += 1
        print("通过：连续发送 %d 次（%d 个报文）" % (repeat, expected))
    finally:
        receiver.close()

    print()
    print("全部通过：%d 项检查，共验证 %d 个报文。" % (passed, total))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="向本机 IPv4 地址发送报文并校验回环接收，无需第二台测试设备。"
    )
    parser.add_argument("--target", help="本机 IPv4 地址；默认自动检测当前局域网地址")
    parser.add_argument(
        "--port", type=int, default=0, help="本机接收端口；默认使用系统分配的空闲端口"
    )
    parser.add_argument(
        "--timeout", type=float, default=3.0, help="等待报文到达的秒数，默认 3"
    )
    parser.add_argument(
        "--repeat", type=int, default=3, help="连续发送检查的次数，默认 3"
    )
    args = parser.parse_args(argv)

    if not 0 <= args.port <= 65535:
        parser.error("--port 必须在 0 到 65535 之间")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    if args.repeat < 1:
        parser.error("--repeat 必须大于 0")

    target = args.target or core.detect_local_ip()
    if not target:
        target = "127.0.0.1"
        print("未能自动检测局域网地址，改用回环地址 127.0.0.1。")
    try:
        run(target, args.port, args.timeout, args.repeat)
    except (TestFailure, ValueError, OSError) as error:
        print("失败：%s" % error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
