# 验证记录

实测环境为 Windows、AstrBot 4.29.4、WeChat Native 0.3.21 和 agent-wechat 2.7.1。聊天使用 AstrBot 本地 Agent 和支持图片的模型。连发测试使用思维链式消息防抖 1.5.0。

| 场景 | 结果 |
| --- | --- |
| 安装与启停 | 通过 AstrBot 面板安装 ZIP 并单独启用插件。隔离测试验证了停用会释放独立 SSE、HTTP 客户端和转换线程。 |
| 并行接收 | 新插件的独立 SSE 与原适配器同时连接。已验证旧版 Native 的最新游标定位。 |
| 单发表情 | 真实微信私聊收到静态及动态原生表情。静态样本转成 PNG，动态样本转成四帧 PNG 拼图并进入原会话。 |
| 表情与文字连发 | 真实私聊中，现有防抖插件把表情和紧随其后的文字并入同一个回复窗口。 |
| 模型使用图片 | 0.2.2 的一次真实私聊复测中，模型收到转换后的表情图和语境说明，微信收到接续对话且省略画面细节的回复。 |
| 本地自动测试 | 七项测试通过，覆盖会话 ID 编码、表情类型、SSE 事件筛选、回环地址限制、透明度、动图帧顺序及异常媒体。 |

分享表情、多联系人并行、普通图片现场回归和卸载回归仍待完整实测。当前插件面向允许名单中的私聊。

## 0.3.0 本地验证

在本机 Python 3.12 与已安装的 AstrBot 运行环境中，33 项自动测试通过。新增测试使用本地模拟 Native HTTP 服务及真实 AstrBot 消息组件，覆盖引用父消息的媒体路径、`source=quote` 与普通媒体隔离、预览、待下载状态、缺失引用的原表情查找、本人发出表情、跨会话拒绝、撤回检查、原事件补图与文字保留、已有图片去重、合并提示以及超时后工作任务继续运行。

0.3.0 引用功能尚未完成真实微信端到端实测；上表中的旧版现场验证不代表引用场景已实测。仅安装基础依赖的 CI 会跳过 8 项需要 AstrBot 的事件集成测试。

[Native HTTP API](https://thisnick.github.io/agent-wechat/use/api/) · [Native 消息类型](https://thisnick.github.io/agent-wechat/how-it-works/message-types/) · [AstrBot 事件参考](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)
