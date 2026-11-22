# 本机可行性验证

环境为 Windows、AstrBot 4.29.4、WeChat Native 0.3.21、agent-wechat 2.7.1。当前运行器为 AstrBot 本地 Agent，聊天模型为百炼 deepseek-v4.1-flash，经 Anthropic 兼容接口发送图片。

| 门槛 | 当前证据 |
| --- | --- |
| 双路接收 | 原适配器恢复微信私聊收发后，独立 SSE 使用自有连接重放到同一私聊的真实 `type=47` 表情和文字。正式插件采用按需读取的线程消息 API，停用时没有事件订阅或消费进度需要释放。 |
| 媒体可用 | 真实私聊 14:02:19 收到一条 `type=47`。使用插件专用令牌取到 240×240 GIF 原图，校验字节长度和 SHA-256，用插件转换代码得到 771×771 的四帧 PNG。单发表情期间未出现回微信的 AI 消息。分享表情和异常媒体待测。 |
| 会话准确 | 测试私聊的 Native 账号、会话、发送者和入站方向已核对。用已安装适配器的会话函数验证了群聊共享和 `unique_session` 两种编码。真实群聊隔离待测。 |
| 真实视觉注入 | 试装插件在现场 AstrBot 4.29.4 正常加载。隔离集成测试从 Native 媒体到同版 Anthropic 序列化器得到一个图像内容块，验证了原提示词和 PNG 像素、临时标记、重复调用及插件停止。仍待正式插件启用后的真实私聊自然消息触发该钩子，并获得对应微信回复。 |

初次启动验证时，原 Native 账号和事件 API 返回 HTTP 500，原适配器也停止接收。Native 重启日志提示 `database family must be private and stable`。检查发现 SQLite 的 WAL 和 SHM 属主为 Administrators，Native 要求属主与运行用户一致。校正属主后原计划任务启动时短暂恢复，随后故障复现。改用当前 Windows 登录会话临时运行同一启动脚本后，原登录显示在线，原私聊文字收发恢复。现行排查沿用现有二进制、账号、数据和模型。

试装范围为一个知情测试私聊，群聊清单为空。默认关联时间是 120 秒，现场为这次测试临时延长到 600 秒。真实静图、分享表情、多联系人与群聊、普通图片回归和现场面板停用/卸载验证待完成。关联、静图、动图、格式异常和会话隔离的七项本地测试通过，安装包通过当前 AstrBot 的 ZIP 校验和解包。

验证使用 [Native HTTP API](https://thisnick.github.io/agent-wechat/use/api/)、[Native 消息类型](https://thisnick.github.io/agent-wechat/how-it-works/message-types/) 和 [AstrBot 事件钩子](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)。仓库测试使用合成样本。
