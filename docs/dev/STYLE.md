<div align="center">
<h1>代码风格规范</h1>
<p>
   <img alt="Python 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=212121">
   <img alt="Black" src="https://img.shields.io/badge/格式化-Black-000000?style=for-the-badge&logo=black&logoColor=white&labelColor=212121">
</p>
<p><a href="../../README.md">← 返回项目首页</a> 丨 <a href="CONTRIBUTING.md">开发与提交规范</a> 丨 <a href="STRUCTURE.md">项目结构</a></p>
</div>

---

排版由 Black 自动完成，注释与 docstring 由开发者按本文手写。**每写完一处代码就格式化一次**，不要攒到提交前统一处理。

## 工具与配置

配置在根目录 [pyproject.toml](../../pyproject.toml)：Black、行宽 88、目标版本 `py313`。开发工具单独放在 [requirements-dev.txt](../../requirements-dev.txt)，不进打包产物。

```powershell
python -m pip install -r requirements-dev.txt
```

`app/core/constants.py` 保存逐字节对齐的十六进制报文数组（`store`），整体被 Black 排除。该文件只手工维护：新增报文时沿用现有每行字节数与缩进，不要为对齐重排已有行，否则会产生上千行的无意义改动。

## 排版规则

- 行宽 88 个字符，超长由 Black 自行换行；Black 无法拆分的超长字符串要提成模块级常量后再引用。
- 4 空格缩进，双引号优先，两个顶层定义之间空两行，方法之间空一行。
- 导入顺序为“标准库 / 第三方 / 本项目”，每组之间空一行；不使用通配符导入（如 `from .common import *`）。
- 不在同一行塞多条语句，不用行尾分号，不留行尾空白。
- 不手工对齐 `=`、`:` 或续行括号；续行样式以 Black 的输出为准，不要为了竖排再改回去。

## Docstring

采用 Google 风格：段落关键字用英文（`Args`、`Returns`、`Yields`、`Raises`、`Attributes`），说明文字用中文，首行是一句以句号结尾的摘要。

只为模块、公共类、公共函数和逻辑复杂的函数写 docstring；私有小函数不强制，名字能说清楚就不写。接口的参数、返回值与异常发生变化时必须同步更新 docstring，不写与实现不符的历史描述。

```python
def split_message(content: str) -> Iterator[str]:
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

## 每次写完代码跑格式化

改完任意 `.py` 文件后立刻执行，让格式化成为一次独立动作，不要留到最后：

```powershell
.\.venv\Scripts\python.exe -m black .
```

提交前确认没有待格式化内容：

```powershell
.\.venv\Scripts\python.exe -m black --check .
```

- `--check` 只报告不修改，用于确认工作区已格式化；有输出时本地先跑一次不带 `--check` 的命令。
- 只改 Markdown 时不涉及此步骤。
- 格式化属于 [`Style`](CONTRIBUTING.md#提交信息) 改动，与功能改动分开提交，便于审阅时跳过纯排版差异。
