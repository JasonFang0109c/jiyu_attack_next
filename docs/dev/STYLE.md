<div align="center">
<h1>代码风格规范</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="Ruff" src="https://img.shields.io/badge/格式化与检查-Ruff-261230?style=for-the-badge&logo=ruff&logoColor=white&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a> 丨 <a href="STRUCTURE.md">项目结构</a></p>
</div>

---

排版由 `ruff format` 自动完成，静态检查由 `ruff check` 把关，注释与 docstring 由开发者按本文手写。**每写完一处代码就格式化一次**，不要攒到提交前统一处理。

## 工具与配置

配置在根目录 [pyproject.toml](../../pyproject.toml)：ruff 格式化与 lint、行宽 88、目标版本 `py313`。开发工具单独放在 [requirements-dev.txt](../../requirements-dev.txt)，不进打包产物。

```powershell
python -m pip install -r requirements-dev.txt
```

`app/packets/constants.py` 保存逐字节对齐的十六进制报文数组（`store`），整体被 ruff 排除。该文件只手工维护：新增报文时沿用现有每行字节数与缩进，不要为对齐重排已有行，否则会产生上千行的无意义改动。

## 排版规则

- 行宽 88 个字符，超长由 `ruff format` 自行换行；无法拆分的超长字符串要提成模块级常量后再引用。
- 4 空格缩进，双引号优先，两个顶层定义之间空两行，方法之间空一行。
- 导入顺序为“标准库 / 第三方 / 本项目”，每组之间空一行；不使用通配符导入（如 `from .common import *`）。
- 不在同一行塞多条语句，不用行尾分号，不留行尾空白。
- 不手工对齐 `=`、`:` 或续行括号；续行样式以 `ruff format` 的输出为准，不要为了竖排再改回去。

## Docstring

采用 Google 风格：段落关键字用英文（`Args`、`Returns`、`Yields`、`Raises`、`Attributes`），说明文字用中文，首行是一句以句号结尾的摘要。

当前代码没有类型注解，示例与正文也不要求补注解，参数说明只描述含义与约束。今后若引入注解，`Args` 段落仍按“参数名: 说明”书写，不在 docstring 里重复类型。

只为模块、公共类、公共函数和逻辑复杂的函数写 docstring；私有小函数不强制，名字能说清楚就不写。接口的参数、返回值与异常发生变化时必须同步更新 docstring，不写与实现不符的历史描述。

```python
def split_message(content):
    """按报文容量把长文本拆成多条消息。

    逐个字符累计 UTF-16 编码后的字节数，超出 MESSAGE_MAX_BYTES 时先交付
    已累积的内容，保证拆出的每条消息都能被学生端完整接收。

    Args:
        content: 待拆分文本，不能包含 NUL 字符。

    Yields:
        每轮产出的消息片段，拼接后与 content 完全一致。

    Raises:
        ValueError: 文本包含 NUL 字符时抛出。
    """
```

```python
@dataclass
class SendOptions:
    """一次发送任务的参数。

    Attributes:
        target: 目标地址，支持单个 IPv4、末段范围与 /24 网段。
        port: 学生端 UDP 端口，默认 4705。
        loops: 发送轮数，必须大于 0。
        cancel_event: 用于中途取消发送的事件对象，未传入时不支持取消。
    """
```

只有一行摘要就够的模块，直接写一句，不凑段落：

```python
"""报文构造、消息分片与目标地址解析。"""
```

## 注释

注释解释“为什么”，不复述代码“做了什么”。一律使用整行中文注释，写在被解释代码的上一行、与代码同缩进；不使用行尾短注释。

```python
# 表头复选框只同步筛选结果，避免把隐藏行也带上导出范围。
self.header_checkbox.setChecked(checked)
```

```python
# 屏蔽信号后再填充，否则每插一行都会触发一次选中状态重算。
self.table.blockSignals(True)
```

- 注释与代码一起维护：改动逻辑时同步改动注释，过时注释直接删掉而不是留着。
- 不提交被注释掉的旧代码，历史留在 Git 里。
- 待办写成 `# TODO(负责人): 具体动作`，负责人缺省时可省略括号。
- 术语首次出现时写中文并附英文原词，例如“报文（DMOC）”。

## 组件库资料

