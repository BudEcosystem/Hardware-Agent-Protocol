---
description: "用于 HMS 仿真发现、观测和持久化操作的原生工具与 PTC 工具。"
kind: "package-reference"
---

# @budmh/experimental-tool-hardware

[English](README.md) | 中文

## Summary

用于 HMS 仿真发现、观测和持久化操作的原生工具与 PTC 工具。

## Use this package

挂载 tools 服务和硬件提供者。九个 `hardware_*` 工具公开 discover、describe、observe、namespace、prepare、invoke、operation、events 和 cancel。Prepare 返回不可变请求但不受理；invoke 接受该完整请求。发送结果不确定时，不要重建请求。

## Understand the implementation

规范 JSON 包含 `ok`，以及完整的已验证 `result` 或带未确认状态的类型化 `error`。`attribution` 对象携带 Session 和工具调用标识；HMS 不会将这些标识作为权限接收。注册由插件生命周期管理，卸载会删除所有工具。原生与 PTC 结果使用相同的值。

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
