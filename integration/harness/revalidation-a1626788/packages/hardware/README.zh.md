---
description: "独立认证硬件提供者的类型化服务定义。"
kind: "package-reference"
---

# @budmh/experimental-hardware

[English](README.md) | 中文

## Summary

独立认证硬件提供者的类型化服务定义。

## Use this package

消费者注入 `hardware` 并调用 `request(method, params, { agent, signal })`。提供者负责认证和响应验证。Session 标识仅用于归属记录和现有文件策略。

## Understand the implementation

回复区分已验证结果和状态未确认的错误码。调用方停止等待后，已接受的操作仍可能继续。保留原始 invoke 信封，并先检查持久化操作状态，再决定下一步。

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
