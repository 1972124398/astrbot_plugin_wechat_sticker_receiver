# AstrBot 微信原生表情转图片

收到微信原生表情时，插件把静图转成 PNG，把动图转成按时序排列的 PNG 代表帧拼图。它保留原消息的会话、发送者、消息 ID 和时间，向 AstrBot 交接一个普通图片组件。现有消息防抖插件负责处理连续消息，AstrBot 按原有规则决定是否调用模型及回复。

## 安装和配置

1. 在 AstrBot 的插件管理上传本项目的安装 ZIP。也可把仓库目录放进 `data/plugins`。运行环境需要 `requirements.txt` 中的依赖。
2. 填写本机 Native 地址、Native 账号 ID 和 AstrBot 的 WeChat Native 平台实例 ID。
3. 通过 Native 的 `wx tokens create` 为该账号签发 `read` 和 `media` 权限的令牌，在插件配置填写令牌文件的绝对路径。
4. 填入允许转换的私聊微信 ID，保存并重载。允许名单默认空白。

兼容验证环境为 AstrBot 4.29.4、WeChat Native 0.3.21 和 agent-wechat 2.7.1。当前适配器把直发普通图片限定在私聊，表情转换沿用该范围。

## 实现

插件使用独立 Native SSE 连接监听新消息，以原消息 ID 读取 `type=47` 或 `type=49 / appMessageType=8` 的媒体。媒体仅从 Native 的受认证接口获取。插件使用已安装适配器的 `create_event` 和 AstrBot 的 `commit_event` 提供图片输入，每张表情的转换都有字节、时间和解码预算。

单发表情即可进入转换步骤。插件随图片提供模型可见的说明，标明这是表达语气和情绪的表情包，用于自然接话。预览和动图取样带有对应标记。现有防抖、唤醒、模型和回复规则处理这次图片输入。

## 启停和排错

- 从 AstrBot 插件管理独立启停、重载或卸载 **微信原生表情转图片**。停用后可用私聊文字和普通图片复测。
- 卸载后用 `wx tokens revoke ID` 撤销本插件的专用令牌，再清理令牌文件。
- 日志的 `got an inbound sticker` 表示已经匹配入站事件，`delivered a sticker image with context` 表示已将图片和说明交给 AstrBot。媒体不可用时查看同时间的 `skipped media` 日志。
- 安装、启停、真实微信验收状态见 [验证记录](VERIFICATION.md)。

## 开发验证

```powershell
python -m pip install -r requirements.txt
python -m unittest -v
python probe_native.py --account ACCOUNT --token-file PATH --check
python probe_native.py --account ACCOUNT --token-file PATH --thread THREAD --sender SENDER
```

独立探针只读取已缓存媒体并验证 SHA-256。旧版 Native 可通过 `--after` 指定已知起始游标。探针同时观察表情和文字是为了核对测试会话的身份。

[MIT 许可证](LICENSE)
