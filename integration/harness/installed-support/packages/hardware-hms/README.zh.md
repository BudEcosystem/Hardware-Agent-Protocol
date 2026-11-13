---
description: "通过已验证的 Python 客户端访问本地 Linux HMS 仿真服务。"
kind: "package-reference"
---

# @budmh/experimental-hardware-hms

[English](README.md) | 中文

## Summary

通过已验证的 Python 客户端访问本地 Linux HMS 仿真服务。

## Use this package

配置绝对路径 `hmsRoot` 和 `socketPath`；可选的 `pythonExecutable`、`timeoutMs`（5000）、`graceMs`（1000）和 `maxOutputBytes`（131072）限制每次调用。在同一执行环境中挂载本地 subprocess、sandbox 和 sandbox-policy 提供者。HMS 源代码树必须提供 `hms.client.Client`。

## Understand the implementation

每次调用都在等待前快照参数，启动一个有界 Python 客户端，并验证返回信封。客户端认证本地套接字并验证对应方法的结果。不会自动重试。取消和卸载会终止并等待子进程退出，但 HMS 操作仍可能继续。错误只公开封闭格式的错误码和 `outcome: unconfirmed`；发送后的模式验证失败使用 `INVALID_RESPONSE`。

## Model Experience

### Hardware tool output

#### What the model sees

通过 hardware 工具，模型接收对应调用的规范结果、证据强度和归属标识。此包不会将仿真结果升级为经过验证的物理效果。

#### Token effect

工具模式随配置启用；结果大小受传输限制。原生结果和 PTC 派发记录保留在 Session 中。

#### KV Cache effect

结果追加到现有工具历史。配置或工具模式变化可能改变请求前缀；提供方的缓存可用性不受本包保证。

## Known Limitations and Deferred Work

仅支持本地 Linux、同 UID 的仿真，不支持每个智能体独立认证、真实硬件、HTTP 或远程传输。每次调用启动 Python 的成本可见；没有延迟保证。
