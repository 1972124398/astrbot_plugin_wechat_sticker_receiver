# 常见问题

[返回首页](../README.md) · [工作方式与开发验证](DEVELOPMENT.md) · [更新记录](../CHANGELOG.md)

## 安装后没有处理表情

先确认同一私聊里的普通文字能够进入 AstrBot，再检查以下项目。

1. Native 已登录，账号在线，配置的账号 ID 对应该登录账号。
2. `platform_id` 对应 AstrBot 的 WeChat Native 平台实例。
3. 对方微信 ID 已加入 `private_peers`。允许名单默认为空。
4. `token_file` 为 AstrBot 进程能够读取的绝对文件路径，令牌具有该账号的 `read` 与 `media` 权限。
5. 配置已保存并重载，日志出现 `listening on its own Native event stream`。

## 日志怎么看

| 日志片段 | 含义或处理方式 |
| --- | --- |
| `waiting for an account and private conversation allowlist` | 账号、平台或私聊名单尚未填齐 |
| `configuration rejected` | 检查 Native 地址、令牌文件路径和文件内容 |
| `got an inbound sticker` | 已匹配到本插件范围内的表情事件 |
| `delivered a sticker image with context` | 图片已交给 AstrBot，接着由模型与消息流程处理 |
| `skipped media` | 媒体尚不可用、格式不受支持，或超出转换预算 |
| `disconnected` | 检查 Native 服务、HTTP 状态、令牌和网络，插件会尝试重连 |

## 识别后没有回复

检查 AstrBot 的唤醒规则、插件启用范围、模型图片能力和现有防抖插件。转换完成后，本插件交给原消息流程处理，回复时机由该流程决定。

动态表情使用代表帧拼图，模型对动作与语气的理解会受到取样结果影响。可用一张常见静态表情先测试基本链路。

## Windows Native 返回 HTTP 500

如果 Native 报出 `database family must be private and stable`，检查服务数据库及其 `-wal`、`-shm` 文件是否属于运行 Native 的账户。某些 Windows 启动令牌会使新建临时文件属于 Administrators，触发 Native 自身的文件归属检查。

停止 Native 后按其运行账户恢复相关文件归属，并检查服务启动器的默认文件所有者。该问题需要在 Native 运行环境中处理。本插件通过 Native HTTP API 读取表情媒体。

## 更新、停用和卸载

从 AstrBot 插件卡片单独更新、启停或重载插件。停用后会释放本插件的事件流、HTTP 客户端和转换线程。卸载后，可按 Native 文档撤销专用令牌并自行清理令牌文件。

[返回使用说明](../README.md) · [验证范围](../VERIFICATION.md)
