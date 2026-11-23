<div align="center">

<h1>AstrBot 微信原生表情转图片</h1>
<p>让 AI 看懂微信表情，接住聊天里的语气与情绪。</p>

<p>
  <a href="https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/releases/latest"><img src="https://img.shields.io/github/v/release/1972124398/astrbot_plugin_wechat_sticker_receiver?style=flat-square&color=2563eb" alt="最新版本"></a>
  <a href="https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/actions/workflows/test.yml"><img src="https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/actions/workflows/test.yml/badge.svg?branch=main" alt="测试状态"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-0BSD-64748b?style=flat-square" alt="0BSD 许可证"></a>
</p>

<p>
  <a href="https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/releases/latest/download/astrbot_plugin_wechat_sticker_receiver.zip"><strong>下载 ZIP</strong></a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#配置说明">配置说明</a> ·
  <a href="https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/issues/new/choose">问题反馈</a>
</p>

</div>

## 功能

| 输入 | 处理方式 |
| --- | --- |
| 静态原生表情 | 转换为 PNG 图片 |
| 动态原生表情 | 转换为按时间顺序排列的代表帧拼图 |
| 引用表情并发送文字 | 将被引用表情的图片加入本条消息，保留文字和引用关系 |
| 表情与连续文字 | 交给原会话流程，可配合消息防抖插件处理 |
| 表情语境 | 提醒模型体会语气与情绪，自然接话 |

转换后的图片沿用原会话、发送者和消息 ID。处理范围为允许名单中的微信私聊。

引用支持普通原生表情和分享表情（`type=47`、`type=49 / appMessageType=8`），包括引用自己发送过的表情。优先读取引用中内嵌的媒体；缺少内嵌媒体时，在适配器记录或同一私聊最近 50 条消息中寻找并校验原表情。找不到、已撤回或读取超时时，继续处理本条文字。

例如，长按一张表情选择“引用”，再发送“这个表情是什么意思？”，模型会同时收到文字和表情图。单发表情保持语气提示；明确询问被引用表情时，模型可以结合图片解释。适配器已提供图片时，本插件跳过重复转换。

## 快速开始

先确认微信普通文字能够正常进入 AstrBot，并准备支持图片输入的模型。

| 项目 | 要求或已验证范围 |
| --- | --- |
| AstrBot | `>=4.29.4,<5`，已验证 Python 3.12 |
| 微信接入 | 已登录的 agent-wechat Native 与 WeChat Native 适配器 |
| 已验证版本 | Native 2.7.1、微信适配器 0.3.21 |
| 服务地址 | 本机回环地址，例如 `http://127.0.0.1:6174` |

1. 在 AstrBot 插件管理中使用下方仓库地址安装，或下载 ZIP 后从文件安装。
2. 打开 **插件 → 微信原生表情转图片 → 配置**。
3. 填写账号、平台实例、令牌文件和私聊允许名单。
4. 保存并单独重载插件，在允许的私聊中发送一张表情。

```text
https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver
```

[agent-wechat](https://github.com/thisnick/agent-wechat) · [WeChat Native 适配器](https://github.com/neozhu/astrbot-plugin-wechat-native)

## 配置说明

| 字段 | 填写内容 |
| --- | --- |
| `native_origin` | 本机 Native 地址，默认 `http://127.0.0.1:6174` |
| `account_id` | Native 登录账号 ID，可通过 `wx accounts list` 查询 |
| `platform_id` | AstrBot 中的 WeChat Native 平台实例 ID |
| `token_file` | 专用 Native 令牌文件的绝对路径 |
| `private_peers` | 允许处理表情的私聊联系人微信 ID 列表 |
| `wait_ms` | 读取和转换超时，默认 `4500` 毫秒 |

账号 ID、平台实例 ID 和联系人微信 ID 分别对应三个配置位置。允许名单默认为空，填齐配置后才会处理表情。

<details>
<summary><strong>查看配置示例</strong></summary>

示例中的 ID 和路径需要替换为自己的实际值。

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

</details>

<details>
<summary><strong>如何准备专用令牌？</strong></summary>

令牌需要对指定账号具有 `read` 和 `media` 权限。配置好 Native 管理访问后，可以按下面的命令结构创建。

```shell
wx tokens create sticker-reader --accounts ACCOUNT_ID --scopes read --scopes media
```

将返回的令牌保存到文件，再把绝对路径填入 `token_file`。管理令牌文件和服务地址参数，以自己的 Native 部署配置为准。

[Native 令牌说明](https://thisnick.github.io/agent-wechat/reference/tokens/)

</details>

## 常见问题

<details>
<summary>怎样确认插件已生效？</summary>

在允许名单中的私聊发送表情，再发送一句接续话题的文字。日志出现 `got an inbound sticker` 表示已匹配表情，出现 `delivered a sticker image with context` 表示已交给 AstrBot。

后续由现有唤醒、防抖、模型与回复规则处理。模型输出取决于图片能力、人设和其他提示词。

</details>

<details>
<summary>安装后没有处理表情，或识别后没有回复</summary>

检查普通文字链路、三个 ID、私聊名单、令牌权限及模型图片能力。完整日志含义和排错步骤见 [排错说明](docs/TROUBLESHOOTING.md)。

</details>

<details>
<summary>Native 断连或返回 HTTP 500</summary>

检查微信服务与账号状态。Windows 的文件归属问题及对应症状见 [运行环境排错](docs/TROUBLESHOOTING.md#windows-native-返回-http-500)。

</details>

## 文档与反馈

| 文档 | 内容 |
| --- | --- |
| [排错说明](docs/TROUBLESHOOTING.md) | 配置检查、日志含义、启停与卸载 |
| [验证记录](VERIFICATION.md) | 已完成的真实微信验证与范围 |
| [开发与探针](docs/DEVELOPMENT.md) | 转换流程、本地测试和独立探针 |
| [更新记录](CHANGELOG.md) | 版本变化与发布内容 |

反馈时请提供 AstrBot、Native、微信适配器及插件版本，附上表情类型和相关日志，并隐藏令牌及个人信息。

[提交问题](https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/issues/new/choose) · [查看发布版本](https://github.com/1972124398/astrbot_plugin_wechat_sticker_receiver/releases)

## 相关插件

| 插件 | 用途 |
| --- | --- |
| [短期共享情绪](https://github.com/1972124398/astrbot_plugin_short_term_mood) | 让表情语气参与持续的短期心境 |
| [Codex 任务桥接](https://github.com/1972124398/astrbot_plugin_codex_bridge) | 从私聊提交本机 Codex 后台任务 |

采用 [0BSD 许可证](LICENSE)，允许使用、修改、分发和商用，无需保留署名。
