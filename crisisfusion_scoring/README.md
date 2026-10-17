# 独立通话打分器 · crisisfusion-scoring 1.0.0

这是可装入其他 Python / Web 主体的独立插件。包含确定性文字提取、每通话 0–100 人工关注指数、未解决需求、修订历史、去重、队列与人工操作审计；自带一个可通过 iframe 嵌入的轻量界面。**不依赖原 CrisisFusion 项目、地图插件、语音插件或 API Key。**

## 安装与独立运行

需要 Python 3.11+。建议在宿主的虚拟环境中安装，选择以下一种：

```powershell
# 安装打包的 wheel（把路径换成实际解压路径）
python -m pip install .\wheels\crisisfusion_scoring-1.0.0-py3-none-any.whl

# 或在本目录从源码安装
python -m pip install .

python -m crisisfusion_scoring --host 127.0.0.1 --port 8811 --db work/scoring.sqlite3
```

打开 <http://127.0.0.1:8811/>。停止进程可按 Ctrl+C。`--db` 是本插件自己的数据库路径，目录会按需创建；`:memory:` 适合临时测试。源码目录和数据库可以放在不同位置。请勿将原系统或其他插件正在使用的数据库传给本插件。

运行依赖为 FastAPI 和 Uvicorn；wheel 本身不包含这些第三方依赖，首次 pip 安装需要它们已在环境中或可由包源下载。所有评分运算在本地进行。

## 方式一：Python 直接调用

```python
from crisisfusion_scoring import ScoringPlugin, extract_call, get_policy

with ScoringPlugin("work/scoring.sqlite3") as scorer:
    result = scorer.ingest({
        "call_id": "call-001",
        "revision": 1,
        "text": "I am trapped in a fire.",
        "language": "en",
        "location": {"label": "123 Main St, Los Angeles, CA"},
    })
    print(result["call"]["priority_assessment"])
    print(scorer.snapshot()["queue_calls"])

print(extract_call("Library hours please.", language="en"))
print(get_policy())
```

公开入口：`ScoringPlugin`、兼容的 `Engine`、`extract_call`、`assess_call`、`get_policy`、`create_app`。推荐用 `ScoringPlugin` 管理完整生命周期；`Engine` 与原成熟生命周期实现等价。底层纯函数 `assess_call(call, needs, *, as_of, wait_by_need, overdue_after_seconds=120)` 面向已存在的证据和需求结构，不接受任意模型分数来替代规则。导入包、导入 CLI 均不会创建数据库或启动服务；实例化插件 / 调用 `create_app` 才创建状态。

同一 `call_id` 每次更新使用更高的正整数 `revision`；`text` 传来电者**累计转写**。同一版本不同内容会被拒绝；相同事件重复投递不会重复创建需求。`event_id` 可由宿主提供；同一事件 ID 不可代表不同内容。更正或无害的新句子不会自动解决旧危险需求，需要明确人工操作。

## 方式二：挂载到现有 FastAPI 主体

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from crisisfusion_scoring import create_app

scoring = create_app("work/scoring.sqlite3")

@asynccontextmanager
async def lifespan(app):
    yield
    scoring.state.plugin.close()

app = FastAPI(lifespan=lifespan)
app.mount("/plugins/scoring", scoring)
```

宿主页面嵌入：

```html
<iframe src="/plugins/scoring/" title="通话打分器"
        style="width:100%;height:900px;border:0"></iframe>
```

UI 的脚本、样式与 API 均采用相对 URL，支持任意挂载前缀；入口保留末尾 `/`。挂载子应用不会自动运行子应用生命周期，宿主应在自己关闭时调用 `scoring.state.plugin.close()`。不要多次关闭同一实例。界面不依赖宿主的导航或 DOM；宿主写入数据后点击“刷新”即可查看最新队列。

默认仅接受 `127.0.0.1`、`localhost` 和 `::1` 的 Host。生产宿主可以传 `allowed_hosts=["your-host.example"]`，这只是 Host 白名单，**不提供账号、角色、TLS 或用户隔离**。将插件放在宿主既有认证与授权之后；不要把此演示实例直接公开到互联网。需要多租户时由宿主隔离实例和数据库。

## 方式三：其他语言主体通过 HTTP 接入

Node、Java、.NET 等主体可以启动本地子服务，或通过同源反向代理挂载它。浏览器端不能直接跨域写入；建议宿主后端调用或同源代理。即使由后端调用，写请求也必须携带 token。

1. GET `/api/scoring/status`，读取 `csrf_token`、`csrf_header` 与 `store_id`。
2. POST 请求设置 `Content-Type: application/json` 和 `X-CrisisFusion-Scoring: <token>`。
3. 浏览器的 `Origin` 必须匹配实际请求的 scheme、hostname、port；挂载路径不属于 Origin。普通后端请求可以没有 Origin。重启后 token 会更换，重新读取即可。

`store_id` 是保存在本插件数据库内的 UUID（Python 对应 `plugin.store_id`），同一个数据库重启后不变；创建新数据库或调用 `ScoringPlugin.reset()` 后会改变。可靠中继应把自己的消费游标同时绑定到源事件流、目标 URL 和这个消费者身份。身份变化时停止并由宿主决定从哪个事件重新导入，不能沿用旧游标跳过历史。普通文件备份会保留原身份；回滚同一身份的旧备份仍需要宿主同步回滚或重建游标。

示例：

```python
import httpx

