# CrisisFusion 地图插件 1.0.0

这是可以迁移到其他主体的独立 Python / ASGI 插件，自带网页、HTTP API、地址判断器、区域关联器、LA County 县界和 Leaflet 静态资源。**不需要安装打分器、语音插件或原 CrisisFusion 主应用**。可以独立启动，也可以挂在现有 FastAPI / Starlette 主体下，通过 iframe 显示。

它接收宿主提供的完整通话文本和修订号，保留地址原话、核查依据及来源；按地址状态画不同形状，并根据有来源、当前有效的区域关联显示颜色。它不会计算或改变通话优先级。宿主可另外提供评分摘要，仅供展示。

## 安装与独立运行

需要 Python 3.11 或以上。建议在自己的项目虚拟环境中安装；离线机器需要预先准备依赖 wheel。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m crisisfusion_map --host 127.0.0.1 --port 8812 --db work/map.sqlite3
```

如果拿到的是 wheel，可使用 `python -m pip install crisisfusion_map-1.0.0-py3-none-any.whl`，然后运行同一 CLI。打开 [本机地图页面](http://127.0.0.1:8812/)；先点“启用地图插件”。网页顶端“接入通话 / 独立测试”可手动保存通话全文。插件默认关闭；加载页面、启用插件或保存通话都不会自动请求官方数据、地址服务或设备定位。

默认 CLI 数据库是相对当前工作目录的 `work/map.sqlite3`。`create_app()` 默认使用内存数据库；生产宿主应明确指定自己的文件。只支持 **单进程、单 worker**，不要用多个实例写同一个 SQLite 文件。文本、精确位置和核查记录以明文保存；宿主负责文件访问权限、备份与保留周期。没有自动后台下载、跟踪、付费 API 调用或外部遥测。

## 挂到另一个主体

```python
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI
from crisisfusion_map import create_app

map_app = create_app(db_path="work/map.sqlite3")

@asynccontextmanager
async def lifespan(host):
    # Starlette 不会自动启动挂载子应用的生命周期，宿主明确管理。
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(map_app.router.lifespan_context(map_app))
        yield

host = FastAPI(lifespan=lifespan)
host.mount("/plugins/map", map_app)

# 已经受宿主验证的通话事件可直接在服务端写入，不经过 HTTP。
map_app.state.store.upsert_call({
    "call_id": "call-123", "revision": 1,
    "text": "I am at 123 Main St, Los Angeles.",
    "language": "en", "input_mode": "host",
})
map_app.state.store.set_active_call("call-123", active=True)
```

运行 `uvicorn your_module:host --host 127.0.0.1 --port 8000`。页面地址是 `/plugins/map/`，静态资源和 API 都按当前前缀解析；无原站导航、DOM 或语音全局变量依赖。主体可嵌入：

```html
<iframe src="/plugins/map/" title="通话地图" style="width:100%;height:1000px;border:0" allow="geolocation 'self'"></iframe>
```

浏览器设备定位需要 HTTPS 或 localhost、页面和宿主 Permissions-Policy 允许，并由用户点击和授权。不要给不可信的跨站 iframe 开放地理位置。该 iframe 不自动读宿主内存，也不使用 `postMessage` 接收任意站点的数据；宿主通过下面的 API 或 Python 方法更新。

公网域名需要显式 `create_app(allowed_hosts=["console.example.com"])`，并在宿主层加入身份验证、授权、HTTPS 和访问控制。这里只做 Host / 同源 / CSRF 检查；**CSRF token 可由同源页面读取，不是用户身份认证**。不要直接把开发 CLI 暴露公网；反向代理应正确设置被信任的协议/Host，不能盲目信任外部转发头。

## 通话输入契约

`app.state.store.upsert_call(payload)` 与 `POST /api/geo/calls` 使用相同字段。每次发送当前 **完整原文快照**，不要仅发送新增句子；宿主负责把语音片段按序合成全文。

```json
{
  "call_id": "call-123",
  "revision": 1,
  "text": "I am at 123 Main St, Los Angeles.",
  "language": "en",
  "timestamp": "2026-10-17T18:00:00Z",
  "event_id": "voice-event-001",
  "input_mode": "browser_voice",
  "location": {"label": "123 Main St, Los Angeles"},
  "priority_assessment": {"category": "HIGH", "score": 82, "policy_version": "host-policy-v1"}
}
```

| 字段 | 约束 |
| --- | --- |
| `call_id` | 必填，1–128 字符，字母数字开头，可用字母数字、点、下划线、冒号、连字符 |
| `revision` | 必填，1 到 2147483647 的整数；新修改必须递增，可以跳号 |
| `text` | 必填字符串，最多 100000 字符，可为空；原文空格及换行完整保留 |
| `language` | 默认 `und`，最多 32 字符；地址规则主要覆盖美式地址及部分英语、西语、中文表述 |
| `timestamp` | 可选，带时区 ISO 8601 时间，保留为 `source_timestamp`；没有时用接收时间 |
| `event_id` | 可选，1–512 字符；重复 ID 不能携带不同数据 |
| `input_mode` | 默认 `host`；`browser_voice` 标记转写未核实，`replay` / `simulated_voice` 标记合成输入 |
| `location` | 可选对象，仅支持 `label`、`lat`、`lon`、`source`、`accuracy_m`；是报告事件地点，不是设备 GPS；经纬度须同时提供 |
| `priority_assessment` | 可选，仅接受 `category`、0–100 的 `score`、`policy_version`；不导入或调用打分器 |

同一当前修订号且所有规范化输入字段完全一致，返回 `duplicate: true`，不会新增历史。已经成功接收的 `event_id` 携带完全相同数据，即使当前通话已更新到更大修订号，仍返回重复成功，附 `event_revision`，不会把当前文本回滚；便于宿主断点重放。相同修订号不同内容、从未接收过的旧修订、相同 `event_id` 不同数据都返回 409。即使收到内容相同的更大修订号，它仍代表新的核查版本，旧人工确认失效；前端要求重新核查。返回的 `upsert_result.call.revisions` 保存完整历史，最多每通话 100 个修订，每个库最多 1000 通话，达到上限会明确拒绝，不会静默丢原话。宿主遇到 409 或其他失败应保留消费游标与原事件，处理版本冲突或归档容量后重试，不能直接跳过事件。

`set_active_call(call_id, active=True)` 只声明宿主所知的通话生命周期，不构成定位授权。通话结束时必须调用 `active=False`。进程重启后活动标记全部清除，防止旧通话仍被视为正在进行。

## HTTP 使用与常用接口

首先 `GET /api/geo/state` 获得 `csrf_token` 和 `store_id`。`store_id` 是数据库初始化时生成并持久化的 UUID：同一个数据库重启保持不变，新数据库使用新 ID。宿主中继应把消费游标绑定到 `store_id`，发现同一 URL 换了数据库时重放历史或重新初始化游标，避免旧游标跳过新库尚未接收的事件。所有写请求都需要实际页面所在 Origin（协议 + 主机 + 端口，**不要附加插件路径**）及 `X-CrisisFusion-Geo`。跨源浏览器调用不开放 CORS；跨服务集成建议在受保护宿主服务端调用 Python 方法，或由宿主同源代理。以下示例针对独立端口；挂载时只改 `base`：

```python
import httpx

