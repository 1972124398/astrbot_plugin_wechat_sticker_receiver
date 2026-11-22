# AstrBot 微信表情上下文

面向 AstrBot 和 WeChat Native 的独立插件项目。微信原生表情作为紧接着的同一会话的视觉上下文，供现有聊天模型理解当前语气、情绪和意图。用户照常聊天，表情单独到达时保持安静。

## 安装和配置

在 AstrBot 4.29.4 的插件管理里上传本项目的安装 ZIP。也可把仓库目录放进 AstrBot 的 `data/plugins`，目录名保持 `astrbot_plugin_wechat_sticker_receiver`。运行环境需要 `requirements.txt` 中的依赖。

1. 填写 Native 地址、Native 账号 ID 和 AstrBot 的 WeChat Native 平台实例 ID。服务地址仅支持本机回环。
2. 通过 Native 的 `wx tokens create` 为该账号创建 `read`、`media` 令牌，保存到 AstrBot 进程可读的私有文件，在插件配置中填写绝对路径。
3. 把允许使用的微信联系人 ID 或群 ID 填入对应清单。清单默认空白，群 ID 形如 `…@chatroom`。原适配器与 AstrBot 按现有规则决定一条消息是否进入模型流程。
4. 重载插件以应用设置。直接发送表情，然后正常聊天即可。表情和后续文字的默认关联窗口为 120 秒。

## 处理方式

插件在 AstrBot 的 `on_llm_request` 中读取 Native 会话的短段历史。以触发当前模型请求的真实 Native 消息 ID 为锚点，找到同一账号、会话、发送者最近的一条入站消息。它是有效的原生表情时，通过 Native 媒体 API 读取原图或可用预览。一连串表情取最后一张。群聊无论共用会话还是按成员分会话，媒体都按真实发送者匹配。

静图转为 PNG，动图转为按时间排列的代表帧拼图，兼容现有单图输入。取样数量和预览状态记在本地日志。插件仅向当前请求追加临时图像内容块。无匹配、请求已经带图或语音、媒体超时或格式异常时，聊天继续走 AstrBot 的正常流程。

## 启停、卸载和排错

- 在 AstrBot 插件管理中单独启用、重载、停用或卸载 **微信原生表情上下文**。停用后用原微信私聊复测文字和普通图片。
- 卸载后用 `wx tokens revoke ID` 撤销为本插件签发的令牌，再清理该令牌的专用文件。
- 日志中的 `matched a recent message` 表示会话匹配，`attached image` 表示仅附加了图像内容块。媒体失败时检查 Native 账号在线状态、令牌权限和媒体资产状态。
- 升级 Native 或 AstrBot 后用已允许的测试会话复测。实测版本和待测项目见 [验证记录](VERIFICATION.md)。

## 开发验证

## 运行探针

在 Native 所在本机运行 Python 3.11 或更新版本。为一个 Native 账号准备权限限定为 `read` 和 `media` 的令牌文件，放在仓库外。

```powershell
python -m pip install -r requirements.txt
python probe_native.py --account ACCOUNT --token-file PATH --check
python probe_native.py --account ACCOUNT --token-file PATH --thread THREAD --sender SENDER
python -m unittest -v
```

由测试者从所选会话发送原生表情并继续聊天。探针输出匹配结果、原生类型、资产状态、可解码格式和尺寸。旧版 Native 需要用 `--after` 指定一个有效的起始游标，例如从该账号的 `GET /events` 响应获得的 `nextCursor`。探针使用自己的 SSE 连接，游标仅在进程中使用。

探针只读取 Native 已缓存的媒体，并检查下载字节数与 SHA-256。动态图转换代码在解码预算内取按时序排列的代表帧。运行过程中保持取样输出和聊天数据在本机。

## 许可证

[MIT](LICENSE)
