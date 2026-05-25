# 数智长征部署方案

这个项目本质上是一个 Streamlit Web App。你本地运行时用的是：

```bash
python3 -m streamlit run app.py
```

如果想让别人不用开你的电脑也能访问，需要把它部署到云端服务器或 Streamlit Cloud。

## 方案 A：Streamlit Community Cloud（最适合先找同学测试）

适合：快速生成公网网址、少量用户测试、答辩前展示。

步骤：

1. 新建 GitHub 仓库，把项目代码上传。
2. 不要上传 `.streamlit/secrets.toml`。
3. 上传 `.streamlit/config.toml`、`requirements.txt`、`app.py`、`brain.py`、`knowledge_base.json` 等项目文件。
4. 到 Streamlit Community Cloud 选择该仓库部署。
5. 在 Cloud 的 Secrets 管理界面填写：

```toml
MOONSHOT_API_KEY = "你的 Kimi/Moonshot API Key"
MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"
MOONSHOT_MODEL = "moonshot-v1-8k"
```

6. App 入口文件选择 `app.py`。

注意：不要把真实 API Key 提交到 GitHub。

## 方案 B：Render / Railway / Fly.io（更像正式网站）

适合：更稳定、可以绑定自定义域名、后期接数据库或后台。

启动命令一般使用：

```bash
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

环境变量需要配置：

```text
MOONSHOT_API_KEY
MOONSHOT_BASE_URL
MOONSHOT_MODEL
```

## 方案 C：做成真正 App

如果要变成手机 App，有两条路线：

1. 低成本路线：继续用 Web App，然后手机浏览器访问，或者包装成 PWA。
2. 正式路线：前端改成 React / Flutter，后端保留 Python RAG 服务，用 FastAPI 提供接口。

当前项目建议先走“网站版”，等测试稳定后再考虑 App。

## 上线前检查清单

- [ ] `.streamlit/secrets.toml` 没有上传到 GitHub
- [ ] `requirements.txt` 能完整安装
- [ ] `knowledge_base.json` 体积没有超过部署平台限制
- [ ] `veteran.png` 可以正常加载
- [ ] 语音识别和语音合成在云端环境可用
- [ ] API Key 有调用额度
- [ ] 页面在 16:9 屏幕和普通笔记本屏幕都能展示
