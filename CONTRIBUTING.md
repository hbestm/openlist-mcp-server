# 贡献指南

感谢您对 OpenList MCP Server 的兴趣！我们欢迎各种形式的贡献。

## 如何贡献

### 报告问题

如果您发现了 bug 或有功能建议，请通过 [GitHub Issues](https://github.com/hbestm/openlist-mcp-server/issues) 提交。

提交 issue 时请包含：
- 问题的清晰描述
- 复现步骤（如果是 bug）
- 期望行为与实际行为
- 环境信息（Python 版本、操作系统等）

### 提交代码

1. **Fork 仓库** 并克隆到本地
2. **创建分支**: `git checkout -b feature/your-feature-name`
3. **安装开发依赖**:
   ```bash
   pip install -e ".[dev]"
   ```
4. **编写代码** 并添加测试
5. **运行测试**:
   ```bash
   pytest tests/
   ```
6. **提交更改**: `git commit -m "feat: add your feature"`
7. **推送分支**: `git push origin feature/your-feature-name`
8. **创建 Pull Request**

### 代码规范

- 使用 Python 3.10+ 类型注解
- 遵循 PEP 8 风格
- 添加适当的 docstring
- 保持测试覆盖率

### 提交信息规范

我们使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `test:` 测试相关
- `refactor:` 代码重构
- `chore:` 构建/工具相关

示例：
```
feat: add batch upload support
fix: handle token expiration correctly
docs: update installation guide
```

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/hbestm/openlist-mcp-server.git
cd openlist-mcp-server

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 安装开发模式
pip install -e .

# 验证安装
openlist-mcp
```

## 测试

### 运行单元测试
```bash
pytest tests/
```

### 运行集成测试（需要 OpenList 实例）
```bash
export OPENLIST_URL="https://your-openlist.example.com"
export OPENLIST_USERNAME="your_username"
export OPENLIST_PASSWORD="your_password"
python scripts/live_integration.py
```

## 新增或修改工具

仓库里每项事实**只有一处来源**，其余都是它的投影 —— 所以加一个工具不再要求你记得改八个地方：

| 事实 | 唯一来源 | 谁负责对齐 |
|---|---|---|
| 工具属于哪个组、每组有哪些工具 | `src/openlist_mcp/skills.py` 的 `SKILL_GROUP_TOOLS` | —（本身就是来源） |
| 工具的中文说明 | `scripts/render_tool_docs.py` 的 `_ZH` | `--check` 发现缺条目即报错 |
| 工具的英文说明 | 函数自身的 docstring（模型读到的就是它） | 生成时自动取首段 |
| README×2 的工具表、AI_GUIDE 的分组清单 | 上面三者的投影 | `scripts/render_tool_docs.py` |
| 散文里引用的分组/档位数量 | 注册表 | `tests/test_docs_consistency.py` |
| CHANGELOG 小节 ↔ 版本表、包版本号 | 各自文件 | 同上 |

因此流程是：

1. 在对应的 `src/openlist_mcp/tools/*.py` 中定义工具，docstring 写清楚 —— **它就是模型看到的工具描述**，写得越好两边都受益
2. 把工具名加进 `skills.py` 中对应的组
3. 在 `scripts/render_tool_docs.py` 的 `_ZH` 里补一条中文说明
4. 运行 `python scripts/render_tool_docs.py` 重新生成文档
5. 运行 `pytest tests/` —— 守卫会逐条检查上表是否对齐

漏了第 3 步、忘了重生成、或删掉了生成标记，`--check` 和测试都会**立刻失败并指出缺什么**，而不是等到几个月后有人偶然翻到。

`pre-commit` 已配置：改动 `skills.py` 或 `tools/` 时会自动重跑生成器。

## 许可证

通过提交贡献，您同意您的代码将在 MIT 许可证下发布。
