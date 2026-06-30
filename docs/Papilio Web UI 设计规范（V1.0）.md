# **Papilio Web UI 设计规范（V1.0）**

**Design Philosophy**

> 

**Break the cocoon. Define the world you see.**

> 

Papilio 不是 RSS 阅读器，也不是新闻推荐系统，而是一个**个人认知操作系统（Personal Cognition Dashboard）**。

------

# **一、设计目标**

Papilio 的 Web UI 不追求：

- 阅读效率最大化
- 停留时间最大化
- 点击率最大化
- 推荐准确率最大化

而是追求：

**帮助用户建立属于自己的信息输入系统，并完成知识沉淀。**

因此整个 UI 必须服务四件事情：

获取信息 → 理解信息 → 比较信息 → 沉淀信息

而不是：

获取信息 → 无限滚动。

整个系统应该更像：

Bloomberg Terminal × Obsidian × Arc Browser × Linear

而不是：

Feedly × 今日头条 × Twitter。

------

# **二、整体设计语言**

## **Design Keywords**

整个系统应该具有以下气质：

- Calm
- Rational
- Minimal
- Dense
- Scientific
- Personal

用户打开页面第一感觉应该不是：

“今天有什么新闻？”

而是：

“今天世界发生了哪些值得理解的事情？”

------

# **三、视觉风格**

整体采用深色模式。

背景：

```
#0F1115
```

一级面板：

```
#161A23
```

二级面板：

```
#1C2230
```

边框：

```
#2A3245
```

正文：

```
#ECEEF3
```

次级文字：

```
#8B93A7
```

Accent Color：

Papilio Purple

```
#8B5CF6
```

辅助颜色：

Information Blue

```
#38BDF8
```

整个页面禁止：

- 大面积渐变
- 毛玻璃
- 发光按钮
- 卡片阴影
- 大面积动画

因为：

Papilio 是工作界面，不是展示页面。

------

# **四、整体布局**

采用经典三栏布局。

```
┌────────────────────────────────────────────────────────────────────┐
│ Papilio                                        Search (⌘K)        │
├──────────────┬───────────────────────────────┬────────────────────┤
│              │                               │                    │
│ Views        │ Timeline                      │ Cognition          │
│              │                               │                    │
│ Today        │                               │                    │
│ Clusters     │                               │                    │
│ AI           │                               │                    │
│ Research     │                               │                    │
│ GitHub       │                               │                    │
│ RSS          │                               │                    │
│               信息流                          │ 信息理解            │
│ Random       │                               │                    │
│ Saved        │                               │                    │
│              │                               │                    │
└──────────────┴───────────────────────────────┴────────────────────┘
```

整个页面宽度建议：

```
280
960
420
```

比例约：

```
18%
55%
27%
```

------

# **五、左侧：Perspective（观察世界）**

这里不是导航栏。

而是：

**你正在以什么视角观察世界。**

例如：

```
Today

AI

Research

Engineering

Markets

Startups

Clusters

Random

Saved

Archive
```

其中最重要的是：

Random。

Random 每次刷新随机展示低权重内容。

目的：

主动打破信息茧房。

这是整个 Papilio 的设计哲学之一。

------

# **六、中间：Timeline**

这是系统核心。

不是普通新闻列表。

而是：

认知时间线。

每张卡片采用统一结构：

```
Title

Hermes Summary

HN
GitHub
arXiv
RSS

4h ago

Importance ●●●●

Tags

Open

Cluster

→ Wiki
```

整个卡片高度控制：

180~220px

避免瀑布流。

避免长摘要。

保持浏览节奏。

------

# **七、Cluster View（Papilio 最大特色）**

普通 RSS：

```
一个来源
↓

一篇文章
```

Papilio：

```
一个事件
↓

多个来源
↓

Hermes 总结
↓

差异分析
```

例如：

```
OpenAI 发布新模型

Sources

HN

GitHub

官方 Blog

论文

Hermes Summary

一句话总结：

真正重要的是：

不是模型更新。

而是推理架构开始全面神经化。

Different Opinions

官方：

强调能力。

HN：

讨论成本。

GitHub：

讨论实现。

论文：

讨论理论基础。

Related Wiki

Transformer

Reasoning

Inference Scaling
```

这个页面应该成为：

Papilio 的灵魂。

------

# **八、右侧：Cognition Panel**

右侧永远展示：

当前信息的认知上下文。

包括：

## **Why important**

为什么值得看。

不是摘要。

而是：

Hermes 的判断。

例如：

```
影响未来 Agent 推理成本。

属于长期趋势。

建议关注。
```

------

## **Related Concepts**

例如：

```
MoE

Reasoning

RL

Scaling Law
```

点击即可跳 Wiki。

------

## **Similar Items**

展示：

过去相关事件。

例如：

```
OpenAI O3

Gemini 3

Claude 5
```

帮助建立长期记忆。

------

## **Knowledge Status**

例如：

```
未阅读

已阅读

已沉淀

已有 Wiki
```

整个生命周期一目了然。

------

# **九、Wiki Workflow**

整个产品最重要按钮：

```
→ Wiki
```

点击以后：

不是立即保存。

而是弹出：

```
Save to Wiki

Title

Summary

Entity

Related Concepts

References

Confirm
```

最后：

Hermes 自动完成：

```
Entity

Concept Link

Log

Index

Raw Article
```

用户只负责：

最后确认。

------

# **十、状态系统**

整个系统只有四种状态：

```
NEW

PROCESSED

SAVED

ARCHIVED
```

颜色保持克制。

例如：

```
NEW

灰色

PROCESSED

蓝色

SAVED

绿色

ARCHIVED

深灰
```

不要：

红色。

黄色。

警告色。

因为：

这不是任务管理软件。

------

# **十一、快捷键**

Papilio 应该支持：

```
J

下一条

K

上一条

O

打开原文

C

打开 Cluster

W

保存 Wiki

R

Random

/

搜索

ESC

返回
```

整个系统几乎可以不用鼠标。

------

# **十二、动画**

动画只允许：

150~200ms。

允许：

- Hover
- Fade
- Panel Slide

禁止：

- 弹跳
- 缩放
- 炫酷转场

Papilio 应该像：

VSCode。

而不是：

Notion。

------

# **十三、未来扩展**

未来右侧可以增加：

Knowledge Graph

```
        Transformer
              │
       Scaling Law
        │      │
     MoE     RLHF
        │
     Reasoning
```

以及：

Timeline Heatmap

展示：

过去一年真正重要的信息。

而不是：

过去一年点击最多的信息。

------

# **十四、设计原则**

整个 Papilio UI 应遵循五条原则。

**Information First**

界面服务于信息，而不是装饰信息。

**Structure over Feed**

展示信息之间的关系，而不是无限滚动。

**User Defines Reality**

世界由用户配置的信息源决定，而不是推荐算法决定。

**Knowledge over Consumption**

每一次阅读都应有机会沉淀为长期知识。

**Calm Interface**

降低视觉噪声，让注意力始终停留在内容本身。

------

# **最终目标**

Papilio 的首页不是一个资讯首页，而是一个每天都会打开的个人认知驾驶舱。

它不回答：

今天有什么新闻？

而回答：

今天哪些变化值得进入我的长期知识体系？