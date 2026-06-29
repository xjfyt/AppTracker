> **对应代码**：`tracker-core/src/agent.rs` (`DocumentMemory`)
> **维护提示**：修改标题→路径解析逻辑或记忆策略时同步更新本文档。

# 十一、DocumentMemory（文档记忆）

## 1、职责

DocumentMemory 是 agent.rs 中的本地记忆缓存，解决"窗口标题包含文件名但无法直接解析为路径"的问题。例如窗口标题为 `report.md - Typora`，但富化管线未能获取到文件路径时，DocumentMemory 可以从历史记录中匹配。

## 2、数据结构

```rust
struct DocumentMemory {
    by_process: HashMap<String, HashMap<String, String>>,  // "pid:exe" → { normalized_name → path }
    global: HashMap<String, String>,                       // normalized_name → path（跨进程）
    global_ambiguous: HashSet<String>,                     // 全局歧义名（多进程同名不同路径）
}
```

## 3、工作流程

### 记忆阶段（remember）

每次窗口信息更新时，DocumentMemory 从 `document_paths` 中提取 `kind == "file"` 的条目：

1. 检查路径是否绝对路径且文件存在
2. 提取文件名，转小写归一化
3. 按进程键（`pid:executable`）存入 `by_process`
4. 尝试存入 `global`：
   - 若已存在且路径不同 → 标记为歧义，从 global 移除
   - 若已存在且路径相同 → 跳过
   - 若不存在且未被标记歧义 → 存入

### 解析阶段（resolve_title_filename）

从窗口标题中提取文件名（`likely_document_name_from_title`），然后：

1. 优先查找进程本地记忆（`by_process`）
2. 回退到全局记忆（`global`）
3. 若命中，追加一条 `source: "title_memory"`, `confidence: 0.88` 的 DocumentSource

## 4、歧义处理

当不同进程打开同名但不同路径的文件时（如两个编辑器各打开一个 `readme.md`），全局记忆会标记该名称为歧义：

```
进程A 打开 /project-a/readme.md → global["readme.md"] = "/project-a/readme.md"
进程B 打开 /project-b/readme.md → global 移除 "readme.md"，加入 global_ambiguous
```

此后第三个进程的窗口标题包含 `readme.md` 时，全局记忆不会解析（避免误匹配），但进程 A 或 B 自身的窗口仍可通过进程本地记忆解析。

## 5、应用时机

DocumentMemory 在两个地方被调用：

1. **主循环**：`active_window()` 返回后立即 `apply_document_memory()`（在基础轮询阶段）
2. **富化 worker**：`enrich_window()` 返回后再次 `apply_document_memory()`（在富化阶段）

这确保即使富化管线遗漏了某个文档路径，DocumentMemory 也有机会补上。

## 6、去重

`apply()` 最后调用 `dedupe_documents()` 合并同路径的 DocumentSource，保留 confidence 最高的条目。

---

- 上一篇：[02-window-monitor.md](./02-window-monitor.md)
- 下一篇：[04-enrichment-pipeline.md](./04-enrichment-pipeline.md)
- 返回索引：[docs/README.md](../../README.md)
