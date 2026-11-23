# AstrBot 微信原生表情转图片

[![版本](https://img.shields.io/github/v/release/1972124398/astrbot_plugin_wechat_sticker_receiver)](https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/releases/latest)
[![许可证](https://img.shields.io/badge/license-0BSD-blue)](LICENSE)

让 AstrBot 看懂微信私聊里收到的原生表情包，并结合正在聊的话题自然接话。

静态表情转换成 PNG，动态表情转换成按时间顺序排列的代表帧拼图。转换后的图片沿用原会话、发送者和消息 ID，交给 AstrBot 现有的模型与回复流程处理。

[快速开始](#快速开始) · [配置说明](#配置说明) · [常见问题](docs/TROUBLESHOOTING.md) · [验证范围](VERIFICATION.md) · [更新记录](CHANGELOG.md)

## 可以做什么

- 接收微信私聊中的静态表情和动态表情。
- 将表情交给支持图片的模型，理解语气、情绪和上下文。
- 与消息防抖插件配合，将连续的表情、文字放进同一段对话。
- 提供表情语境提示，让模型接话时关注交流的意思。
- 通过私聊允许名单选择需要处理的联系人。

## 安装前准备

| 项目 | 要求或已验证范围 |
| --- | --- |
| AstrBot | `>=4.29.4,<5` |
| Python | 已验证 3.12，使用 AstrBot 运行环境 |
| 微信服务 | 已登录的 agent-wechat Native，已验证 2.7.1 |
| 微信适配器 | 已接入 AstrBot 的 WeChat Native，已验证 0.3.21 |
| 模型 | 支持图片输入 |
| 处理范围 | 允许名单中的微信私聊 |
| Native 地址 | 本机回环地址，例如 `http://127.0.0.1:6174` |

先确认普通微信文字消息能够正常进入 AstrBot，再安装本插件。

[agent-wechat](https://github.com/thisnick/agent-wechat) · [WeChat Native 适配器](https://github.com/neozhu/astrbot-plugin-wechat-native)

## 快速开始

1. 在 AstrBot 插件管理中通过下面的仓库地址安装，或下载发布页的插件 ZIP 后从文件安装。
2. 打开 **插件 → 微信原生表情转图片 → 配置**。
3. 填写本机 Native 地址、Native 账号 ID、AstrBot 平台实例 ID，以及令牌文件路径。
4. 在 `private_peers` 中加入允许处理表情的私聊微信 ID。
5. 保存并单独重载插件，然后在已加入名单的私聊里发送一张表情。

```text
https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver
```

[下载安装包](https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/releases/latest/download/astrbot_plugin_wechat_sticker_receiver.zip)

## 配置说明

| 字段 | 填写内容 | 默认值 |
| --- | --- | --- |
| `native_origin` | Native 服务所在的本机地址 | `http://127.0.0.1:6174` |
| `account_id` | Native 账号 ID，可从 `wx accounts list` 查询 | 空 |
| `platform_id` | AstrBot 中已创建的 WeChat Native 平台实例 ID | 空 |
| `token_file` | 保存专用 Native 令牌的绝对文件路径 | 空 |
| `private_peers` | 允许读取表情的私聊微信 ID 列表 | 空列表 |
| `wait_ms` | 单张表情读取和转换的超时，单位毫秒 | `4500` |

这三个 ID 分别标识 Native 登录账号、AstrBot 平台实例和聊天联系人，填写时对应各自的位置。允许名单为空时，插件等待配置完成。

例如下面的配置结构，示例 ID 与路径需要替换为实际值。

```json
{
  "native_origin": "http://127.0.0.1:6174",
  "account_id": "account-example",
  "platform_id": "wechat-platform-example",
  "token_file": "C:/path/to/sticker-reader.token",
  "private_peers": ["wxid_example"],
  "wait_ms": 4500
}
```

### 准备专用令牌

令牌需要对指定账号具有 `read` 和 `media` 权限。已配置 Native 管理访问的情况下，可按下面的命令结构创建。

```shell
wx tokens create sticker-reader --accounts ACCOUNT_ID --scopes read --scopes media
```

将返回的令牌保存到一个文件，再把该文件的绝对路径填入 `token_file`。管理令牌文件和服务地址的参数，以 Native 的部署配置为准。

[Native 令牌说明](https://thisnick.github.io/agent-wechat/reference/tokens/)

## 怎么确认生效

在允许名单中的私聊发送一张表情，再发送一句接续话题的文字。模型应收到转换后的图片，并根据现有的唤醒、防抖和回复规则接话。

日志中的 `got an inbound sticker` 表示已经匹配到表情，`delivered a sticker image with context` 表示已交给 AstrBot。模型输出仍取决于图片能力、人设和其他提示词。

[排错方法](docs/TROUBLESHOOTING.md) · [真实微信验证记录](VERIFICATION.md) · [开发与探针](docs/DEVELOPMENT.md)

## 问题反馈与相关插件

反馈时请提供 AstrBot、Native、微信适配器和本插件版本，以及表情类型、配置字段说明和相关日志。令牌文件的内容请保持私密。

[提交问题](https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/issues/new/choose) · [更新记录](CHANGELOG.md)

可以配合 [短期共享情绪](https://github.com/1972124398/astrbot_plugin_short_term_mood) 使用。同一作者还维护 [Codex 任务桥接](https://github.com/1972124398/astrbot_plugin_codex_bridge)。

## 许可证

采用 [0BSD](LICENSE)，允许使用、修改、分发和商用，无需保留署名。
