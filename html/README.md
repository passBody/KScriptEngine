# KScript 类图（HTML）

用 Mermaid.js 渲染的项目类图，单文件自包含。

## 打开

双击 `class-diagram.html`，或浏览器打开 `file:///.../KScript/html/class-diagram.html`。

页面包含四张图：

1. **总览** — 全项目跨层关系（入口 → MainWindow → model 全家桶 → actions 步骤模板）。
2. **model 层** — 数据核心（KscpPackage / 变量体系 / 步骤体系 / 执行器 / 日志）。
3. **widgets 层** — UI（MainWindow 簇 + 4 棵管理树 + 卡片链 + 各树预览面板）。
4. **actions+libs+tools** — 8 个 Step 子类 + InputControl + 图片标注。

点击任一类框可打开对应源码文件。

## Mermaid 来源

页面按以下顺序尝试加载 Mermaid，任一成功即渲染：

1. 本地 `./mermaid.min.js`（离线可用，推荐）
2. jsdelivr CDN
3. unpkg CDN
4. cdnjs CDN
5. jsdelivr v10 兜底

若全部失败，页面会显示每张图的原始 Mermaid 文本（仍可阅读）。

### 离线：下载 mermaid.min.js

若 `html/mermaid.min.js` 不存在（首次使用 / 内网无法访问 CDN），手动下载一次即可永久离线：

```bash
# 任选其一
curl -sL https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js -o html/mermaid.min.js
# 或用 python
python -c "import urllib.request; urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js','html/mermaid.min.js')"
```

## 重新生成

类图源码内嵌于 `class-diagram.html` 的 `<script type="text/mermaid">` 块中，可直接编辑。若要按最新源码重抽：

- 三张分层图由并行子代理逐文件核验生成（model / widgets / actions+libs+tools）。
- 已排除全部 `DemoStep / _DemoInput / _DemoOutput / BadStep / _BadInput / _BadOutput / NoDcStep` 等内嵌冒烟夹具。
- 关系箭头含义：`<|--` 继承 · `*--` 组合 · `o--` 聚合 · `-->` 关联 · `..>` 依赖 · `<<X>>` 基类/构造型。
