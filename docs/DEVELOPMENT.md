# 工作方式与开发验证

[返回首页](../README.md) · [常见问题](TROUBLESHOOTING.md) · [更新记录](../CHANGELOG.md)

插件使用独立的 Native SSE 连接监听新消息，以原消息 ID 读取 `type=47` 或 `type=49 / appMessageType=8` 的媒体，再转换为图片。

媒体从 Native 的认证接口获取。插件使用已安装适配器的 `create_event` 和 AstrBot 的 `commit_event` 提交图片输入，每张表情的转换都有字节、时间和解码预算。

单发表情即可进入转换。图片附带表情语境说明，预览和动图取样带有对应标记。本轮包含表情时，插件提醒模型体会语气和情绪，直接接话。现有唤醒、防抖、模型与回复流程处理后续输出。

引用表情通过优先级为 100 的消息事件处理器，在防抖收集和模型图片提取之前补充图片，不再提交第二个事件。处理 `type=49 / appMessageType=57`，引用对象必须是受支持的表情。`state=embedded / embeddedSticker=true` 使用当前引用回复的消息 ID 读取 `source=quote` 媒体；`state=missing` 使用适配器保存的原消息 ID，或查询同一私聊最近 50 条消息，再校验账号、会话、发送者、serverId 和表情类型后读取原消息媒体。

下载和转换后再次校验引用消息与原消息的身份及撤回状态。超时、撤回、找不到原表情等情况保留原文字输入。引用提示单独标记，消息合并后仍能应用“优先回应当前文字”的指导。Native 引用字段与父消息媒体规则见 [消息类型说明](https://thisnick.github.io/agent-wechat/how-it-works/message-types/#quotes)。

## 本地测试

在仓库根目录、使用安装了依赖的 Python 运行。

```shell
python -m pip install -r requirements.txt
python -m unittest -v
```

仅安装 `requirements.txt` 时运行媒体与引用来源测试；安装 AstrBot 的环境还会运行 `test_event_integration.py` 中的事件补图、去重、提示和超时恢复测试，未安装时明确标记为跳过。事件测试将 AstrBot 导入时产生的运行文件隔离到临时目录。

## 独立探针

检查账号接口是否可访问。

```shell
python probe_native.py --account ACCOUNT --token-file PATH --check
```

观察指定测试私聊的文字和表情，验证会话身份及媒体转换。

```shell
python probe_native.py --account ACCOUNT --token-file PATH --thread THREAD --sender SENDER
```

Native 使用非默认地址时可增加 `--origin`。旧版 Native 可通过 `--after` 指定已知起始游标。探针读取已缓存媒体并校验 SHA-256，结果会报告匹配的文字、表情与成功解码数量。

真实微信测试范围见验证记录，仍待实测的场景也在其中列出。

[验证记录](../VERIFICATION.md) · [返回使用说明](../README.md)
