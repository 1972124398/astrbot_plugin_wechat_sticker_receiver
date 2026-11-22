# 本机验证

环境为 Windows、AstrBot 4.29.4、WeChat Native 0.3.21、agent-wechat 2.7.1。原有合并插件为思维链式消息防抖 1.5.0。聊天使用 AstrBot 本地 Agent 和现有百炼视觉模型。

## 0.2.0 直接转换版

| 项目 | 证据 |
| --- | --- |
| 双路接收 | AstrBot 面板单独停用旧版并安装、启用 0.2.0。日志显示独立 SSE 已连接，原 Native 客户端与新 SSE 同时保持连接。旧版 Native 游标获取也用现场 2.7.1 验证。 |
| 单发表情 | 14:25:12 真实私聊只收到一条 `type=47` 动图，14:25:13 插件转换为四帧 PNG，并把图片及表情说明交给原 AstrBot 私聊。隔离测试确认会话、身份和消息 ID 保留，重复事件只交接一次。 |
| 视觉输入 | AstrBot 事件日志记录了表情说明与图片组件。现场合并插件 1.5.0 开启思考窗口并结合画面情绪，微信在 14:25:33 和 14:25:36 收到自然接话。 |
| 安装与启停 | 现场 AstrBot 面板上传 ZIP 成功，并单独开启插件。隔离测试确认停用清理 SSE、HTTP 客户端及转换线程。 |
| 范围 | 现场配置只有一个知情测试私聊。群聊直发图片沿用现场适配器的现有处理范围。 |

七项本地测试通过。真实静图、分享表情、多联系人隔离、表情与紧接文字的合并、普通图片现场回归和卸载回归仍待验证。

## 早期真实微信验证

14:02:19 的真实 `type=47` 表情通过 Native 媒体 API 获得 240×240 的 GIF 原图，校验 SHA-256 并转换为 771×771 四帧 PNG。早期 0.1.0 试装版在同一私聊 14:09:20 的「在」所触发的请求中成功附图。原模型返回后，微信实际收到包含画面文字和姿势信息的回复。0.2.0 随图提供语境说明，并将连续消息的处理交给现有合并插件。

## 本机 Native 恢复

验证开始时原 Native 账号和事件 API 返回 HTTP 500。Native 日志表明 SQLite 的 WAL 和 SHM 属主不符合检查。校正属主后，原计划任务运行期间问题再次出现。当前由 Windows 登录会话临时运行同一个 Native 启动脚本，复用了原登录和数据。验证期间原私聊文字收发和账号接口均已恢复。计划任务恢复后的长期运行尚待确认。

接口见 [Native HTTP API](https://thisnick.github.io/agent-wechat/use/api/)、[Native 消息类型](https://thisnick.github.io/agent-wechat/how-it-works/message-types/) 和 [AstrBot 事件参考](https://docs.astrbot.app/dev/star/guides/listen-message-event.html)。