界面组件来自 `qfluentwidgets`，只在新增或改动组件用法时查证，调整布局参数、文案或已有控件不必重新翻文档：

- [QFluidWidgets 文档](https://qfluentwidgets.com/)
- [PySide6 分支源码](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6)
- [PySide6 示例](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6/examples)

以 PySide6 分支与本项目安装的 `PySide6-Fluent-Widgets` 版本为准，不套用 PyQt5/PyQt6 示例。文档、示例与本地版本冲突时，先导入、读源码或写最小测试验证，再改代码。亚克力与云母统一调用组件自带的 `windowEffect`，不自行用 ctypes 操作窗口材质。

## 界面视觉规范

界面数值以 Windows 11 的 WinUI 3 主题资源为准，写在 `app/gui/theme.py`，改界面时先取这里的常量，不要就地写字面量。`qfluentwidgets` 的默认值只作参考：浅色下它的卡片描边比 WinUI 淡，窗口底色也偏蓝。

### 两个圆角

| 令牌 | 值 | 用在哪 |
| --- | --- | --- |
| `ControlCornerRadius` | 4 | 控件与内容面：卡片、表格、树、输入框、按钮 |
| `OverlayCornerRadius` | 8 | 项目自绘的浮出层：对话框；弹出菜单与提示气泡由组件库自绘，不再覆盖 |

小圆角让内容面显得紧凑、成排卡片之间不打架；浮出层面积大、离背景更远，圆角大一点才和阴影一起成立。项目里对应 `CONTROL_CORNER_RADIUS` 与 `OVERLAY_CORNER_RADIUS`。

### 页面骨架

带顶部导航的容器页（远程攻击、本机工具）自上而下是“组标题 → 导航栏 → 子页面卡片”，三段留白按 WinUI 的间距阶梯固定：

| 位置 | 值 | 依据 |
| --- | --- | --- |
| 组标题顶部留白 | 24 | 与普通页 `Page` 的 24 像素上边距一致，换页时标题不上下跳 |
| 组标题到导航项文字 | 16 | 对应 WinUI“控件与标头 8 epx” |
| 选中指示条到卡片 | 24 | 对应 WinUI“内容区域之间 12 epx” |

两者按 8:12 排成 2:3：标题与导航同属页头，贴得近；导航与内容换了一组，拉开一档。导航项自带上下各 10 像素内边距，所以布局里只补 6 像素。参见[内容布局和间距](https://learn.microsoft.com/windows/apps/design/style/spacing)。

导航栏用 `Pivot`，规格如表：

| 项 | 值 | 说明 |
| --- | --- | --- |
| 导航项字号 | 14（`NAV_ITEM_PIXELS`） | 与卡片正文 `BodyLabel` 同号，比组标题 `SubtitleLabel` 的 20 小一档 |
| 选中指示条 | 16×3，下缘留 4 | `PivotHeaderItem` 模板的 `SelectedPipe`，即 `setIndicatorLength(16)` |
| 导航栏宽度 | 自身 `sizeHint` | 用 `addWidget(pivot, 0, Qt.AlignLeft)`；组件库 `sizePolicy` 是 `Minimum`，行内加 `addStretch()` 会把多余宽度平分给它 |

### 侧边导航

左侧导航栏（`SidebarPanel`）与右侧内容区共用一条顶部基线，但比内容区略低；标题栏只在按钮占用的那一段宽度内后退，图标与标题始终留在左侧：

| 项 | 值 | 依据 |
| --- | --- | --- |
| 导航首项顶边 | 内容区顶边 + 5 | 对应 WinUI 的 `NavigationViewPaneContentGridMargin` 上 3 像素与 `NavigationViewItemButtonMargin` 上 2 像素 |
| 工具按钮与首项间距 | 11（`SIDEBAR_TOOL_ROW_GAP`） | 工具行 36 + 11 = 47，减去面板自身 6 像素后首项正好落在 +5 |
| 标题栏左缘（展开） | 工具行右缘 + 2（`TITLE_BAR_TOOL_GAP`） | 返回与菜单并排时工具行 80 宽，标题栏从 86 起，图标与标题紧跟在按钮之后 |
| 标题栏左缘（收起） | 46（`TITLE_BAR_COLLAPSED_OFFSET`） | 面板收起后宽 48，减 2 让标题栏压住面板右缘而不是留下缝 |
| 标题栏文字左留白 | 6（`TITLE_BAR_MARGIN`） | 图标与标题文字的内缩，与按钮内边距对齐 |
| 返回按钮（收起时） | 标题栏图标左侧（40×36） | 图标栏只有 48 宽塞不下两个按钮，上下排列又会把菜单按钮挤进导航项 |

收起成图标栏时，菜单按钮留在顶部原位（y = 6），返回按钮搬进标题栏、排在图标左侧，展开后再搬回工具行与菜单按钮并排——`SidebarPanel._place_return_button` 负责这次迁移，两种状态都不会让按钮落进导航项或压到标题栏下面。

导航项本身不自带间距，首项的下沉量要加在工具行与首项之间，所以 `SidebarPanel` 用 `topLayout` 的 `spacing` 而不是下边距——组件库会把“顶部”位置的导航项插进同一个布局，用边距只会把下面的滚动区一起推下去。改动这些数值时同步改 `app/gui/window/data.py` 的常量，不要在 `sidebar.py` 里另写一份。

### 颜色

| 令牌 | 浅色 | 深色 | 用在哪 |
| --- | --- | --- | --- |
| `CardBackgroundFillColorDefault` | `#B3FFFFFF` | `#0DFFFFFF` | 卡片填充 |
| `CardStrokeColorDefault` | `#0F000000` | `#19000000` | 卡片描边 |
| `SolidBackgroundFillColorBase` | `#F3F3F3` | `#202020` | 窗口底色（实色材质） |
| 语义色 ok | `#107C10` | `#6CCB5F` | 状态行、成功提示 |
| 语义色 warning | `#9D5D00` | `#FCE100` | 需要留意但可恢复的状态 |
| 语义色 error | `#C42B1C` | `#FF99A4` | 失败、越界、被占用等错误 |
| 语义色 neutral | `#605E5C` | `#A0A0A0` | 中性说明文字 |
| 滚动条滑块 | 黑色 27% | 白色 24% | 滚动时短暂出现的细滑块 |

浅色下卡片是 70% 的白，压在灰底上刚好浮起一层；描边只有 6% 的黑，负责收边而不是勾轮廓。深色下填充几乎透明，靠 10% 的黑色描边把卡片压在深色背景上。语义色只用于文字与图标，不给背景上色。

### 落点

- `app/gui/theme.py` 存常量与取值函数：`card_fill()`、`card_stroke()`、`window_background(dark=None)`、`tone_color(tone)`（`ok`/`warning`/`error`/`neutral`）、`scroll_colors()`。
- `app/gui/widgets/common.py` 的 `FluentCard` 用 `paintEvent` 画填充与描边，`FluentDialog` 追加一条 QSS 覆盖组件库写死的 10 像素对话框圆角。
- 新增卡片一律继承 `FluentCard`，不要直接用 `SimpleCardWidget`；新增对话框用 `FluentDialog`，不要直接用 `Dialog`。
- 浮出层圆角只覆盖项目自绘的容器：`FluentDialog` 用 `OVERLAY_CORNER_RADIUS`；`RoundMenu`、`ToolTip`、`TeachingTip` 的圆角、描边与阴影由组件库自己绘制，按上节“复用组件库”的要求直接调用，不追加覆盖样式。
- 状态文字的颜色一律走 `tone_color()`，不在页面里写 `#c42b1c` 这类字面量；滚动条滑块同理，用 `scroll_colors()` 取色。
- 云母与亚克力材质开启时窗口必须是全透明，只有实色材质才用窗口底色，主窗口的 `_normalBackgroundColor` 委托给 `app/gui/window/service.py` 的 `WindowService`，窗口材质由该服务的 `apply_window_material` 统一应用。

## 每次写完代码跑格式化

改完任意 `.py` 文件后立刻执行，让格式化成为一次独立动作，不要留到最后：

```powershell
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check --fix .
```

提交前确认没有待格式化内容：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
```

- `--check` 只报告不修改，用于确认工作区已格式化；有输出时本地先跑一次不带 `--check` 的命令。
- 只改 Markdown 时不涉及此步骤。
- 格式化属于 [`style`](CONTRIBUTING.md#提交信息) 改动，与功能改动分开提交，便于审阅时跳过纯排版差异。