origin = "http://127.0.0.1:8812"
base = origin  # 挂载例：origin + "/plugins/map"
with httpx.Client() as client:
    token = client.get(base + "/api/geo/state").json()["csrf_token"]
    client.headers.update({"Origin": origin, "X-CrisisFusion-Geo": token})
    client.post(base + "/api/geo/config", json={"enabled": True}).raise_for_status()
    client.post(base + "/api/geo/calls", json={
        "call_id": "call-123", "revision": 1,
        "text": "I am at 123 Main St, Los Angeles.", "language": "en"
    }).raise_for_status()
    client.post(base + "/api/geo/calls/call-123/active", json={"active": True}).raise_for_status()
```

| 接口 | 用途 |
| --- | --- |
| `GET /health` | 插件版本与存活状态 |
| `GET /api/geo/state` | 当前地图、数据源、通话地址和区域评估、token |
| `POST /api/geo/calls` | 完整通话快照；返回地图状态及 `upsert_result` |
| `POST /api/geo/calls/{call_id}/active` | `{"active":true}` / `false`，返回地图状态及 `activity_result` |
| `POST /api/geo/config` | `{"enabled":true,"providers":{"nws":true,"usgs":true}}`，字段可按需省略 |
| `POST /api/geo/refresh` | 明确手动获取官方来源；每源至少间隔 60 秒 |
| `POST /api/geo/event-geometry` | `{"event_id":"已有NWS事件ID"}`，按需取官方区域，禁止任意 URL |
| `POST /api/geo/address/geocode` | `{call_id,revision,address,consent:true}`，只发送所填地址，保留查询结果及精度限制 |
| `POST /api/geo/address/confirm` | `{call_id,revision,label,lat,lon,reviewer,note,confirmed:true,accuracy_m?}`；note 至少 10 字符 |
| `DELETE /api/geo/address/{call_id}` | 清除人工确认和地理编码候选，不删原文 |
| `POST /api/geo/caller-location` | `{call_id,lat,lon,accuracy_m,captured_at,consent:true}`，只接受宿主活动通话和 5 分钟内浏览器定位 |
| `DELETE /api/geo/caller-location/{call_id}` | 删除精确设备位置；审计日志不复制坐标 |
| `POST /api/geo/reports` | 保存本地人工报告，字段见下例 |
| `DELETE /api/geo/reports/{report_id}` | 删除人工报告 |

人工报告例子；没有半径时只保存报告点：

```json
{"call_id":"call-123","label":"来电报告的事件","lat":34.02,"lon":-118.285,
 "note":"操作员通过复述地址核查，范围由操作员记录，尚无官方警戒边界。",
 "source_url":"https://example.org/evidence","reviewed":true,"hazard_type":"shooting",
 "zone_radius_m":200,"zone_level":"HIGH","valid_minutes":30}
