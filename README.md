# 数智长征：数字叙事官（原版 UI + 企业级增强版）

本版本保留原项目的页面板块、比例和核心视觉风格，同时增强后端工程能力与展示稳定性。

## 本次增强

- 保留原 UI 版式：人物居中、左侧时间轴、右侧档案馆、底部输入区不重新布局。
- API Key 安全化：从 `.streamlit/secrets.toml` 或环境变量读取，不再写死在代码里。
- 中文 RAG 检索增强：支持长征事件专名、2~5 字短语匹配、来源页码保留。
- 引用来源展示：回答时显示命中的资料来源、页码和关键词。
- 加载动画：提问后显示“正在检索长征档案、比对史料证据”。
- 人物呼吸动画：静态状态轻微呼吸，回答状态增加光晕。
- 时间轴可点击：点击时间轴节点可自动触发对应问题。
- 语音缓存：不同回答生成不同音频缓存，避免反复覆盖 `speech.mp3`。

## 运行

```bash
python3 -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
python3 -m streamlit run app.py
```

## 配置 Kimi / Moonshot API Key

复制 `.streamlit/secrets.example.toml` 为 `.streamlit/secrets.toml`，然后填写：

```toml
MOONSHOT_API_KEY = "你的 Kimi/Moonshot API Key"
MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
MOONSHOT_MODEL = "moonshot-v1-8k"
```

不要把真实 API Key 上传到公开仓库或发给别人。


## 本版新增能力

- 保留原版 UI 的版式、比例和视觉中心，不改变左侧时间轴、中间人物、右侧档案馆和底部输入栏的位置。
- 新增人物轻微呼吸动画和回答时光晕。
- 时间轴节点可点击，并自动触发对应历史问题。
- 回答区新增引用来源，并在“原始史料证据”下方提供可折叠的馆藏资料片段。
- 右侧档案馆新增“讲解员模式 / 问答模式”切换。
- 保留企业级工程增强：API Key 不写死、配置集中管理、RAG 检索增强、语音缓存、异常处理。

## 部署说明

如果要分享给别人测试，请参考 `DEPLOYMENT.md`。最推荐先部署到 Streamlit Community Cloud；如果后期要做成正式网站，再迁移到 Render、Railway、Fly.io 或云服务器。

## 本版新增：站点式讲解员系统

讲解员模式已改为“站点导览模块”，不再完全依赖大模型临场生成。每个时间轴节点都有固定讲稿骨架：历史处境、关键事件、后续影响、精神收束，并在下方继续保留知识库命中的史料证据。这样能避免讲解内容只剩“伟大、壮丽、精神丰碑”等空泛概括。

入口：右侧档案馆上方点击“开启讲解员模式”，系统会从“瑞金集结出发”开始；回答区的“继续下一站”会依次进入下一站。
