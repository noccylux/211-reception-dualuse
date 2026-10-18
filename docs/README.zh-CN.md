[English](README.md) · 中文

# 文档布局

| 路径 | 内容 | 变更时机 |
|---|---|---|
| [hackathon.md](hackathon.md) | 官方活动信息：日程、截止时间、规则、赛道、评审。 | 主办方宣布变更时。 |
| [problem/](problem/) | 公布的题目（`brief.md`）和三个转折（`twists.md`），逐字记录，附我们的解读。 | 题目公布时及每次转折时。 |
| [architecture.md](architecture.md) | 当前的构建：双重用途叙事、组件、数据来源、演示路径。 | 随代码更新。 |
| [datasets.md](datasets.md) | 本地数据集清单、来源、局限和固定版本的下载清单。 | 数据集变更时。 |
| [evaluation.md](evaluation.md) | 在带代理标签的录制灾害消息上的首轮评估：方法、结果、局限。 | 评估重新运行时。 |
| [mentor-advice.md](mentor-advice.md) | 对应到固定 main 提交的导师反馈，附实现差距和建议的后续工作。 | 反馈对照新构建审阅时。 |
| [submission.md](submission.md) | Devpost 清单、使用的 AI 工具、路演提纲、Devpost 文本、演示脚本。 | 直到提交为止。 |
| [poster/](poster/) | 转折 3 海报：HTML 源文件、导出的 PDF 和 PNG、演示截图。导出命令见 [submission.md](submission.md#poster)。 | 海报变更时。 |
| [changes/](changes/) | 时间线：每个决策、转折响应或功能一条记录。 | 只追加。 |
| [agents/](agents/) | 编码代理的工作规则，由根目录的 `AGENTS.md` 索引。 | 规则变更时。 |
| `local/` | Git 忽略，仅存在于作者的机器上：本地 Python 环境、启动器以及供其代理使用的发布说明。在全新克隆中不存在，这是有意为之。 | 本地。 |
| `information/` | Git 忽略：`hackathon.md` 和 `problem/` 引用的已保存主办方页面和 PDF。 | 从不编辑。 |

记录格式与命名：[agents/change-records.md](agents/change-records.md)。
