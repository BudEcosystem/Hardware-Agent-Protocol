---
description: "显式启用本地 HMS 仿真的实验性配置层。"
kind: "package-bundle"
---

# @budmh/experimental-hardware-profile

[English](README.md) | 中文

## Summary

显式启用本地 HMS 仿真的实验性配置层。

## Use this package

在 base 配置后应用 `cordis.patch.yml`。启动前将 `HMS_ROOT` 和 `HMS_SOCKET` 设置为绝对路径，或覆盖 `hardware-hms` 配置行。本层挂载原生提供者和工具，不会启动或初始化 HMS。

## Understand the implementation

显式启动独立的 HMS 仿真守护进程。同一 POSIX UID 下的所有参与进程共享权限。本层既不授予每个智能体独立的权限，也不传递委托设备凭据。

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