```

人工范围半径 10–10000 米、有效期 1–1440 分钟；有范围时必须提供 HTTPS 依据、核查说明并 `reviewed:true`。级别只允许 `INFO/WATCH/HIGH/CRITICAL`。插件不请求此依据链接，也不把它认证为官方内容；圆始终标为操作员定义、非官方。不要把示例证据网址用于实际核查。

## 如何读地图

| 维度 | 表示与规则 |
| --- | --- |
| 没有坐标 | 留在逐通话列表，不使用县中心伪造位置 |
| 空心菱形 | 有候选坐标但未确认，包括可选 Census 插值结果 |
| 实心圆 | 人工确认当前修订，保留核查人和依据；不等于系统证明了真实现场位置 |
| 叉形 | 地址存在冲突，需要人工核查 |
| 灰 / 蓝 / 黄 / 橙 / 红 | UNKNOWN / INFO / WATCH / HIGH / CRITICAL，表示本原型区域关注等级，与通话评分独立 |
| 蓝色设备点及误差圈 | 用户对活动通话单次授权的本网页设备位置，独立图层，不能定位远端电话 |
| 虚线人工圆 | 非官方的操作员假设范围，过期后不参与当前区域等级 |

NWS 当前 Actual Alert/Update 必须有有效时间、区域几何、最近 5 分钟内成功获取的缓存以及可用 CAP 字段；Severity 的 Minor→INFO、Moderate→WATCH、Severe→HIGH、Extreme→CRITICAL。Urgency 只接受 Immediate / Expected；Certainty 为 Possible / Unlikely 时最高 WATCH，Observed / Likely 保留映射级别。取消、过期、未来生效、字段缺失、陈旧缓存不形成当前有效等级。对应 [CAP 1.2 字段规范](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.pdf)，**颜色分级是本产品的原型规则，不是官方统一应急分级**。

点在多边形内、精度圆完全包含、边界附近可能重叠分别说明。使用 25 米原型边界保护距离；未知坐标精度不等于准确无误。多个有效匹配取最高背景级别。未确认坐标仅为条件性关联，冲突或过时人工确认使当前汇总返回 UNKNOWN。无匹配 / 灰色永远不等于安全。合成人工范围不进入当前区域等级。

**没有实测地址准确率，也不输出虚构百分比。** 地址规则的单元测试是功能验证，不是总体真实通话准确率评测。Census 使用 TIGER 街道范围插值，范围可能包含未建成门牌；匹配成功不证明来电者在该处，见 [Census 地理编码说明](https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html)。查询只有明确 `consent:true` 才发送当前输入框地址，完整通话原文不会发送给地理编码服务。

官方覆盖仅限 NWS 与 USGS。NWS Red Flag Warning 是[火险气象条件](https://www.weather.gov/safety/wildfire-ww)，不是火场。USGS 只取 LA County 县内近 7 天 M≥2.5 震中，震中不能推导当地震动强度、受损范围，也漏掉县外震中的本地震感；见 [USGS 震级与烈度说明](https://www.usgs.gov/programs/earthquake-hazards/earthquake-magnitude-energy-release-and-shaking-intensity)。没有接入完整官方火场、疏散区、ShakeMap 或实时枪击警戒区。所有来源链接、采集时间、过期及缓存失败都会显示。

## 网络与数据许可

NWS / USGS 只在手动刷新时请求固定官方 HTTPS 端点；区域加载只接受 NWS 的固定 CA zone URL；Census 仅在显式地址查询时调用。底图默认关闭，勾选后浏览器请求 OpenStreetMap 当前视野图块，第三方能看到网络 IP 和地图视野；不发送通话正文和自定义标记。不会进行预下载或离线图块抓取。

LA County 县界及来源记录保存在包内 `data/`。Leaflet 1.9.4 JS、CSS 和 BSD 许可在 `static/vendor/leaflet/`，地图保留 LA County / OSM 署名。`plugin.json` 是主体集成的机器可读声明。网络源规则和获取时间约束均保留；官方数据服务变化时需重新验证适配器。

## 验证

```powershell
python -m pip install ".[test]"
python -m pytest -q
```

测试覆盖地址候选/冲突、多边形与边界、缓存与有效期、Census 只发送明确地址、修订幂等和过时确认、迟到查询丢弃、设备授权、独立导入、SQLite 重启和 ASGI 挂载前缀。所有网络用 mock，不调用真实 GPS、麦克风或外部付费服务。真实现场识别准确率、完整灾害覆盖和大规模多租户部署不在本次验证范围。
