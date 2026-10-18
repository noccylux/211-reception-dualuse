[English](README.md) · 中文

# 211 接待与排队等候助手

一个面向社区与灾害援助热线的本地文字演示。来电者进入一条真实的申请队列，
在等待期间用自己的语言与自动接待助手交谈；随后接线员收到对话、证据和摘要。
Claude 依据可编辑的话术手册（playbook）撰写回复并提取字段；分级、队列顺序、
紧急转介和交接由代码掌控。线路配置覆盖洛杉矶 211 和中国的 12345 热线。
英语电话可以通过独立的 Retell 语音桥接（[docs/voice.md](docs/voice.md)）
接入接线台；语音转接到真人尚未接通。

## 运行

要求：Python 3.14 和 [uv](https://docs.astral.sh/uv/)。从干净的检出开始，
创建锁定的环境，把 `.env.example` 复制为 `.env` 并填入 `ANTHROPIC_API_KEY`
（其他密钥可选），然后在两个终端中分别启动 API 和 UI：

```bash
uv sync --frozen
uv run uvicorn dualuse.api:app --host 127.0.0.1 --port 8000
uv run streamlit run dualuse/ui.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

打开 <http://localhost:8501>。若要在原有端口旁运行一个隔离的演示，为 API 设置
`DUALUSE_QUEUE_DB`、为 UI 设置 `DUALUSE_API_URL`，例如：

```bash
DUALUSE_QUEUE_DB=.tmp/reception-demo.sqlite3 uv run uvicorn dualuse.api:app --host 127.0.0.1 --port 8020
DUALUSE_API_URL=http://127.0.0.1:8020 uv run streamlit run dualuse/ui.py --server.address 127.0.0.1 --server.port 8521 --server.headless true
```

在 PowerShell 中，先设置变量，例如 `$env:DUALUSE_QUEUE_DB = ".tmp/reception-demo.sqlite3"`。
变更记录中提到的 `scripts/uv-run.sh` 和 `scripts/uv-run.ps1` 启动器是作者在
Windows + WSL 上与 `uv run` 等价的工具；它需要 `.env` 中的 `DUALUSE_WSL_DISTRO`，
在其他环境中不需要。

要通过隧道向访客展示事件地图，将公共主机名的 `/plugins/map/` 路径路由到 API，
并在启动 API 和 UI 时都把 `DUALUSE_MAP_URL` 设为该公共 URL，例如
`DUALUSE_MAP_URL=https://demo.211deskdemo.site uv run uvicorn ...`
（[架构](docs/architecture.md#failure-behavior-and-limits)）。

每个数据库只保留一个 API 进程：不要使用多个 worker。`ANTHROPIC_API_KEY`
选择 Claude 访谈模式；侧边栏还提供明确标注的英文关键词模式和不做访谈的 FIFO
模式。模型故障会保持可见，并保留来电者的消息供人工审阅。它们不会悄悄切换模型。

## 演示

使用两个浏览器标签页，一个打开 **Caller conversation**（来电者对话），一个打开
**Operator desk**（接线台）。来电者页面是一条静默文字线路，供无法安全说话的
来电者使用。以下是团队编写的情景，不是真实来电：

1. 以常规来电者身份加入并询问 FEMA 援助。再加入一位来电者并说
   "I see smoke coming from a building."
2. 用 "It is at 12 Oak Street. I am outside." 回答助手的提问。然后透露
   "Someone on the second floor is shouting for help and cannot get out."
   在接线台中，于 **Caller details**（来电者详情）选中该来电，查看风险证据、
   分级变化和报告。在 **Call records**（来电记录；用第三个标签页打开效果很好）
   中，接听清单随来电者的回答逐步填写，最新消息改动过的答案带有橙色标记。
3. 第三位来电者可以报告同一地址的烟雾。**Incident reports**（事件报告）会把
   种类和位置相符的来电关联起来，而不降低任何人的风险等级。
4. 以 `operator-1` 预留下一位来电者。**Confirm human takeover**（确认人工接管），
   或将转接标记为失败，让该来电按原到达时间回到队列。预留在模型请求进行中
   也有效；迟到的回复无法改变已转接的来电。
5. 在 **Reply to the caller**（回复来电者）中输入 "This is the 211 operator. Is everyone out
   of the building?" 在来电者标签页中展示该回复，并在 **Type a
   message to the operator**（给接线员发消息）中作答。然后选择
   **Operator finished this call**（接线员已结束此来电）以释放座席。
   **Call records** 保留已结束来电的清单和完整对话。重启 API 以验证持久化。
6. 在 **Demo call events**（演示来电事件）下，发送两次无应答事件，或断开一个
   来电。在接线台查看由此产生的关注标记或回拨任务。这些按钮模拟连接事件；
   不存在静音检测器或拨号器。
7. 语言：加入并写 "Mi mamá necesita oxígeno y se fue la luz hace dos
   horas." 助手用西班牙语回答；接线员卡片显示 `es`。
8. 转折 2：在侧边栏把 **Line profile**（线路配置）切换到 12345 热线，加入，
   并写 "我家楼下被水淹了，我奶奶腿脚不方便，出不去，水还在涨"。欢迎语、
   紧急电话（110、119、120）和回复都是普通话；队列规则不变。之后切回洛杉矶。
9. 激增：在接线台打开 **Demo surge**（演示激增），保持 20 位来电者、混合内容
   和 Austin 到达分布，然后注入。团队编写的脚本（模拟）和 Munro 灾害消息
   （录制，逐个来电标注）填满队列，而生命威胁移到顶部。该激增大约发出 30 次
   模型调用。
10. 情景模拟器：实测比率表显示离线规则和 Claude 在录制的 2010 年海地与
    巴基斯坦短信以及飓风桑迪帖子上的结果（代理标签，仅首条消息，并非 211
    来电）。运行回放，在同一模拟激增上比较假定错误率与那里实测的分级。

SQLite 默认将来电、对话、事件和审阅任务保存到 `.tmp/211-queue.sqlite3`
（`DUALUSE_QUEUE_DB` 可覆盖）。Reset（重置）会明确清空此接线台。没有身份验证：
只使用本地演示数据。

## 验证与解读

```bash
uv run python -m pytest tests -q
```

测试使用隔离的数据库，不发出付费模型调用；`tests/test_ui.py` 用 `AppTest`
驱动 Streamlit 应用，对接进程内的 API。情景模拟器使用带有假定错误率的合成
来电，以及在评估运行后、在带代理标签的录制灾害消息上实测的分级占比
（[评估](docs/evaluation.md)）。两者都不是 211 的准确率，也不是真实的排队
等待时间。重新运行评估会免费回放缓存的 Claude 响应：

```bash
env -u ANTHROPIC_API_KEY uv run python scripts/evaluate_messages.py
```

详情：[架构](docs/architecture.md)、变更记录
[008](docs/changes/2026-10-17-008-reception-agent.md) 和
[009](docs/changes/2026-10-17-009-reception-agent-design.md)、
[活动](docs/hackathon.md)、[提交材料](docs/submission.md)。