with httpx.Client(base_url="http://127.0.0.1:8811") as client:
    status = client.get("/api/scoring/status").json()
    headers = {status["csrf_header"]: status["csrf_token"]}
    response = client.post("/api/scoring/calls", headers=headers, json={
        "call_id": "call-001", "revision": 1,
        "text": "I am trapped in a fire.", "language": "en",
        "event_id": "caller-final-001", "input_mode": "text"
    })
    response.raise_for_status()
    result = response.json()
    print(result["call"]["priority_assessment"]["score"])  # 初始 80
```

| 方法与相对路径 | 输入 / 返回 |
|---|---|
| GET `/health` | 插件、API、提取规则、评分规则版本 |
| GET `/api/scoring/status` | CSRF token、header 名、持久化 `store_id`、是否需要 Key |
| GET `/api/scoring/policy` | 实际运行的分数区间、参数、约束 |
| POST `/api/scoring/calls` | 通话 JSON；返回 `call`、`incident`、`needs`、`alerts`、`duplicate` |
| GET `/api/scoring/state` | `calls`、`needs`、`queue_calls`、`audit`、规则与指标 |
| GET `/api/scoring/calls/{call_id}/priority` | `assessment`、`revisions`、该通话全部 `needs` |
| POST `/api/scoring/needs/{need_id}/actions` | 显式人工操作，带操作者、理由、可选事件 ID |
| POST `/api/scoring/settings` | 已知配置字段，例如 `{"available_agents": 2}` |
| POST `/api/scoring/recompute` | `{}` 或 `{"call_id":"call-001"}`，重算已存证据 |
| GET `/api/scoring/metrics` | 本地可观察指标；真实话务成功率仍为 null |

接收通话字段：`call_id`、`text`（最多 20000 字符）、`language`（`en/es/mixed/unknown`）、`location`（可含 `label/lat/lon/source`）、`timestamp`（可选 ISO 时间）、`revision`、`event_id`、`input_mode`（`text/replay/simulated_voice/browser_voice`）、`speaker`。其他推理或“标准答案”字段会被拒绝。中文应设 `unknown`，需要人工核查。传入真实语音时只应发送来电者最终转写，宿主不要将 Agent 自己说的话作为来电证据。

典型评分输出节选：

```json
{
  "call_id": "call-001",
  "score": 80,
  "category": "IMMEDIATE_HUMAN",
  "band": {"min": 80, "max": 100},
  "policy_version": "human-attention-2026-10-17-v1",
  "safety_floor_applied": false
}
```

完整 `priority_assessment` 同时含 `components`、原句证据、规则 ID、修订号、时间、不确定性、未解决需求 ID、队列资格、等待时间、逾时和人工排序记录。已全部解决时 `assessment` 为 `null`，历史不丢失。

人工解决某一需求：

```json
{"action":"resolve","actor":"operator-17","note":"已与来电者核实此项需求已经解决","event_id":"review-001"}
```

人工升级：

```json
{"action":"escalate","actor":"operator-17","note":"核实到当前受困风险","target_category":"IMMEDIATE_HUMAN"}
```

同类别人工顺序：`{"action":"override","actor":"operator-17","note":"人工排序依据","manual_order":-1}`。`manual_order` 仅在当前类别生效，不能把低优先级放到高优先级之前。

保留的模拟话务动作包括 `request_transfer` → `simulate_dial` → `simulate_bridge`，以及 `simulate_no_answer`、`simulate_failure`、`interrupted`、`request_callback`、`callback_no_answer`、`callback_connected` 和 `confirm_incident`。它们用于验证未解决需求与队列生命周期，**不会拨号、转接或派遣人员**；语音插件与电话运营商应由宿主另行对接。

## 评分与限制

| 类别 | 分数段 | 含义 |
|---|---|---|
| IMMEDIATE_HUMAN | 80–100 | 当前明确危险 / 受困等规则触发，立即人工关注 |
| HUMAN_VERIFY | 50–79 | 危险线索、矛盾、未知语义等需要人工核查 |
| ROUTINE_HUMAN | 20–49 | 常规人工请求 |
| AUTOMATION_ELIGIBLE | 0–19 | 全文符合允许的服务意图，未出现未解释内容 |

分数先受硬类别约束，再按每等待一分钟 +1（最多 +15）及跟进项 +5 计算，并封顶于本类别。队列仍按类别、显式同类别人工顺序、最长累计等待、稳定 ID 排列，不把一个浮点“风险概率”当作唯一排序依据。缺地址、语言身份、人员短缺、重复报告不会用于扣减危险优先级。

此版本迁移了 v0.5 的评分、提取和生命周期代码，规则版本保持 `prototype-2026-10-17-v4.1` / `human-attention-2026-10-17-v1`。它是有限英语/西班牙语规则原型，不是经过临床或调度标准认证的系统。单元测试证明已覆盖情形的行为，不代表真实来电识别准确率；不输出虚构的准确率或死亡风险。

SQLite 保存原文、修订、地点、需求和审计，不保存音频，不调用外部服务。数据保留、访问控制、备份与删除策略由宿主配置。`ScoringPlugin` 的 Python API 是可信宿主接口，没有 HTTP token 检查；不要将不可信输入变成任意 Python 调用。

每个数据库仅由**单一进程 / 单个活动 Engine 实例**拥有。进程内 RLock 支持并发调用，但没有跨进程状态合并；不要用多个 Uvicorn workers 或多个插件实例共享同一个文件。需要多进程扩展时应实现宿主状态服务，而不是复制本地数据库连接。

## 验证与重新构建

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build --wheel
```

测试覆盖原评分算术与证据、未解决需求保留、修订/事件去重、并发持久化、人工升级与队列、断线/回拨模拟、跨域拒绝、CSRF、不同挂载前缀、实例隔离以及无导入副作用。机器可读插件入口见包内 `plugin.json`。此插件不导入评测标签、地图、语音或宿主的 `app` 包。
